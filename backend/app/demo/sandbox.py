"""Judge sandboxes: one Postgres schema per judge, cloned from the demo seed.

Create = new schema, tables from the ORM metadata, the append-only audit trigger, then the seed
(profile "demo") and a signed SANDBOX_CREATED row. Reset = drop and rebuild that one schema and
append DEMO_RESET (with the previous chain head) in the new one. A sandbox is tied to the browser by
a signed cookie, expires after SANDBOX_TTL_HOURS and a janitor drops the schema. Nothing here ever
runs an unqualified TRUNCATE: the only destructive statement is DROP SCHEMA of a validated name.
"""

import hashlib
import hmac
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.demo import _secret
from app.config import get_settings
from app.db import tenancy
from app.db.base import Base
from app.db.models import AuditLog, DemoSandbox
from app.db.session import batch_session, database_url, get_batch_engine
from app.demo.context import SandboxInfo, use_sandbox
from app.errors import Gone, ServiceUnavailable

log = structlog.get_logger("setu.demo.sandbox")

COOKIE_NAME = "setu_sandbox"
CACHE_SECONDS = 15.0
PROFILE = "demo"

_cache: dict[uuid.UUID, tuple[float, SandboxInfo | None]] = {}
_locks: dict[uuid.UUID, threading.RLock] = defaultdict(threading.RLock)
_windows: dict[tuple[uuid.UUID, str], deque[float]] = defaultdict(deque)
_guard = threading.Lock()


def now() -> datetime:
    return datetime.now(UTC)


# --- cookie ---------------------------------------------------------------------------------


def _sign(payload: str) -> str:
    return hmac.new(_secret(), f"sandbox:{payload}".encode(), hashlib.sha256).hexdigest()


def make_token(sandbox_id: uuid.UUID) -> str:
    return f"{sandbox_id}.{_sign(str(sandbox_id))}"


def parse_token(token: str) -> uuid.UUID | None:
    try:
        raw, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(raw)):
            return None
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None


# --- registry (always in `public`) ----------------------------------------------------------


@contextmanager
def registry() -> Iterator[Session]:
    with tenancy.use_schema(None), batch_session() as db:
        yield db


def _info(row: DemoSandbox) -> SandboxInfo:
    return SandboxInfo(row.id, row.schema_name, row.live_ai, row.expires_at)


def invalidate(sandbox_id: uuid.UUID) -> None:
    _cache.pop(sandbox_id, None)


def lookup(sandbox_id: uuid.UUID) -> SandboxInfo | None:
    """The live sandbox for an id, or None (unknown, expired, deleted). Cached a few seconds."""
    hit = _cache.get(sandbox_id)
    if hit is not None and time.monotonic() - hit[0] < CACHE_SECONDS:
        info = hit[1]
        return info if info is None or info.expires_at > now() else None
    with registry() as db:
        row = db.get(DemoSandbox, sandbox_id)
        info = _info(row) if row and row.status == "ACTIVE" and row.expires_at > now() else None
    _cache[sandbox_id] = (time.monotonic(), info)
    return info


def get_row(db: Session, sandbox_id: uuid.UUID) -> DemoSandbox:
    row = db.get(DemoSandbox, sandbox_id)
    if row is None or row.status != "ACTIVE" or row.expires_at <= now():
        raise Gone("this sandbox has expired; start a new one", "SANDBOX_EXPIRED")
    return row


def sandbox_lock(sandbox_id: uuid.UUID) -> threading.RLock:
    return _locks[sandbox_id]


# --- schema lifecycle -----------------------------------------------------------------------


def _require_schema(schema: str) -> str:
    if not tenancy.SCHEMA_RE.match(schema):
        raise ValueError("invalid sandbox schema name")
    return schema


CHECKPOINT_TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


def _purge_checkpoints(schema: str) -> None:
    """The LangGraph checkpointer keeps its (masked) conversation state in `public`, keyed by
    "<schema>:<thread id>". Forget the threads of a sandbox that is going away. Best effort."""
    try:
        with tenancy.use_schema(None), get_batch_engine().begin() as conn:
            for table in CHECKPOINT_TABLES:  # keys are "<schema>:<thread id>" (checkpoint_key)
                conn.execute(
                    text(f"DELETE FROM {table} WHERE thread_id LIKE :p"), {"p": f"{schema}:%"}
                )
    except Exception as exc:  # the schema may not exist yet, or the tables may be absent
        log.info("checkpoint_purge_skipped", error=type(exc).__name__)


