"""Make a payload safe to sign: JSON-native types only, personal identifiers redacted.

The audit log is public evidence (judges export it), so identifiers found by the Privacy Gateway
detectors are replaced with `[redacted:TYPE]` before hashing. Amounts are kept: they are what the
log proves. Unlike gateway tokens, the redaction is one-way and needs no vault.
"""

import re
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from app.audit.scheme import fmt_ts
from app.privacy.detectors import detect
from app.privacy.gateway import id_type

MAX_TEXT = 1000
MAX_DEPTH = 8
MAX_SAFE_INT = 2**53 - 1
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_TOKEN = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-f]{32,128})$"
)


def redact_text(text: str) -> str:
    """Replace detected identifiers (not amounts). UUIDs and hex digests pass untouched."""
    if _SAFE_TOKEN.match(text):
        return text
    hits = detect(text, mask_amounts=False)
    for h in reversed(hits):
        text = f"{text[: h.start]}[redacted:{h.type}]{text[h.end :]}"
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def clean(value: Any, key: str | None = None, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return "[truncated]"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if id_type(key):
            return f"[redacted:{id_type(key)}]"
        return value if abs(value) <= MAX_SAFE_INT else str(value)  # JS-safe integers only
    if isinstance(value, str):
        value = _CONTROL.sub(" ", value)
        kind = id_type(key)
        if kind and value.strip() and not _SAFE_TOKEN.match(value):
            return f"[redacted:{kind}]"
        return redact_text(value)
    if isinstance(value, float):
        return str(Decimal(repr(value)))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return fmt_ts(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return clean(value.value, key, depth)
    if isinstance(value, dict):
        return {str(k): clean(v, str(k), depth + 1) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean(v, key, depth + 1) for v in value]
    if isinstance(value, set | frozenset):
        return sorted((clean(v, key, depth + 1) for v in value), key=str)
    return redact_text(str(value))


def clean_payload(params: dict[str, Any]) -> dict[str, Any]:
    out = clean(params)
    return out if isinstance(out, dict) else {"value": out}
