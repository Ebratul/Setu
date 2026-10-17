"""Hash-chained, Ed25519-signed audit entries (SR-5).

entry_hash = sha256(canonical_json(entry_without_sig_and_hash) + prev_hash)
signature  = Ed25519(bytes.fromhex(entry_hash)), hex-encoded

Phase 5.4 adds the append service, /audit/verify and JSONL export on top of these primitives.
"""

import base64
import binascii
import hashlib
import json
import os
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

GENESIS_HASH = "0" * 64


def _default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"not canonicalisable: {type(value).__name__}")


def canonical_json(data: Any) -> str:
    """Sorted keys, no whitespace, Decimal/datetime as strings."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default
    )


def sha256_hex(text: str | bytes) -> str:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(raw).hexdigest()


def params_hash(params: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(params))


@dataclass(frozen=True, slots=True)
class AuditFields:
    seq: int
    ts: datetime
    actor: str
    action: str
    tier: int
    params_hash: str
    result: str
    prev_hash: str

    def as_dict(self) -> dict[str, Any]:
        if self.ts.tzinfo is None:
            raise ValueError("audit ts must be timezone-aware")
        return {
            "seq": self.seq,
            "ts": self.ts.astimezone(UTC).isoformat(),  # canonical: UTC, whatever the DB session TZ
            "actor": self.actor,
            "action": self.action,
            "tier": self.tier,
            "params_hash": self.params_hash,
            "result": self.result,
            "prev_hash": self.prev_hash,
        }


def compute_entry_hash(fields: AuditFields) -> str:
    return sha256_hex(canonical_json(fields.as_dict()) + fields.prev_hash)


def _parse_seed(value: str) -> bytes:
    value = value.strip()
    try:
        raw = bytes.fromhex(value)
        if len(raw) == 32:
            return raw
    except ValueError:
        pass
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("audit signing key must be 32 bytes as hex or base64") from exc
    if len(raw) != 32:
        raise ValueError("audit signing key must be 32 bytes as hex or base64")
    return raw


def load_signing_key(*, create_dev_key: bool = False) -> Ed25519PrivateKey:
    """AUDIT_SIGNING_KEY from env if set; otherwise the git-ignored dev key file (keys/),
    generated on first use when `create_dev_key` is True (seed time)."""
    settings = get_settings()
    if settings.audit_signing_key is not None:
        seed = _parse_seed(settings.audit_signing_key.get_secret_value())
        return Ed25519PrivateKey.from_private_bytes(seed)
    path: Path = settings.audit_dev_key_path
    if not path.exists():
        if not create_dev_key:
            raise FileNotFoundError(
                f"no audit signing key: set AUDIT_SIGNING_KEY or run the seed ({path})"
            )
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        seed_bytes = os.urandom(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(base64.b64encode(seed_bytes).decode("ascii") + "\n")
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"{path} must not be readable by group/others (chmod 600)")
    return Ed25519PrivateKey.from_private_bytes(_parse_seed(path.read_text()))


def key_id(public_key: Ed25519PublicKey) -> str:
    return sha256_hex(public_key.public_bytes(Encoding.Raw, PublicFormat.Raw))[:16]


def sign_hash(private_key: Ed25519PrivateKey, digest_hex: str) -> str:
    return private_key.sign(bytes.fromhex(digest_hex)).hex()


def verify_signature(public_key: Ed25519PublicKey, digest_hex: str, signature_hex: str) -> bool:
    try:
        public_key.verify(bytes.fromhex(signature_hex), bytes.fromhex(digest_hex))
    except Exception:
        return False
    return True


@dataclass(frozen=True, slots=True)
class SignedEntry:
    fields: AuditFields
    entry_hash: str
    signature: str
    key_id: str


def build_chain(
    private_key: Ed25519PrivateKey,
    entries: list[tuple[datetime, str, str, int, str, str]],
    *,
    start_seq: int = 1,
    prev_hash: str = GENESIS_HASH,
) -> list[SignedEntry]:
    """Sign a run of (ts, actor, action, tier, params_hash, result) tuples as a chain."""
    kid = key_id(private_key.public_key())
    out: list[SignedEntry] = []
    for offset, (ts, actor, action, tier, p_hash, result) in enumerate(entries):
        fields = AuditFields(start_seq + offset, ts, actor, action, tier, p_hash, result, prev_hash)
        digest = compute_entry_hash(fields)
        out.append(SignedEntry(fields, digest, sign_hash(private_key, digest), kid))
        prev_hash = digest
    return out


def verify_chain(public_key: Ed25519PublicKey, entries: list[SignedEntry]) -> list[str]:
    """Return a list of problems (empty == valid). Entries must be ordered by seq."""
    problems: list[str] = []
    prev = GENESIS_HASH
    for expected_seq, e in enumerate(entries, start=entries[0].fields.seq if entries else 1):
        if e.fields.seq != expected_seq:
            problems.append(f"seq {e.fields.seq}: expected seq {expected_seq} (gap or reorder)")
        if e.fields.prev_hash != prev:
            problems.append(f"seq {e.fields.seq}: prev_hash does not link")
        if compute_entry_hash(e.fields) != e.entry_hash:
            problems.append(f"seq {e.fields.seq}: entry_hash mismatch")
        if not verify_signature(public_key, e.entry_hash, e.signature):
            problems.append(f"seq {e.fields.seq}: bad signature")
        prev = e.entry_hash
    return problems


# --- Agent action seam ---------------------------------------------------------------------
# TODO(5.4): append a signed, hash-chained `audit_log` entry here. Until then agent actions are
# logged as structured events (ids and hashes only, never raw text or PII).
_audit_log = structlog.get_logger("setu.audit")
RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=500)


def record_event(
    *,
    actor: str,
    action: str,
    tier: int,
    params: dict[str, Any],
    result: str,
    refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    event = {
        "ts": datetime.now(UTC).isoformat(),
        "actor": actor,
        "action": action,
        "tier": tier,
        "params_hash": params_hash(params),
        "result": result,
        **(refs or {}),
    }
    RECENT_EVENTS.append(event)
    _audit_log.info("agent_action", **event)
    return event


# --- Append service --------------------------------------------------------------------------
AUDIT_LOCK_KEY = (
    5_400_001  # pg_advisory_xact_lock: one appender at a time keeps seq/prev_hash linear
)


def write_audit(
    db: "Session",
    *,
    actor: str,
    action: str,
    tier: int,
    params: dict[str, Any],
    result: str,
    ts: datetime | None = None,
    deal_id: "uuid.UUID | None" = None,
) -> int:
    """Append one signed, hash-chained row to `audit_log` in the caller's transaction (the caller
    commits). Returns its seq. Only ids and hashes go in: `params` is stored as its hash.
    `deal_id` is unsigned listing metadata (not part of the hash) for the per-deal activity feed.

    Takes a transaction-scoped advisory lock, reads the chain head, and signs with the audit key
    (AUDIT_SIGNING_KEY or the dev key file). Raises if no key is available: no unsigned rows.
    """
    from sqlalchemy import select, text

    from app.db.enums import Actor
    from app.db.models import AuditLog
    from app.errors import ServiceUnavailable

    try:
        key = load_signing_key()
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise ServiceUnavailable("the audit signing key is not available") from exc
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": AUDIT_LOCK_KEY})
    head = db.execute(
        select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
    ).first()
    seq, prev = (head[0] + 1, head[1]) if head else (1, GENESIS_HASH)
    fields = AuditFields(
        seq,
        ts or datetime.now(UTC),
        Actor(actor).value,
        action,
        tier,
        params_hash(params),
        result,
        prev,
    )
    digest = compute_entry_hash(fields)
    db.add(
        AuditLog(
            seq=seq,
            ts=fields.ts,
            actor=Actor(actor),
            action=action,
            tier=tier,
            params_hash=fields.params_hash,
            result=result,
            prev_hash=prev,
            entry_hash=digest,
            signature=sign_hash(key, digest),
            key_id=key_id(key.public_key()),
            deal_id=deal_id,
        )
    )
    db.flush()
    _audit_log.info("audit_appended", seq=seq, action=action, tier=tier, result=result)
    return seq
