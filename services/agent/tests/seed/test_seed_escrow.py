"""The seeded deals satisfy the escrow invariant and carry the P13 columns."""

import pytest
from sqlalchemy import func, select

from app.db.enums import EvidenceStatus, LedgerKind, MilestoneStatus
from app.db.models import Deal, EscrowAccount, LedgerEntry, Milestone, MilestoneConfirmation
from app.db.session import batch_session
from seed.cli import seed

pytestmark = pytest.mark.db


def test_seeded_escrow_obeys_the_invariant_and_new_columns(migrated_db: str) -> None:
    seed()
    with batch_session() as s:
        for e in s.scalars(select(EscrowAccount)).all():
            assert e.funded_total == e.released_total + e.refunded_total + e.balance, e.deal_id
            assert e.partner == "Simulated Escrow Partner" and e.advance_over_20k is False
        rows = s.scalars(select(LedgerEntry)).all()
        assert rows and all(r.kind in (LedgerKind.FUND, LedgerKind.RELEASE) for r in rows)
        assert all(r.milestone_id is not None for r in rows)
        released = s.scalars(
            select(Milestone).where(Milestone.status == MilestoneStatus.RELEASED)
        ).all()
        assert released and all(m.evidence_status == EvidenceStatus.VERIFIED for m in released)
        assert all(m.condition_text for m in s.scalars(select(Milestone)).all())
        main = s.scalars(select(Deal).where(Deal.reference == "SETU-2026-0001")).one()
        n = s.scalar(
            select(func.count())
            .select_from(MilestoneConfirmation)
            .where(MilestoneConfirmation.deal_id == main.id)
        )
        assert n == 2
