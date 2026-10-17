"""Walk the seeded demo deal SETU-2026-0001 (funded tranche by tranche, M1 READY, a Tier 2
approval already open) through the new escrow service, and check the cash-flow and alert
derivation does not double count. Mutates the module's own seeded database."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.enums import AlertStatus, AlertType, ApprovalStatus, MilestoneStatus
from app.db.models import Alert, ApprovalRequest, Deal, EscrowAccount, Milestone, Party
from app.db.session import batch_session
from app.security import risk_hook
from app.security.risk_hook import RiskDecision, RiskResult
from app.services import escrow
from app.services.cashflow import load_book
from tests.api.deals_support import (
    ADMIN,
    RAHIMA,
    as_user,
    current_user_of,
    fund,
    release,
    verify_evidence,
)

pytestmark = pytest.mark.db

MAIN = "SETU-2026-0001"
SEEDED_APPROVAL = "approval:SETU-2026-0001:release-m1"


def milestone_flows() -> list[str]:
    with batch_session() as s:
        buyer = s.scalars(select(Party).where(Party.code == "rahima-knitwear")).one()
        return sorted(f.ref for f in load_book(s, buyer).flows if f.kind == "MILESTONE_PAYMENT")


def shortfalls() -> list[tuple[str, Decimal | None]]:
    with batch_session() as s:
        rows = s.scalars(
            select(Alert).where(
                Alert.type == AlertType.SHORTFALL, Alert.status != AlertStatus.RESOLVED
            )
        ).all()
        return sorted((a.key, a.amount) for a in rows)


def test_seeded_main_deal_reads_through_the_new_model(seeded_db: str) -> None:
    rahima = as_user(RAHIMA)
    d = rahima.get(f"/deals/{MAIN}").json()
    assert d["status"] == "FUNDED" and d["goods_value"] == "9600.00" and d["currency"] == "USD"
    assert [m["status"] for m in d["milestones"]] == ["READY", "PENDING", "PENDING"]
    assert [m["amount"] for m in d["milestones"]] == ["2880.00", "5760.00", "960.00"]
    assert d["milestones"][0]["evidence_status"] == "VERIFIED"
    assert [e["status"] for e in d["milestones"][0]["required_evidence"]] == ["VERIFIED"] * 2
    assert all(m["condition_text"] for m in d["milestones"])
    e = d["escrow"]
    assert (e["funded"], e["released"], e["balance"], e["status"]) == (
        "2880.00",
        "0.00",
        "2880.00",
        "FUNDED",
    )
    assert e["invariant_ok"] and e["partner"] == "Simulated Escrow Partner"
    assert [c["confirmed"] for c in d["confirmations"]] == [True, True]
    assert d["kyb"]["status"] in ("VERIFIED", "WARNING") and d["settlement_currency"] == "CNY"
    ledger = rahima.get(f"/deals/{MAIN}/ledger").json()
    assert (
        ledger["balanced"]
        and [(r["kind"], r["milestone_seq"]) for r in ledger["rows"]] == [("FUND", 1)] * 2
    )


def test_walk_the_demo_deal_through_release_and_the_next_tranche(seeded_db: str) -> None:
    rahima, admin = as_user(RAHIMA), as_user(ADMIN)
    d = rahima.get(f"/deals/{MAIN}").json()
    m1, m2, m3 = (m["id"] for m in d["milestones"])
    before_flows = milestone_flows()
    assert before_flows == [f"milestone:{MAIN}:2", f"milestone:{MAIN}:3"]

    # The seeded Tier 3 beneficiary-change approval is open: no Huaxin money moves until decided.
    status, body = release(rahima, m1)
    assert status == 409 and body["code"] == "TIER3_APPROVAL_PENDING"
    with batch_session() as s:
        s.execute(
            ApprovalRequest.__table__.update()
            .where(ApprovalRequest.tier == 3)
            .values(status=ApprovalStatus.REJECTED)
        )

    # Interim policy: USD -> CNY needs an FX lock (Tier 2), matching the seeded approval, which is
    # reused instead of creating a second one.
    status, body = release(rahima, m1)
    assert status == 202 and body["outcome"] == "PENDING_APPROVAL"
    assert body["approval"]["key"] == SEEDED_APPROVAL and body["approval"]["tier"] == 2
    assert body["risk"]["tier"] == 2 and body["ledger"] == []
    assert body["milestone"]["status"] == "PENDING_APPROVAL"
    with batch_session() as s:
        n = s.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.milestone_id == uuid.UUID(m1))
        )
        assert n == 1, "no second approval is created"
        approval_id = s.scalars(
            select(ApprovalRequest.id).where(ApprovalRequest.key == SEEDED_APPROVAL)
        ).one()
        s.execute(
            ApprovalRequest.__table__.update()
            .where(ApprovalRequest.id == approval_id)
            .values(status=ApprovalStatus.CANCELLED)
        )
    with batch_session() as s:
        escrow.release_approval_closed(s, approval_id)
    assert rahima.get(f"/deals/{MAIN}").json()["milestones"][0]["status"] == "READY"

    # New request, one-tap approval (simulated 5.5), then the execution path posts the release.
    status, body = release(rahima, m1, "demo-walk-m1-0001")
    assert status == 202 and body["approval"]["key"] != SEEDED_APPROVAL
    new_id = uuid.UUID(body["approval"]["id"])
    with batch_session() as s:
        s.execute(
            ApprovalRequest.__table__.update()
            .where(ApprovalRequest.id == new_id)
            .values(status=ApprovalStatus.APPROVED)
        )
    with batch_session() as s:
        done = escrow.release_tranche(
            s, uuid.UUID(m1), current_user_of(RAHIMA), "demo-walk-m1-0001", approval_id=new_id
        )
    assert done.outcome == "RELEASED"
    status, out = release(rahima, m1, "demo-walk-m1-0001")
    assert status == 200 and out["idempotent_replay"] is True
    assert out["deal"]["status"] == "IN_PRODUCTION"
    assert out["ledger"][0]["amount"] == "2880.00" and out["ledger"][0]["counter_currency"] == "CNY"
    assert (
        out["deal"]["escrow"]["balance"] == "0.00"
        and out["deal"]["escrow"]["released"] == "2880.00"
    )
    # Releasing does not touch the buyer's cash or the unfunded-tranche flows (no double count).
    assert milestone_flows() == before_flows

    # Deposit the next tranche: its projected outflow leaves the forecast and the cash drops.
    with batch_session() as s:
        cash_before = s.scalars(
            select(Party.cash_balance).where(Party.code == "rahima-knitwear")
        ).one()
    shortfall_before = shortfalls()
    funded = fund(rahima, MAIN)
    assert funded["escrow"]["funded"] == "8640.00" and funded["escrow"]["balance"] == "5760.00"
    assert [m["status"] for m in funded["milestones"]] == ["RELEASED", "READY", "PENDING"]
    assert milestone_flows() == [f"milestone:{MAIN}:3"]
    with batch_session() as s:
        cash_after = s.scalars(
            select(Party.cash_balance).where(Party.code == "rahima-knitwear")
        ).one()
    assert cash_before - cash_after == Decimal("5760.00")
    # TC-08 shortfall (1,560.00 on 2026-11-07) was driven by the unfunded M2; funding it moved it.
    assert shortfall_before == [
        ("alert:rahima-knitwear:shortfall:balance:2026-11-07", Decimal("1560.00"))
    ]
    assert shortfalls() != shortfall_before, "alerts were recomputed for the buyer"

    verify_evidence(admin, m2)
    status, r2 = release(rahima, m2)
    assert status == 202, "CNY settlement is a Tier 2 FX lock under the interim policy"
    allow = RiskResult(decision=RiskDecision.ALLOW, tier=1)
    with risk_hook.use_hook(lambda a, c: allow), batch_session() as s:
        s.execute(
            ApprovalRequest.__table__.update()
            .where(ApprovalRequest.milestone_id == uuid.UUID(m2))
            .values(status=ApprovalStatus.CANCELLED)
        )
    with batch_session() as s:
        escrow.release_approval_closed(s, uuid.UUID(r2["approval"]["id"]))
    with risk_hook.use_hook(lambda a, c: allow):
        status, r2 = release(rahima, m2, "demo-walk-m2-0001")
    assert status == 200 and r2["deal"]["status"] == "SHIPPED"
    with batch_session() as s:
        e = s.scalars(select(EscrowAccount).join(Deal).where(Deal.reference == MAIN)).one()
        assert e.funded_total == e.released_total + e.refunded_total + e.balance
        assert s.get(Milestone, uuid.UUID(m3)).status == MilestoneStatus.PENDING  # type: ignore[union-attr]


def test_escrow_service_enforces_the_roles_itself(seeded_db: str) -> None:
    """Defence in depth: the service refuses a supplier or judge even when called directly."""
    from app.errors import Forbidden

    with batch_session() as s:
        ms = s.scalars(
            select(Milestone.id).join(Deal).where(Deal.reference == MAIN, Milestone.seq == 3)
        ).one()
        for email in ("huaxin@demo.setu", "judge@demo.setu"):
            with pytest.raises(Forbidden):
                escrow.release_tranche(s, ms, current_user_of(email), "service-guard-0001")
            with pytest.raises(Forbidden):
                escrow.fund_escrow(
                    s,
                    current_user_of(email),
                    s.scalars(select(Deal.id).where(Deal.reference == MAIN)).one(),
                )