def _drop_schema(schema: str) -> None:
    _require_schema(schema)
    _purge_checkpoints(schema)
    with tenancy.use_schema(None), get_batch_engine().begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _build_schema(schema: str, *, previous_head: tuple[int, str] | None = None) -> int:
    """Create the schema, its tables, the audit trigger and the demo-profile seed. Returns rows."""
    _require_schema(schema)
    with tenancy.use_schema(None), get_batch_engine().begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))  # fails if it exists: never drop another's
    try:
        return _populate(schema, previous_head)
    except Exception:
        _drop_schema(schema)
        raise


def _populate(schema: str, previous_head: tuple[int, str] | None) -> int:
    from seed.cli import seed
    from seed.common import default_ctx

    with tenancy.use_schema(schema):
        with get_batch_engine().begin() as conn:
            tables = [t for t in Base.metadata.sorted_tables if t.name not in tenancy.PUBLIC_ONLY]
            Base.metadata.create_all(conn, tables=tables, checkfirst=False)
            conn.execute(
                text(
                    "CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE "
                    "ON audit_log FOR EACH ROW EXECUTE FUNCTION public.audit_log_append_only()"
                )
            )
        ctx = default_ctx(PROFILE)
        counts = seed(ctx)
        rows = sum(counts.values())
        with batch_session() as db:
            params: dict[str, Any] = {"anchor_date": ctx.today.isoformat(), "rows": rows}
            if previous_head is not None:
                params["previous_head_seq"], params["previous_head_hash"] = previous_head
            write_audit(
                db,
                actor="system",
                action="DEMO_RESET" if previous_head is not None else "SANDBOX_CREATED",
                tier=0,
                params=params,
                result="OK",
            )
    return rows


def create_sandbox() -> DemoSandbox:
    settings = get_settings()
    if not settings.sandboxes_enabled:
        raise ServiceUnavailable("judge sandboxes are switched off on this server")
    if "-pooler" in (make_url(database_url()).host or ""):
        # a session-level search_path is not safe behind a transaction pooler
        raise ServiceUnavailable(
            "sandboxes need a direct (not pooled) database connection", "SANDBOX_POOLER"
        )
    cleanup_expired()
    with registry() as db:
        active = db.scalar(
            select(func.count()).select_from(DemoSandbox).where(DemoSandbox.status == "ACTIVE")
        )
    if (active or 0) >= settings.sandbox_max_active:
        raise ServiceUnavailable(
            "all judge sandboxes are in use right now; try again in a few minutes",
            "SANDBOX_CAPACITY",
        )
    sandbox_id = uuid.uuid4()
    schema = f"sbx_{sandbox_id.hex[:12]}"
    started = time.monotonic()
    rows = _build_schema(schema)
    with registry() as db:
        row = DemoSandbox(
            id=sandbox_id,
            schema_name=schema,
            status="ACTIVE",
            created_at=now(),
            expires_at=now() + timedelta(hours=settings.sandbox_ttl_hours),
            last_seen_at=now(),
            run_state={},
        )
        db.add(row)
        db.flush()
        db.expunge(row)
    log.info(
        "sandbox_created", schema=schema, rows=rows, seconds=round(time.monotonic() - started, 2)
    )
    return row


def reset_sandbox(sandbox_id: uuid.UUID) -> DemoSandbox:
    """Rebuild this sandbox from the seed (threads, approvals, notifications and run state go).
    The copy is built in a NEW schema and swapped in, so a request never meets a half-built or
    missing schema; DEMO_RESET (with the previous chain head) is the first row of the new chain."""
    with sandbox_lock(sandbox_id):
        with registry() as db:
            old = get_row(db, sandbox_id).schema_name
        head: tuple[int, str] = (0, "")
        with tenancy.use_schema(old), batch_session() as db:
            found = db.execute(
                select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
            ).first()
            if found:
                head = (found[0], found[1])
        new = f"sbx_{uuid.uuid4().hex[:12]}"
        _build_schema(new, previous_head=head)
        with registry() as db:
            row = get_row(db, sandbox_id)
            row.schema_name = new
            row.run_state = {}
            row.resets += 1
            row.live_ai = False  # the live-AI budget (llm_calls) is never given back by a reset
            db.flush()
            db.expunge(row)
        invalidate(sandbox_id)
        _drop_schema(old)
        return row


def delete_sandbox(sandbox_id: uuid.UUID) -> None:
    with sandbox_lock(sandbox_id):
        with registry() as db:
            row = db.get(DemoSandbox, sandbox_id)
            if row is None:
                return
            schema = row.schema_name
            row.status = "DELETED"
        _drop_schema(schema)
        invalidate(sandbox_id)


