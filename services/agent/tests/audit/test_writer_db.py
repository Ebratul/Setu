"""The single audit writer against real Postgres: ordering under concurrency, append-only trigger,
no-key refusal and actor/deal defaults."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.audit import keys
from app.audit.export import line_of
from app.audit.keys import load_signing_key
from app.audit.verify import verify_lines
from app.audit.writer import write_audit
from app.config import get_settings
from app.db.models import AuditLog
from app.db.session import batch_session
from app.errors import ServiceUnavailable

pytestmark = pytest.mark.db


def _write(i: int) -> int:
    with batch_session() as s:
        return write_audit(
            s,
            actor="system",
            action="TEST_PARALLEL",
            tier=0,
            params={"n": i, "amount": "12.50"},
            result="OK",
        )


def _all_lines() -> list[dict]:
    with batch_session() as s:
        return [line_of(r) for r in s.scalars(select(AuditLog).order_by(AuditLog.seq))]


def test_twenty_parallel_writers_get_contiguous_seq_and_a_verifying_chain(migrated_db: str) -> None:
    with ThreadPoolExecutor(max_workers=20) as pool:
        returned = list(pool.map(_write, range(20)))
    lines = _all_lines()
    assert [ln["seq"] for ln in lines] == list(range(1, 21))
    assert sorted(returned) == list(range(1, 21))
    assert sorted(ln["payload"]["n"] for ln in lines) == list(range(20))
    report = verify_lines(lines, load_signing_key().public_key())
    assert report.ok, report.detail
    assert report.anchored and report.entries_checked == 20


def _one_row() -> int:
    with batch_session() as s:
        return write_audit(
            s, actor="system", action="TEST_ROW", tier=0, params={"a": "1"}, result="OK"
        )


def test_update_on_audit_log_is_refused_by_the_trigger_and_the_row_is_unchanged(
    migrated_db: str,
) -> None:
    seq = _one_row()
    before = _all_lines()
    with pytest.raises(DBAPIError), batch_session() as s:
        s.execute(text("UPDATE audit_log SET decision = 'HACKED' WHERE seq = :s"), {"s": seq})
    assert _all_lines() == before


def test_delete_on_audit_log_is_refused_by_the_trigger_and_the_row_survives(
    migrated_db: str,
) -> None:
    seq = _one_row()
    before = _all_lines()
    with pytest.raises(DBAPIError), batch_session() as s:
        s.execute(text("DELETE FROM audit_log WHERE seq = :s"), {"s": seq})
    assert _all_lines() == before


def test_insert_still_works_after_a_refused_update(migrated_db: str) -> None:
    first = _one_row()
    with pytest.raises(DBAPIError), batch_session() as s:
        s.execute(text("UPDATE audit_log SET tier = 3"))
    second = _one_row()
    assert second == first + 1
    assert verify_lines(_all_lines(), load_signing_key().public_key()).ok


def test_no_signing_key_raises_service_unavailable_and_writes_no_row(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_key = get_settings().model_copy(
        update={"audit_signing_key": None, "audit_dev_key_path": tmp_path / "missing.key"}
    )
    monkeypatch.setattr(keys, "get_settings", lambda: no_key)
    with pytest.raises(ServiceUnavailable), batch_session() as s:
        write_audit(s, actor="system", action="TEST_NOKEY", tier=0, params={}, result="OK")
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 0
    assert not (tmp_path / "missing.key").exists()


@pytest.mark.parametrize(
    ("actor", "expected"), [("system", "system"), ("llm", "agent")], ids=["system", "llm"]
)
def test_actor_id_defaults_by_actor_type(migrated_db: str, actor: str, expected: str) -> None:
    with batch_session() as s:
        seq = write_audit(s, actor=actor, action="TEST_ACTOR", tier=0, params={}, result="OK")
        assert s.get(AuditLog, seq).actor_id == expected  # type: ignore[union-attr]


def test_user_actor_without_a_request_context_is_anonymous(migrated_db: str) -> None:
    with batch_session() as s:
        seq = write_audit(s, actor="user", action="TEST_ACTOR", tier=0, params={}, result="OK")
        assert s.get(AuditLog, seq).actor_id == "anonymous"  # type: ignore[union-attr]


def test_explicit_actor_id_wins_over_the_default(migrated_db: str) -> None:
    with batch_session() as s:
        seq = write_audit(
            s, actor="llm", action="TEST_ACTOR", tier=0, params={}, result="OK", actor_id="bot-7"
        )
        assert s.get(AuditLog, seq).actor_id == "bot-7"  # type: ignore[union-attr]


def test_deal_id_is_derived_from_the_payload_when_not_passed(migrated_db: str) -> None:
    did = uuid.uuid4()
    with batch_session() as s:
        seq = write_audit(
            s, actor="system", action="T", tier=0, params={"deal_id": str(did)}, result="OK"
        )
        assert s.get(AuditLog, seq).deal_id == did  # type: ignore[union-attr]


def test_explicit_deal_id_beats_the_payload_and_junk_payload_deal_id_is_ignored(
    migrated_db: str,
) -> None:
    explicit, other = uuid.uuid4(), uuid.uuid4()
    with batch_session() as s:
        a = write_audit(
            s, actor="system", action="T", tier=0, params={"deal_id": str(other)},
            result="OK", deal_id=explicit,
        )  # fmt: skip
        b = write_audit(
            s, actor="system", action="T", tier=0, params={"deal_id": "not-a-uuid"}, result="OK"
        )
        assert s.get(AuditLog, a).deal_id == explicit  # type: ignore[union-attr]
        assert s.get(AuditLog, b).deal_id is None  # type: ignore[union-attr]
