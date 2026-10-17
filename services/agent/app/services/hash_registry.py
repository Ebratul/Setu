"""Cross-lender hash registry seam (SR-6). Phase 14 ships a stub that always answers NEW; Phase 15
replaces `_default_check` (or calls `set_checker`) with the real lookup against `hash_registry`.

The registry answers "has this document, or this invoice identity, been financed or used
elsewhere?" across lenders. It is not the same as the in-platform duplicate rules (identical file
re-uploaded to the same or another deal), which are decided at upload and by the DUPLICATE_HASH
check against other deals of this platform.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class RegistryResult:
    status: str = "NEW"  # NEW | DUPLICATE
    detail: dict[str, Any] = field(default_factory=dict)  # ids and codes only, no document text


Checker = Callable[[Session, str, str | None, str], RegistryResult]


def _default_check(
    db: Session, sha256: str, canonical_hash: str | None, doc_type: str
) -> RegistryResult:
    return RegistryResult()


_checker: Checker = _default_check


def check(db: Session, sha256: str, canonical_hash: str | None, doc_type: str) -> RegistryResult:
    return _checker(db, sha256, canonical_hash, doc_type)


def set_checker(fn: Checker | None) -> None:
    global _checker
    _checker = fn or _default_check


@contextmanager
def use_checker(fn: Checker) -> Iterator[None]:
    previous = _checker
    set_checker(fn)
    try:
        yield
    finally:
        set_checker(previous)
