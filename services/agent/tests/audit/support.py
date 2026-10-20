"""Helpers shared by the audit tests."""

import re
from collections.abc import Iterator
from typing import Any

from app.privacy.detectors import detect

# Digests and UUIDs are deliberately kept verbatim by the masker; their digit runs are not PII.
SAFE_TOKEN = re.compile(
    r"^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-f]{32,128})$"
)


def string_leaves(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from string_leaves(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from string_leaves(v, f"{path}[{i}]")


def pii_hits(lines: list[dict[str, Any]]) -> list[tuple[int, str, str, str]]:
    """(seq, path, type, text) of every identifier the P18 detectors still find in a payload."""
    found = []
    for ln in lines:
        for path, text in string_leaves(ln["payload"]):
            if SAFE_TOKEN.match(text):
                continue
            for h in detect(text, mask_amounts=False):
                found.append((ln["seq"], path, h.type, text[h.start : h.end]))
    return found


def has_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(has_float(v) for v in value.values())
    if isinstance(value, list):
        return any(has_float(v) for v in value)
    return False
