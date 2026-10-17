"""write_audit: concurrent appenders keep one linear signed chain; no key means no row."""

import threading
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session as db_session
from app.db.models import AuditLog
from app.errors import ServiceUnavailable
from app.security.audit import AuditFields, SignedEntry, load_signing_key, verify_chain, write_audit

pytestmark = pytest.mark.db


def chain(s: Session) -> list[SignedEntry]:
    return [
        SignedEntry(
            AuditFields(
                r.seq, r.ts, r.actor.value, r.action, r.tier, r.params_hash, r.result, r.prev_hash
            ),
            r.entry_hash,
            r.signature,
            r.key_id,
        )
        for r in s.scalars(select(AuditLog).order_by(AuditLog.seq)).all()
    ]


def test_concurrent_appends_are_contiguous_and_the_chain_verifies(migrated_db: str) -> None:
    engine = db_session.get_engine()
    errors: list[BaseException] = []
    per_thread, threads_n = 6, 3

    def worker(n: int) -> None:
        try:
            for i in range(per_thread):
                with Session(engine) as s:
                    write_audit(
                        s,
                        actor="system",
                        action="TEST",
                        tier=0,
                        params={"t": n, "i": i},
                        result="OK",
                    )
                    time.sleep(0.01)  # hold the lock so the others really queue
                    s.commit()
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(threads_n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    with Session(engine) as s:
        entries = chain(s)
    assert [e.fields.seq for e in entries] == list(range(1, per_thread * threads_n + 1))
    assert verify_chain(load_signing_key().public_key(), entries) == []


def test_missing_signing_key_raises_and_leaves_no_row(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from app.security import audit

    no_key = get_settings().model_copy(
        update={"audit_signing_key": None, "audit_dev_key_path": tmp_path / "nope.key"}
    )
    monkeypatch.setattr(audit, "get_settings", lambda: no_key)
    with Session(db_session.get_engine()) as s:
        with pytest.raises(ServiceUnavailable):
            write_audit(
                s,
                actor="system",
                action="TEST",
                tier=0,
                params={},
                result="OK",
                ts=datetime.now(UTC),
            )
        s.rollback()
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 0
