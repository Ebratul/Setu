"""Seed + verification against a real Postgres (separate *_test database)."""

from datetime import date

import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db.base import Base
from app.db.enums import ApprovalStatus
from app.db.models import ApprovalRequest, AuditLog
from app.db.session import batch_session, get_batch_engine
from seed.cli import SeedError, seed
from seed.common import Ctx
from seed.verify import run_checks, snapshot

pytestmark = pytest.mark.db


def test_migration_creates_every_model_table(migrated_db: str) -> None:
    tables = set(inspect(get_batch_engine()).get_table_names())
    assert set(Base.metadata.tables) <= tables


def test_seed_twice_is_idempotent_and_all_checks_pass(migrated_db: str) -> None:
    seed()
    with batch_session() as s:
        first = snapshot(s)
    seed()
    with batch_session() as s:
        second = snapshot(s)
        checks = run_checks(s)
    assert first == second
    failed = [f"{c.name}: expected {c.expected}, got {c.actual}" for c in checks if not c.ok]
    assert failed == []


def test_reset_demo_restores_canonical_rows(migrated_db: str) -> None:
    seed()
    with batch_session() as s:
        before = {t: n for t, (n, _) in snapshot(s).items()}
    seed(reset=True)
    with batch_session() as s:
        after = {t: n for t, (n, _) in snapshot(s).items()}
    assert before == after


def test_reseed_never_rewrites_decided_approvals_or_audit(migrated_db: str) -> None:
    seed()
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.tier == 2)
            .values(status=ApprovalStatus.APPROVED)
        )
        audit_before = s.execute(select(AuditLog.seq, AuditLog.entry_hash)).all()
    seed()
    with batch_session() as s:
        status = s.scalar(select(ApprovalRequest.status).where(ApprovalRequest.tier == 2))
        audit_after = s.execute(select(AuditLog.seq, AuditLog.entry_hash)).all()
    assert status == ApprovalStatus.APPROVED
    assert sorted(audit_before) == sorted(audit_after)


def test_changed_anchor_requires_explicit_reset(migrated_db: str) -> None:
    seed()
    with pytest.raises(SeedError, match="reset-demo"):
        seed(Ctx(today=date(2027, 1, 5)))
    seed(Ctx(today=date(2027, 1, 5)), reset=True)


def test_db_rejects_tier3_without_step_up(migrated_db: str) -> None:
    seed()
    with pytest.raises(IntegrityError), batch_session() as s:
        s.execute(
            update(ApprovalRequest).where(ApprovalRequest.tier == 3).values(cooling_off_until=None)
        )


def test_reset_refuses_remote_database(monkeypatch: pytest.MonkeyPatch, audit_key: None) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/neondb")
    get_settings.cache_clear()
    try:
        with pytest.raises(SeedError, match="non-local"):
            seed(reset=True)
    finally:
        get_settings.cache_clear()
