"""Who the current request is a sandbox for. Set by the sandbox middleware (and by the guided-demo
runner when it acts on a sandbox) and read by the LLM layer to choose replay or live."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.db import tenancy


@dataclass(frozen=True, slots=True)
class SandboxInfo:
    id: UUID
    schema: str
    live_ai: bool
    expires_at: datetime


_current: ContextVar[SandboxInfo | None] = ContextVar("setu_sandbox", default=None)


def current_sandbox() -> SandboxInfo | None:
    return _current.get()


@contextmanager
def use_sandbox(info: SandboxInfo | None) -> Iterator[None]:
    token = _current.set(info)
    try:
        with tenancy.use_schema(info.schema if info else None):
            yield
    finally:
        _current.reset(token)
