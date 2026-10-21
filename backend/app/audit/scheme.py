"""Audit-log scheme `setu-audit-v2`: canonical bytes, hashes and the export line shape.

The browser verifier (frontend/src/lib/audit/verify.ts) re-implements exactly this file.

    body         = {seq, ts, actor_type, actor_id, deal_id, action, tier, decision, payload}
    payload_hash = sha256(canonical_json(body))
    entry_hash   = sha256(prev_hash "|" payload_hash "|" seq "|" ts)      (ASCII, hex digests)
    signature    = Ed25519(private_key, bytes.fromhex(entry_hash))
    prev_hash    = entry_hash of seq-1, or GENESIS_HASH for seq 1
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

SCHEME = "setu-audit-v2"
GENESIS_HASH = "0" * 64
BODY_FIELDS = (
    "seq",
    "ts",
    "actor_type",
    "actor_id",
    "deal_id",
    "action",
    "tier",
    "decision",
    "payload",
)
LINE_FIELDS = (*BODY_FIELDS, "payload_hash", "prev_hash", "entry_hash", "signature", "key_id")


def _default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"not canonicalisable: {type(value).__name__}")


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("floats are not allowed in audit payloads (use Decimal or str)")
    if isinstance(value, dict):
        for v in value.values():
            _reject_floats(v)
    elif isinstance(value, list | tuple):
        for v in value:
            _reject_floats(v)


def canonical_json(data: Any) -> str:
    """Sorted keys, UTF-8 text, no whitespace, Decimal as string. Floats are refused: their text
    differs between languages."""
    _reject_floats(data)
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fmt_ts(ts: datetime) -> str:
    """Fixed-width UTC text, microseconds: 2026-10-20T09:30:00.000000Z."""
    if ts.tzinfo is None:
        raise ValueError("audit ts must be timezone-aware")
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def body_of(line: dict[str, Any]) -> dict[str, Any]:
    return {k: line[k] for k in BODY_FIELDS}


def compute_payload_hash(body: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(body))


def compute_entry_hash(prev_hash: str, payload_hash: str, seq: int, ts: str) -> str:
    return sha256_hex(f"{prev_hash}|{payload_hash}|{seq}|{ts}")
