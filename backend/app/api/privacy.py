"""Privacy transparency endpoints (Phase P18): the live counter, the "what did the AI see?"
X-ray for a chat message or a document check, the judge playground dry-run and the admin overview.
Responses carry the caller's own text or masked payloads, never the token vault."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, Select, cast, func, select, true
from sqlalchemy.orm import Session

from app.agent.persistence import get_thread
from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
from app.db.enums import ChatRole
from app.db.models import ChatMessage, ChatThread, PrivacyRecord
from app.db.session import get_db
from app.errors import Forbidden, NotFound
from app.llm import tracing
from app.privacy import views
from app.privacy.records import new_gateway
from app.schemas.privacy import (
    DayPoint,
    PrivacyConfigOut,
    PrivacyDryRunIn,
    PrivacyDryRunOut,
    PrivacyOverviewOut,
    RecentRecord,
    SummaryOut,
    TotalsOut,
    TraceOut,
    XrayOut,
)
from app.services.documents.read import FULL_VIEW, find_document, role_of

router = APIRouter(prefix="/privacy", tags=["privacy"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
SERIES_DAYS = 14
RECENT = 20
RECENT_PAYLOAD_CHARS = 2000


def _require_reader(user: CurrentUser) -> None:
    if not user.reads_all:
        raise Forbidden("this view is for admins and judges")


def _by_type(db: Session, *where: Any) -> dict[str, int]:
    """Sum of the per-call counters by identifier type (JSONB object → key/value rows)."""
    rec = PrivacyRecord.__table__
    kv = func.jsonb_each_text(rec.c.masked_by_type).table_valued("key", "value").lateral()
    q: Select[Any] = select(kv.c.key, func.sum(cast(kv.c.value, Integer))).select_from(
        rec.join(kv, true())
    )
    for w in where:
        q = q.where(w)
    return {k: int(v) for k, v in db.execute(q.group_by(kv.c.key)).all()}


@router.post("/dry-run", response_model=PrivacyDryRunOut)
def dry_run(body: PrivacyDryRunIn, db: Db, user: User) -> PrivacyDryRunOut:
    """Mask the typed text and show what a model would receive. Saves nothing, calls no model."""
    _require_reader(user)
    return views.dry_run(body.text, new_gateway(db, user, mask_amounts=body.mask_amounts))


@router.get("/summary", response_model=SummaryOut)
def summary(db: Db, user: User, thread_id: uuid.UUID | None = None) -> SummaryOut:
    """Identifiers protected / leaked: one conversation, the caller's chats, or (admin) all."""
    where: list[Any] = []
    if thread_id is not None:
        get_thread(db, user, thread_id)
        where.append(PrivacyRecord.thread_id == thread_id)
    elif not user.reads_all:
        where.append(PrivacyRecord.user_id == user.id)
    protected, leaked, calls = db.execute(
        select(
            func.coalesce(func.sum(PrivacyRecord.protected), 0),
            func.coalesce(func.sum(PrivacyRecord.leaked), 0),
            func.count(PrivacyRecord.id),
        ).where(*where)
    ).one()
    return SummaryOut(
        protected=int(protected),
        leaked=int(leaked),
        calls=int(calls),
        by_type=_by_type(db, *where),
    )


def _rows(db: Session, *where: Any) -> list[PrivacyRecord]:
    return list(
        db.scalars(select(PrivacyRecord).where(*where).order_by(PrivacyRecord.created_at)).all()
    )


def _xray(kind: str, left: list[Any], rows: list[PrivacyRecord]) -> XrayOut:
    stats = views.count_tokens([r.masked_payload for r in rows])
    stats.leaked_count = sum(r.leaked for r in rows)
    stats.chars_sent = sum(r.chars_sent for r in rows if r.sent)
    return XrayOut(
        kind=kind,  # type: ignore[arg-type]
        available=bool(rows),
        stats=views.stats_out(stats),
        left=left,
        right=[
            views.right_block(_label(r), r.node, r.model, r.sent, r.masked_payload) for r in rows
        ],
    )


def _label(r: PrivacyRecord) -> str:
    return {
        "router": "Routing",
        "agent": "Planning",
        "respond": "Answer",
        "extract": "Extraction",
    }.get(r.node, r.node)


