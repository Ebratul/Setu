"""Schema-per-sandbox tenancy. A judge sandbox is one Postgres schema holding a full copy of the
demo tables; every pooled connection gets `search_path = <schema>, public` for the request's
sandbox, so services and SQL never need a tenant column. Shared tables (kb_chunks, llm_cache,
demo_sandboxes) are not copied and resolve to `public` through the fallback."""

import re
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

SCHEMA_RE = re.compile(r"^sbx_[0-9a-f]{12}$")
PUBLIC_ONLY = frozenset({"kb_chunks", "llm_cache", "demo_sandboxes"})

_schema: ContextVar[str | None] = ContextVar("setu_schema", default=None)


def current_schema() -> str | None:
    return _schema.get()


@contextmanager
def use_schema(schema: str | None) -> Iterator[None]:
    if schema is not None and not SCHEMA_RE.match(schema):
        raise ValueError("invalid sandbox schema name")
    token = _schema.set(schema)
    try:
        yield
    finally:
        _schema.reset(token)


def lock_key(base: int) -> int:
    """Advisory-lock key made per schema, so two sandboxes never wait for each other."""
    schema = _schema.get()
    return base if schema is None else (base ^ zlib.crc32(schema.encode())) & 0x7FFFFFFF


class SchemaMissing(RuntimeError):
    """The sandbox schema is gone (reset, expiry): never fall back to the shared tables."""


def _on_checkout(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    want = _schema.get()
    if want is None and record.info.get("setu_schema") is None:
        return
    with dbapi_connection.cursor() as cur:
        if want is None:
            cur.execute("RESET search_path")
        else:
            # A schema missing from search_path is skipped silently by Postgres, and unqualified
            # names would then land in `public`: check on every checkout, fail closed.
            cur.execute("SELECT to_regnamespace(%s) IS NOT NULL", (f'"{want}"',))
            row = cur.fetchone()
            if not row or not row[0]:
                dbapi_connection.rollback()
                record.info["setu_schema"] = None
                raise SchemaMissing(want)
            cur.execute(f'SET search_path TO "{want}", public')
    dbapi_connection.commit()  # a later rollback must not undo the setting
    record.info["setu_schema"] = want


def install(engine: Engine) -> None:
    if not event.contains(engine, "checkout", _on_checkout):
        event.listen(engine, "checkout", _on_checkout)
