"""Hashing helpers and the structured agent-action event log.

The signed, hash-chained audit log lives in `app/audit/` (scheme, writer, verify, export).
"""

import hashlib
import json
from collections import deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog


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


# --- Agent action seam ---------------------------------------------------------------------
# Structured log events for debugging (ids and hashes only, never raw text or PII). Entries that
# must be provable go through `app.audit.write_audit` instead.
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
