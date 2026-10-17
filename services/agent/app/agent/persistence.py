"""Chat persistence: ChatThread / ChatMessage read-write, and the LangGraph checkpointer.

Checkpointer choice: langgraph-checkpoint-postgres `PostgresSaver` on a psycopg pool (same
database as the app). Its tables are created by our Alembic migration, so `setup()` is never
called at runtime. Without DATABASE_URL (unit tests) an in-memory saver is used.
"""

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.agent.state import DealBrief, Lang
from app.auth.deps import CurrentUser, can_read_party
from app.config import get_settings
from app.db.enums import ChatRole, DealStatus, Language
from app.db.models import ChatMessage, ChatThread, Deal
from app.db.session import normalize_url
from app.errors import Forbidden, NotFound

TITLE_CHARS = 80
BRIEF_DEALS = 10
CLOSED = frozenset({DealStatus.COMPLETED, DealStatus.CANCELLED})


def now() -> datetime:
    return datetime.now(UTC)


# --- threads & messages ---------------------------------------------------------------------


def get_thread(db: Session, user: CurrentUser, thread_id: uuid.UUID) -> ChatThread:
    """The caller's own thread. Another user's thread is 403; a user only sees their own."""
    thread = db.get(ChatThread, thread_id)
    if thread is None:
        raise NotFound("chat thread not found")
    if thread.user_id != user.id:
        raise Forbidden("this chat thread belongs to another user")
    return thread


def create_thread(
    db: Session, user: CurrentUser, first_message: str, language: Lang, deal_id: uuid.UUID | None
) -> ChatThread:
    title = " ".join(first_message.split())[:TITLE_CHARS] or "New chat"
    ts = now()
    thread = ChatThread(
        id=uuid.uuid4(),
        user_id=user.id,
        title=title,
        language=Language(language),
        created_at=ts,
        updated_at=ts,
        deal_id=deal_id,
        tokens_used=0,
    )
    db.add(thread)
    db.flush()
    return thread


def list_threads(db: Session, user: CurrentUser, q: str | None = None) -> list[ChatThread]:
    stmt = select(ChatThread).where(ChatThread.user_id == user.id)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(ChatThread.title.ilike(f"%{escaped}%", escape="\\"))
    return list(
        db.scalars(
            stmt.order_by(func.coalesce(ChatThread.updated_at, ChatThread.created_at).desc())
        ).all()
    )


def rename_thread(db: Session, user: CurrentUser, thread_id: uuid.UUID, title: str) -> ChatThread:
    thread = get_thread(db, user, thread_id)
    thread.title = title
    thread.updated_at = now()
    db.commit()
    return thread


def delete_thread(db: Session, user: CurrentUser, thread_id: uuid.UUID) -> None:
    """Deletes the thread, its messages (FK cascade) and its LangGraph checkpoints."""
    thread = get_thread(db, user, thread_id)
    # Checkpoints (raw conversation state) go first, so a failure never leaves them orphaned.
    get_checkpointer().delete_thread(str(thread_id))
    db.delete(thread)
    db.commit()


def set_feedback(
    db: Session, user: CurrentUser, message_id: uuid.UUID, rating: str, comment: str | None
) -> ChatMessage:
    """👍/👎 on one of the caller's assistant messages (stored in meta.feedback)."""
    msg = db.get(ChatMessage, message_id)
    thread = db.get(ChatThread, msg.thread_id) if msg is not None else None
    # One answer for missing, someone else's, and non-assistant messages (no existence oracle).
    if msg is None or thread is None or thread.user_id != user.id or msg.role != ChatRole.ASSISTANT:
        raise NotFound("message not found")
    msg.meta = {
        **(msg.meta or {}),
        "feedback": {"rating": rating, "comment": comment, "at": now().isoformat()},
    }
    db.commit()
    return msg


def list_messages(db: Session, thread: ChatThread) -> list[ChatMessage]:
    return list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.thread_id == thread.id).order_by(ChatMessage.seq)
        ).all()
    )


def append_message(
    db: Session,
    thread: ChatThread,
    role: ChatRole,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ChatMessage:
    # Row lock on the thread serialises seq allocation for parallel turns (held until commit).
    db.execute(select(ChatThread.id).where(ChatThread.id == thread.id).with_for_update())
    seq = (
        db.scalar(select(func.max(ChatMessage.seq)).where(ChatMessage.thread_id == thread.id)) or 0
    ) + 1
    msg = ChatMessage(
        id=uuid.uuid4(),
        thread_id=thread.id,
        seq=seq,
        role=role,
        content=content,
        created_at=now(),
        meta=meta,
    )
    db.add(msg)
    db.flush()
    return msg


def add_tokens(db: Session, thread: ChatThread, tokens: int) -> int:
    """Atomic increment (parallel turns on one thread both count); returns the new total."""
    total = db.execute(
        update(ChatThread)
        .where(ChatThread.id == thread.id)
        .values(tokens_used=ChatThread.tokens_used + tokens, updated_at=now())
        .returning(ChatThread.tokens_used)
    ).scalar_one()
    db.refresh(thread)
    return int(total)


# --- context --------------------------------------------------------------------------------


def resolve_deal(db: Session, user: CurrentUser, ref_or_id: str) -> Deal:
    """A deal the caller may read, by reference or UUID. Others' deals look missing (404)."""
    cond = Deal.reference == ref_or_id
    with contextlib.suppress(ValueError):
        cond = cond | (Deal.id == uuid.UUID(ref_or_id))
    deal = db.scalars(select(Deal).where(cond)).first()
    if deal is None or not can_read_party(user, deal.buyer_id):
        raise NotFound("deal not found")
    return deal


def deals_brief(db: Session, party_id: uuid.UUID | None) -> list[DealBrief]:
    """Ids and reference codes only (no amounts or names) for the agent's context."""
    if party_id is None:
        return []
    deals = db.scalars(
        select(Deal)
        .where(Deal.buyer_id == party_id)
        .order_by(Deal.opened_on.desc())
        .limit(BRIEF_DEALS)
    ).all()
    return [
        {"id": str(d.id), "reference": d.reference, "status": str(d.status)}
        for d in deals
        if d.status not in CLOSED
    ]


# --- checkpointer ---------------------------------------------------------------------------


def _psycopg_url(url: str) -> str:
    return (
        make_url(normalize_url(url))
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


_pools: dict[str, ConnectionPool] = {}
_memory = InMemorySaver()


def get_checkpointer() -> BaseCheckpointSaver[Any]:
    settings = get_settings()
    if settings.database_url is None:
        return _memory
    url = _psycopg_url(settings.database_url.get_secret_value())
    pool = _pools.get(url)
    if pool is None:
        pool = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=5,
            open=True,
            # prepare_threshold=0: works through pgbouncer / Neon pooled endpoints.
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        _pools[url] = pool
    return PostgresSaver(conn=pool)  # type: ignore[arg-type]


def close_checkpointers() -> None:
    while _pools:
        _, pool = _pools.popitem()
        pool.close()