@router.get("/messages/{message_id}", response_model=XrayOut)
def message_xray(message_id: uuid.UUID, db: Db, user: User) -> XrayOut:
    msg = db.get(ChatMessage, message_id)
    thread = db.get(ChatThread, msg.thread_id) if msg else None
    if msg is None or thread is None or msg.role != ChatRole.ASSISTANT:
        raise NotFound("message not found")
    get_thread(db, user, thread.id)
    question = db.scalar(
        select(ChatMessage)
        .where(
            ChatMessage.thread_id == thread.id,
            ChatMessage.role == ChatRole.USER,
            ChatMessage.seq < msg.seq,
        )
        .order_by(ChatMessage.seq.desc())
        .limit(1)
    )
    gw = new_gateway(db, user)
    left = []
    if question is not None:
        left.append(views.left_block("You wrote", question.content, gw))
    if msg.content:
        left.append(views.left_block("Assistant answer", msg.content, gw))
    return _xray("message", left, _rows(db, PrivacyRecord.message_id == msg.id))


@router.get("/documents/{document_id}", response_model=XrayOut)
def document_xray(document_id: uuid.UUID, db: Db, user: User) -> XrayOut:
    from app.services.documents.extract_text import extract_text
    from app.services.documents.storage import get_storage

    doc, deal = find_document(db, user, document_id)
    if role_of(user, deal) not in FULL_VIEW:
        raise Forbidden("document privacy details are for the buyer, admins and judges")
    rows = _rows(db, PrivacyRecord.document_id == doc.id)
    if rows:  # latest check only
        latest = max(rows, key=lambda r: r.created_at).run_id
        rows = [r for r in rows if r.run_id == latest]
    left = []
    try:
        pdf = extract_text(get_storage().get(doc.storage_path), doc.mime_type)
        if pdf is not None and pdf.visible_text.strip():
            left.append(views.left_block("Document text", pdf.visible_text, new_gateway(db, user)))
    except Exception:
        left = []
    return _xray("document", left, rows)


@router.get("/admin/overview", response_model=PrivacyOverviewOut)
def overview(db: Db, user: User) -> PrivacyOverviewOut:
    _require_reader(user)
    protected, leaked, calls = db.execute(
        select(
            func.coalesce(func.sum(PrivacyRecord.protected), 0),
            func.coalesce(func.sum(PrivacyRecord.leaked), 0),
            func.count(PrivacyRecord.id),
        )
    ).one()
    today = datetime.now(UTC).date()
    since = datetime.combine(today - timedelta(days=SERIES_DAYS - 1), datetime.min.time(), UTC)
    day = func.date_trunc("day", PrivacyRecord.created_at)
    per_day = {
        d.date().isoformat(): (int(p), int(lk))
        for d, p, lk in db.execute(
            select(day, func.sum(PrivacyRecord.protected), func.sum(PrivacyRecord.leaked))
            .where(PrivacyRecord.created_at >= since)
            .group_by(day)
        ).all()
    }
    series = [
        DayPoint(
            day=(d := (today - timedelta(days=SERIES_DAYS - 1 - i)).isoformat()),
            protected=per_day.get(d, (0, 0))[0],
            leaked=per_day.get(d, (0, 0))[1],
        )
        for i in range(SERIES_DAYS)
    ]
    recent = db.scalars(
        select(PrivacyRecord).order_by(PrivacyRecord.created_at.desc()).limit(RECENT)
    ).all()
    s = get_settings()
    return PrivacyOverviewOut(
        totals=TotalsOut(protected=int(protected), leaked=int(leaked), calls=int(calls)),
        by_type=_by_type(db),
        series=series,
        recent=[
            RecentRecord(
                id=str(r.id),
                created_at=r.created_at.isoformat(),
                source=r.source,
                node=r.node,
                model=r.model,
                sent=r.sent,
                protected=r.protected,
                leaked=r.leaked,
                by_type=dict(r.masked_by_type or {}),
                masked_payload=r.masked_payload[:RECENT_PAYLOAD_CHARS],
            )
            for r in recent
        ],
        trace=_trace(db),
        config=PrivacyConfigOut(enabled=s.privacy_enabled, mask_amounts=s.privacy_mask_amounts),
    )


def _trace(db: Session) -> TraceOut:
    """A recent chat run to open in LangSmith: its inputs and outputs there are the masked ones."""
    run_id = db.scalar(
        select(PrivacyRecord.run_id)
        .where(PrivacyRecord.source == "chat", PrivacyRecord.run_id.is_not(None))
        .order_by(PrivacyRecord.created_at.desc())
        .limit(1)
    )
    if not tracing.tracing_enabled():
        return TraceOut(
            enabled=False,
            url=None,
            run_id=run_id,
            note="LangSmith tracing is off in this environment (LANGSMITH_TRACING).",
        )
    url = tracing.run_url(uuid.UUID(run_id)) if run_id else None
    note = (
        "Open the run: every input and output shows tokens such as ⟦ACCT_1⟧, never real values."
        if url
        else "No traced chat run yet. Ask the assistant something, then reload."
    )
    return TraceOut(enabled=True, url=url, run_id=run_id, note=note)
