"""Tamper demo: change, delete or reorder entries of an in-memory COPY and verify it.

Nothing here writes to the database. The copy is a list of export lines; the real table is only
read (the API opens the connection read-only).
"""

import copy
from typing import Any, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.audit.verify import Report, verify_lines

Mode = Literal["edit", "delete", "reorder"]
TOP_LEVEL_EDITABLE = ("decision", "tier", "action", "actor_id")


class TamperError(ValueError):
    pass


def _index(lines: list[dict[str, Any]], seq: int) -> int:
    for i, ln in enumerate(lines):
        if ln["seq"] == seq:
            return i
    raise TamperError(f"seq {seq} is not in the selected window")


def apply_tamper(
    lines: list[dict[str, Any]],
    *,
    mode: Mode,
    seq: int,
    field: str | None = None,
    value: str | None = None,
    other_seq: int | None = None,
) -> list[dict[str, Any]]:
    """A tampered deep copy of `lines`. `field` is a payload key, or one of TOP_LEVEL_EDITABLE."""
    out = copy.deepcopy(lines)
    i = _index(out, seq)
    if mode == "delete":
        del out[i]
    elif mode == "reorder":
        j = _index(out, other_seq if other_seq is not None else seq + 1)
        out[i], out[j] = out[j], out[i]
    else:
        if field is None or value is None:
            raise TamperError("edit needs a field and a new value")
        entry = out[i]
        if field in TOP_LEVEL_EDITABLE:
            if field == "tier":
                if not value.isdigit():
                    raise TamperError("tier must be a number")
                entry[field] = int(value)
            else:
                entry[field] = value
        else:
            entry["payload"][field] = value
    return out


def run(
    lines: list[dict[str, Any]],
    public_key: Ed25519PublicKey,
    *,
    anchor_prev_hash: str | None,
    **change: Any,
) -> tuple[list[dict[str, Any]], Report]:
    tampered = apply_tamper(lines, **change)
    return tampered, verify_lines(tampered, public_key, anchor_prev_hash=anchor_prev_hash)
