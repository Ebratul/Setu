"""The single ordered audit writer.

`write_audit` appends one signed, chained row inside the caller's transaction (the caller
commits). A transaction-scoped advisory lock makes seq and prev_hash strictly sequential: the
second writer waits until the first commits, then reads the new chain head.
"""

import contextvars
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.audit.keys import key_id, load_signing_key, sign_hash
from app.audit.mask import clean_payload
from app.audit.scheme import (
    GENESIS_HASH,
    compute_entry_hash,
    compute_payload_hash,
    fmt_ts,
)
from app.db import tenancy

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

AUDIT_LOCK_KEY = 5_400_001
_log = structlog.get_logger("setu.audit")

# Set per request by the auth middleware, so call sites need not pass the acting user.
current_actor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audit_actor_id", default=None
)


@dataclass(frozen=True, slots=True)
class PendingEntry:
    ts: datetime
    actor_type: str
    actor_id: str
    deal_id: uuid.UUID | None
    action: str
    tier: int
    decision: str
    payload: dict[str, Any]


def default_actor_id(actor_type: str) -> str:
    explicit = current_actor_id.get()
    if actor_type == "user":
        return explicit or "anonymous"
    return "agent" if actor_type == "llm" else "system"


def _deal_from(payload: dict[str, Any]) -> uuid.UUID | None:
    raw = payload.get("deal_id")
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def sign_entry(
    key: Ed25519PrivateKey, entry: PendingEntry, seq: int, prev_hash: str
) -> dict[str, Any]:
    """Row values (DB column names) of one signed entry."""
    ts = entry.ts.astimezone(UTC)
    body = {
        "seq": seq,
        "ts": fmt_ts(ts),
        "actor_type": entry.actor_type,
        "actor_id": entry.actor_id,
        "deal_id": str(entry.deal_id) if entry.deal_id else None,
        "action": entry.action,
        "tier": entry.tier,
        "decision": entry.decision,
        "payload": entry.payload,
    }
    p_hash = compute_payload_hash(body)
    digest = compute_entry_hash(prev_hash, p_hash, seq, body["ts"])
    return {
        "seq": seq,
        "ts": ts,
        "actor": entry.actor_type,
        "actor_id": entry.actor_id,
        "deal_id": entry.deal_id,
        "action": entry.action,
        "tier": entry.tier,
        "decision": entry.decision,
        "payload": entry.payload,
        "payload_hash": p_hash,
        "prev_hash": prev_hash,
        "entry_hash": digest,
        "signature": sign_hash(key, digest),
        "key_id": key_id(key.public_key()),
    }


def build_chain(
    key: Ed25519PrivateKey,
    entries: Sequence[PendingEntry],
    *,
    start_seq: int = 1,
    prev_hash: str = GENESIS_HASH,
) -> list[dict[str, Any]]:
    """Sign a run of entries as a chain (seed history, tests). Payloads must already be clean."""
    rows: list[dict[str, Any]] = []
    for offset, entry in enumerate(entries):
        row = sign_entry(key, entry, start_seq + offset, prev_hash)
        rows.append(row)
        prev_hash = row["entry_hash"]
    return rows


def write_audit(
    db: "Session",
    *,
    actor: str,
    action: str,
    tier: int,
    params: dict[str, Any],
    result: str,
    ts: datetime | None = None,
    deal_id: uuid.UUID | None = None,
    actor_id: str | None = None,
) -> int:
    """Append one entry and return its seq. `params` is the payload (masked here), `result` the
    decision. No signing key means no row: the audit trail is never unsigned."""
    from sqlalchemy import select, text

    from app.db.enums import Actor
    from app.db.models import AuditLog
    from app.errors import ServiceUnavailable

    try:
        key = load_signing_key()
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise ServiceUnavailable("the audit signing key is not available") from exc
    actor_type = Actor(actor).value
    payload = clean_payload(params)
    entry = PendingEntry(
        ts=ts or datetime.now(UTC),  # replaced after the lock when not given
        actor_type=actor_type,
        actor_id=actor_id or default_actor_id(actor_type),
        deal_id=deal_id or _deal_from(payload),
        action=action[:64],
        tier=tier,
        decision=result[:64],
        payload=payload,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": tenancy.lock_key(AUDIT_LOCK_KEY)})
    head = db.execute(
        select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
    ).first()
    seq, prev = (head[0] + 1, head[1]) if head else (1, GENESIS_HASH)
    if ts is None:  # time of signing, so ts never runs backwards with seq
        entry = replace(entry, ts=datetime.now(UTC))
    row = sign_entry(key, entry, seq, prev)
    db.add(AuditLog(**{**row, "actor": Actor(actor_type)}))
    db.flush()
    _log.info("audit_appended", seq=seq, action=action, tier=tier, decision=result)
    return seq