def cleanup_expired() -> int:
    """Drop the schema of every expired sandbox and forget rows a day after they ended."""
    dropped = 0
    with registry() as db:
        due = db.execute(
            select(DemoSandbox.id, DemoSandbox.schema_name).where(
                DemoSandbox.status == "ACTIVE", DemoSandbox.expires_at <= now()
            )
        ).all()
    for sandbox_id, schema in due:
        try:
            _drop_schema(schema)
        except Exception as exc:  # keep going: one stuck schema must not stop the janitor
            log.error("sandbox_cleanup_failed", schema=schema, error=type(exc).__name__)
            continue
        with registry() as db:
            row = db.get(DemoSandbox, sandbox_id)
            if row is not None:
                row.status = "EXPIRED"
        invalidate(sandbox_id)
        dropped += 1
    with registry() as db:
        old = now() - timedelta(days=1)
        for row in db.scalars(
            select(DemoSandbox).where(DemoSandbox.status != "ACTIVE", DemoSandbox.expires_at < old)
        ).all():
            db.delete(row)
    if dropped:
        log.info("sandbox_cleanup", dropped=dropped)
    return dropped


@contextmanager
def acting_in(sandbox_id: uuid.UUID) -> Iterator[SandboxInfo]:
    """Run service code inside a sandbox from outside a request (orchestrator, CLI, tests)."""
    info = lookup(sandbox_id)
    if info is None:
        raise Gone("this sandbox has expired; start a new one", "SANDBOX_EXPIRED")
    with use_sandbox(info):
        yield info


# --- run state, live AI, budgets ------------------------------------------------------------


def load_state(sandbox_id: uuid.UUID) -> dict[str, Any]:
    with registry() as db:
        return dict(get_row(db, sandbox_id).run_state or {})


def save_state(sandbox_id: uuid.UUID, state: dict[str, Any]) -> None:
    with registry() as db:
        get_row(db, sandbox_id).run_state = state


def set_live_ai(sandbox_id: uuid.UUID, enabled: bool) -> DemoSandbox:
    with registry() as db:
        row = get_row(db, sandbox_id)
        row.live_ai = enabled
        db.flush()
        db.expunge(row)
    invalidate(sandbox_id)
    return row


def live_ai_budget_left(row: DemoSandbox) -> int:
    return max(0, get_settings().sandbox_live_ai_budget - row.llm_calls)


def spend_live_call(sandbox_id: uuid.UUID) -> bool:
    """Count one live model call atomically; False (and live mode off) once the budget is used."""
    budget = get_settings().sandbox_live_ai_budget
    with registry() as db:
        got = db.execute(
            update(DemoSandbox)
            .where(DemoSandbox.id == sandbox_id, DemoSandbox.llm_calls < budget)
            .values(llm_calls=DemoSandbox.llm_calls + 1)
            .returning(DemoSandbox.llm_calls)
        ).first()
        if got is None or got[0] >= budget:
            db.execute(
                update(DemoSandbox).where(DemoSandbox.id == sandbox_id).values(live_ai=False)
            )
            invalidate(sandbox_id)
        return got is not None


def touch(sandbox_id: uuid.UUID) -> None:
    with registry() as db:
        row = db.get(DemoSandbox, sandbox_id)
        if row is not None:
            row.last_seen_at = now()


# --- rate limits ----------------------------------------------------------------------------


def bucket_of(method: str, path: str) -> tuple[str, int]:
    settings = get_settings()
    if method == "POST" and path == "/demo/run/reset":
        return "reset", 3
    if method == "POST" and path.startswith("/demo/run/"):
        return "run", 60
    if method == "POST" and path.startswith("/chat"):
        return "chat", settings.sandbox_chat_per_minute
    if method == "POST" and path.startswith("/deals/") and path.endswith("/documents"):
        return "upload", settings.sandbox_upload_per_minute
    return "all", settings.sandbox_requests_per_minute


_creates: dict[str, deque[float]] = defaultdict(deque)


def allow_create(client_id: str) -> float | None:
    """A caller may start only a few sandboxes per hour (guards against filling them all)."""
    limit = get_settings().sandbox_creates_per_hour_per_ip
    t = time.monotonic()
    with _guard:
        window = _creates[client_id]
        while window and t - window[0] > 3600:
            window.popleft()
        if len(window) >= limit:
            return max(1.0, 3600 - (t - window[0]))
        window.append(t)
        if len(_creates) > 5000:  # forget idle callers
            for key in [k for k, w in _creates.items() if not w or t - w[-1] > 3600]:
                _creates.pop(key, None)
    return None


def allow(sandbox_id: uuid.UUID, method: str, path: str) -> float | None:
    """None when the request may go ahead, else the seconds to wait (sliding one-minute window)."""
    bucket, limit = bucket_of(method, path)
    t = time.monotonic()
    with _guard:
        window = _windows[(sandbox_id, bucket)]
        while window and t - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return max(1.0, 60 - (t - window[0]))
        window.append(t)
    return None
