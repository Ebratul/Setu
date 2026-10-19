"""Security-review hardening for FR-5: the interim risk policy end to end, open approvals, frozen
escrow, Tier 3 holds, buyer-row locking, supplier projection, audit of 403s and refund clean-up.
These run with the DEFAULT interim hook unless a test injects its own."""

import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, update

from app.db.enums import (
    ApprovalAction,
    ApprovalStatus,
    EscrowStatus,
    MilestoneStatus,
)
from app.db.models import ApprovalRequest, Deal, EscrowAccount, Milestone, Party
from app.db.session import batch_session
from app.errors import Conflict
from app.security import risk_hook
from app.security.risk_hook import RiskDecision, RiskResult
from app.services import escrow
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAXIN,
    HUAXIN_USER,
    JUDGE,
    KARIM,
    RAHIMA,
    as_user,
    confirmed,
    create,
    current_user_of,
    fund,
    funded_deal,
    give_cash,
    party_id,
    payload,
    propose,
    release,
    verify_evidence,
)
from tests.api.test_escrow_release import (
    audit_actions,
    fake,
    ms_status,
    release_rows,
    totals,
)

pytestmark = pytest.mark.db

SEEDED_T2 = "approval:SETU-2026-0001:release-m1"
SEEDED_T3 = "approval:shaoxing-huaxin:beneficiary-change-hk"
MAIN = "SETU-2026-0001"


@pytest.fixture(autouse=True)
def fresh_state(seeded_db: str) -> None:
    give_cash("dhaka-stitch-works")
    give_cash("rahima-knitwear")
    with batch_session() as s:  # the two seeded approvals are open at the start of every test
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.key.notin_([SEEDED_T2, SEEDED_T3]))
            .values(status=ApprovalStatus.CANCELLED)
        )
        s.execute(
            update(EscrowAccount)
            .where(
                EscrowAccount.deal_id
                == select(Deal.id).where(Deal.reference == MAIN).scalar_subquery()
            )
            .values(status=EscrowStatus.FUNDED)
        )
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.key.in_([SEEDED_T2, SEEDED_T3]))
            .values(status=ApprovalStatus.PENDING)
        )
        s.execute(
            update(Milestone)
            .where(
                Milestone.deal_id == select(Deal.id).where(Deal.reference == MAIN).scalar_subquery()
            )
            .values(status=MilestoneStatus.READY)
            .where(Milestone.seq == 1)
        )


def decide_tier3() -> None:
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.key == SEEDED_T3)
            .values(status=ApprovalStatus.REJECTED)
        )


def usd_deal(buyer, goods: str = "9600.00", percents=None, supplier=BRIGHTLINE, **kw):  # type: ignore[no-untyped-def]
    """Confirmed USD deal (Brightline has a USD account) with the first tranche deposited."""
    d = create(buyer, supplier, qty=goods, price="1.00", **kw)
    propose(buyer, d["id"], **({"template": "custom", "percents": percents} if percents else {}))
    confirmed(buyer, None, d["id"])
    return fund(buyer, d["id"])


# --- the interim policy on real releases ------------------------------------------------------


def test_seeded_tier3_beneficiary_change_freezes_every_huaxin_release() -> None:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, body = release(karim, ms)
    assert status == 409 and body["code"] == "TIER3_APPROVAL_PENDING"
    assert release_rows(d["id"]) == 0
    main_m1 = as_user(RAHIMA).get(f"/deals/{MAIN}").json()["milestones"][0]
    assert release(as_user(RAHIMA), main_m1["id"])[1]["code"] == "TIER3_APPROVAL_PENDING"
    # APPROVED but not yet executed still holds the money
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.key == SEEDED_T3)
            .values(status=ApprovalStatus.APPROVED)
        )
    assert release(karim, ms)[1]["code"] == "TIER3_APPROVAL_PENDING"
    decide_tier3()
    assert release(karim, ms)[0] == 202


def test_demo_deal_cny_release_is_tier_two_and_reuses_the_seeded_approval() -> None:
    decide_tier3()
    rahima = as_user(RAHIMA)
    m1 = rahima.get(f"/deals/{MAIN}").json()["milestones"][0]["id"]
    status, body = release(rahima, m1)
    assert status == 202 and body["risk"]["tier"] == 2
    assert body["risk"]["reasons"] and "no rate is locked" in body["risk"]["reasons"][0]
    assert body["approval"]["key"] == SEEDED_T2
    assert release_rows(body["deal"]["id"]) == 0


def test_usd_release_to_a_known_supplier_is_tier_one_with_a_notice() -> None:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = usd_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, body = release(karim, ms)
    assert status == 200 and body["risk"]["tier"] == 1 and body["notice"]


def test_first_deal_with_a_supplier_needs_one_tap_approval() -> None:
    rahima, admin = as_user(RAHIMA), as_user(ADMIN)
    d = usd_deal(rahima, goods="1000.00")  # Rahima only has a DRAFT with Brightline
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, body = release(rahima, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    assert body["approval"]["tier"] == 2 and body["approval"]["otp_required"] is False


def test_twenty_thousand_is_tier_one_and_one_cent_more_is_tier_three() -> None:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    at_limit = usd_deal(karim, goods="40000.00", percents=["50", "50"])
    assert at_limit["milestones"][0]["amount"] == "20000.00"
    assert at_limit["escrow"]["advance_over_20k"] is False
    ms = at_limit["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, body = release(karim, ms)
    assert status == 200 and body["risk"]["tier"] == 1

    over = usd_deal(karim, goods="40000.02", percents=["50", "50"])
    assert over["milestones"][0]["amount"] == "20000.01"
    assert over["escrow"]["advance_over_20k"] is True
    ms2 = over["milestones"][0]["id"]
    verify_evidence(admin, ms2)
    status, body = release(karim, ms2)
    assert status == 202 and body["risk"]["tier"] == 3
    assert body["approval"]["otp_required"] is True and body["approval"]["cooling_off_until"]
    assert body["deal"]["escrow"]["status"] == "FROZEN"


def test_the_hook_gets_the_unrounded_usd_amount_for_a_cny_deal() -> None:
    decide_tier3()
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = create(karim, HUAXIN, qty="283960.02", price="1.00", currency="CNY")
    propose(karim, d["id"], template="custom", percents=["50", "50"])
    confirmed(karim, as_user(HUAXIN_USER), d["id"])
    d = fund(karim, d["id"])
    ms = d["milestones"][0]["id"]
    assert d["milestones"][0]["amount"] == "141980.01"
    verify_evidence(admin, ms)
    seen: list[Any] = []
    with risk_hook.use_hook(fake(RiskDecision.ALLOW, 1, seen=seen)):
        assert release(karim, ms)[0] == 200
    usd = seen[0].amount_usd
    assert usd != usd.quantize(Decimal("0.01")), "not rounded before the hook sees it"
    assert seen[0].settlement_currency == "CNY" and seen[0].currency == "CNY"


# --- open approvals, frozen escrow ------------------------------------------------------------


def parked(tier: int = 2):  # type: ignore[no-untyped-def]
    decide_tier3()
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, tier, "FX_RATE_LOCK")):
        status, body = release(karim, ms)
    assert status == 202
    return karim, admin, d, ms, body["approval"]["id"]


def test_an_approved_but_unexecuted_approval_does_not_let_a_plain_release_post() -> None:
    karim, _, d, ms, aid = parked(2)
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(aid))
            .values(status=ApprovalStatus.APPROVED)
        )
    allow = RiskResult(decision=RiskDecision.ALLOW, tier=0)
    with risk_hook.use_hook(lambda a, c: allow):
        status, body = release(karim, ms, "plain-key-0001")
    assert status == 202 and body["outcome"] == "PENDING_APPROVAL"
    assert body["approval"]["status"] == "APPROVED"
    assert release_rows(d["id"]) == 0 and totals(d["id"])["released"] == 0


def test_a_frozen_escrow_refuses_a_plain_release() -> None:
    decide_tier3()
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:
        s.execute(
            update(EscrowAccount)
            .where(EscrowAccount.deal_id == uuid.UUID(d["id"]))
            .values(status=EscrowStatus.FROZEN)
        )
    allow = RiskResult(decision=RiskDecision.ALLOW, tier=0)
    with risk_hook.use_hook(lambda a, c: allow):
        status, body = release(karim, ms)
    assert status == 409 and body["code"] == "ESCROW_FROZEN" and release_rows(d["id"]) == 0


def test_a_deal_level_tier3_approval_holds_the_money() -> None:
    decide_tier3()
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:
        deal = s.get(Deal, uuid.UUID(d["id"]))
        assert deal is not None
        s.add(
            ApprovalRequest(
                id=uuid.uuid4(),
                key=f"approval:test:{uuid.uuid4().hex}",
                deal_id=deal.id,
                milestone_id=None,
                bank_account_id=None,
                action=ApprovalAction.CHANGE_BENEFICIARY,
                tier=3,
                params={},
                params_hash="0" * 64,
                reasons=[],
                status=ApprovalStatus.PENDING,
                requested_by=ApprovalRequest.requested_by.type.python_type("system"),  # type: ignore[attr-defined]
                otp_required=True,
                cooling_off_until=deal.created_at,
                created_at=deal.created_at,
            )
        )
    allow = RiskResult(decision=RiskDecision.ALLOW, tier=0)
    with risk_hook.use_hook(lambda a, c: allow):
        status, body = release(karim, ms)
    assert status == 409 and body["code"] == "TIER3_APPROVAL_PENDING"


def test_a_resync_to_pending_approval_is_audited() -> None:
    decide_tier3()
    rahima = as_user(RAHIMA)
    d = rahima.get(f"/deals/{MAIN}").json()
    allow = RiskResult(decision=RiskDecision.ALLOW, tier=0)
    with risk_hook.use_hook(lambda a, c: allow):
        status, body = release(rahima, d["milestones"][0]["id"])
    assert status == 202 and body["approval"]["key"] == SEEDED_T2
    assert "RELEASE_PENDING_APPROVAL_RESYNC" in audit_actions(d["id"])


def test_a_new_request_after_a_rejection_gets_a_fresh_approval() -> None:
    karim, _, _d, ms, aid = parked(2)
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(aid))
            .values(status=ApprovalStatus.REJECTED)
        )
    with batch_session() as s:
        escrow.release_approval_closed(s, uuid.UUID(aid))
    assert ms_status(ms) == MilestoneStatus.READY
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, 2, "FX_RATE_LOCK")):
        status, body = release(karim, ms, "second-try-0001")
    assert status == 202 and body["approval"]["id"] != aid
    with batch_session() as s:
        keys = list(
            s.scalars(
                select(ApprovalRequest.key).where(ApprovalRequest.milestone_id == uuid.UUID(ms))
            )
        )
    assert len(keys) == 2 and len(set(keys)) == 2


def test_a_stricter_request_supersedes_the_open_lower_tier_approval() -> None:
    """The seeded Tier 2 approval is open while M1 is still READY; a Tier 3 verdict replaces it."""
    decide_tier3()
    rahima = as_user(RAHIMA)
    d = rahima.get(f"/deals/{MAIN}").json()
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, 3, "DOC_INSTRUCTION")):
        status, body = release(rahima, d["milestones"][0]["id"], "stricter-0001")
    assert status == 202 and body["approval"]["tier"] == 3 and body["approval"]["key"] != SEEDED_T2
    with batch_session() as s:
        old = s.scalars(select(ApprovalRequest).where(ApprovalRequest.key == SEEDED_T2)).one()
        assert old.status == ApprovalStatus.CANCELLED
    assert "APPROVAL_SUPERSEDED" in audit_actions(d["id"])


def test_a_refund_cancels_open_release_approvals_and_audits_it() -> None:
    _, admin, d, ms, aid = parked(2)
    res = admin.post(f"/deals/{d['id']}/refund", json={"reason": "supplier ceased trading"})
    assert res.status_code == 200, res.text
    with batch_session() as s:
        assert s.get(ApprovalRequest, uuid.UUID(aid)).status == ApprovalStatus.CANCELLED  # type: ignore[union-attr]
    assert "APPROVAL_CANCELLED_BY_REFUND" in audit_actions(d["id"])
    assert ms_status(ms) == MilestoneStatus.REFUNDED


# --- buyer-row locking ------------------------------------------------------------------------


def threads(*targets) -> None:  # type: ignore[no-untyped-def]
    barrier = threading.Barrier(len(targets))

    def wrap(fn):  # type: ignore[no-untyped-def]
        def run() -> None:
            barrier.wait()
            fn()

        return run

    ts = [threading.Thread(target=wrap(t)) for t in targets]
    [t.start() for t in ts]
    [t.join(timeout=30) for t in ts]


def confirmed_unfunded(buyer: Any) -> uuid.UUID:
    d = create(buyer, HUAXIN)
    propose(buyer, d["id"])
    confirmed(buyer, as_user(HUAXIN_USER), d["id"])
    return uuid.UUID(d["id"])


def cash(code: str) -> Decimal:
    with batch_session() as s:
        return s.scalars(select(Party.cash_balance).where(Party.code == code)).one()  # type: ignore[return-value]


def test_concurrent_funding_of_two_deals_cannot_overdraw_the_buyer() -> None:
    karim = as_user(KARIM)
    a, b = confirmed_unfunded(karim), confirmed_unfunded(karim)
    give_cash("dhaka-stitch-works", "5000.00")  # enough for one 2,880 deposit, not two
    user = current_user_of(KARIM)
    results: list[Any] = []

    def go(deal_id: uuid.UUID):  # type: ignore[no-untyped-def]
        def run() -> None:
            with batch_session() as s:
                try:
                    results.append(escrow.fund_escrow(s, user, deal_id))
                except Conflict as exc:
                    results.append(exc)

        return run

    threads(go(a), go(b))
    ok = [r for r in results if isinstance(r, escrow.FundOutcome)]
    refused = [r for r in results if isinstance(r, Conflict)]
    assert len(ok) == 1 and len(refused) == 1 and refused[0].code == "INSUFFICIENT_CASH"
    assert cash("dhaka-stitch-works") == Decimal("2120.00")


def test_fund_racing_a_refund_keeps_cash_and_escrow_consistent() -> None:
    karim = as_user(KARIM)
    deal_id = confirmed_unfunded(karim)
    with batch_session() as s:  # a first deposit so there is something to refund
        escrow.fund_escrow(s, current_user_of(KARIM), deal_id)
    give_cash("dhaka-stitch-works", "10000.00")
    funder, admin = current_user_of(KARIM), current_user_of(ADMIN)
    errors: list[Exception] = []

    def do_fund() -> None:
        with batch_session() as s:
            try:
                escrow.fund_escrow(s, funder, deal_id, Decimal("1000.00"))
            except Conflict as exc:
                errors.append(exc)

    def do_refund() -> None:
        with batch_session() as s:
            try:
                escrow.refund(s, admin, reason="supplier ceased trading", deal_id=deal_id)
            except Conflict as exc:
                errors.append(exc)

    threads(do_fund, do_refund)
    t = totals(str(deal_id))  # also asserts funded = released + refunded + balance and the ledger
    assert t["funded"] - t["refunded"] - t["released"] == t["balance"]
    # cash moved by exactly what was deposited minus what came back
    assert (
        cash("dhaka-stitch-works")
        == Decimal("10000.00") - (t["funded"] - Decimal("2880.00")) + t["refunded"]
    )
    assert all(e.code in ("DEAL_NOT_FUNDABLE", "NOT_REFUNDABLE") for e in errors)


# --- supplier projection, 403 audit, caps -----------------------------------------------------


def test_a_supplier_sees_its_deal_without_the_buyers_business_details() -> None:
    karim, huaxin, admin = as_user(KARIM), as_user(HUAXIN_USER), as_user(ADMIN)
    d = create(karim, HUAXIN, expected_sale_value="14000.00")
    propose(karim, d["id"])
    confirmed(karim, huaxin, d["id"])
    d = fund(karim, d["id"])
    with batch_session() as s:
        s.execute(
            update(Deal)
            .where(Deal.id == uuid.UUID(d["id"]))
            .values(dispute_reason="quality claim about lot 7")
        )
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, 2, "FX_RATE_LOCK")):
        decide_tier3()
        assert release(karim, ms)[0] == 202
    full = karim.get(f"/deals/{d['id']}").json()
    seen = huaxin.get(f"/deals/{d['id']}").json()
    assert (
        full["expected_sale_value"] == "14000.00" and full["costs"] and full["kyb"]["score"] == 100
    )
    assert full["milestones"][0]["approval"]["reasons"] == ["because FX_RATE_LOCK"]
    assert full["dispute_reason"] == "quality claim about lot 7"
    assert seen["expected_sale_value"] is None and seen["costs"] == []
    assert seen["dispute_reason"] is None
    assert seen["kyb"]["score"] is None and seen["kyb"]["reason_codes"] == []
    assert seen["kyb"]["status"] == "VERIFIED"
    assert seen["milestones"][0]["approval"]["reasons"] == []
    assert seen["milestones"][0]["approval"]["tier"] == 2
    assert set(seen) == set(full) and seen["escrow"] == full["escrow"], "same shape, same escrow"
    assert [m["amount"] for m in seen["milestones"]] == [m["amount"] for m in full["milestones"]]

    ledger = huaxin.get(f"/deals/{d['id']}/ledger").json()
    assert ledger["balanced"] and not any(
        r["account"].startswith("buyer:") and r["account"] != "buyer:cash" for r in ledger["rows"]
    )
    assert "dhaka" not in huaxin.get(f"/deals/{d['id']}/ledger").text
    full_ledger = karim.get(f"/deals/{d['id']}/ledger").json()
    assert any("dhaka" in r["account"] for r in full_ledger["rows"])

    feed = huaxin.get(f"/deals/{d['id']}/activity").json()["rows"]
    assert feed and {r["action"] for r in feed} >= {"ESCROW_FUNDED", "MILESTONES_CONFIRMED"}
    assert all(
        r["result"] == r["params_hash"] == r["entry_hash"] == r["key_id"] == "" for r in feed
    )
    buyer_feed = karim.get(f"/deals/{d['id']}/activity").json()["rows"]
    assert all(r["entry_hash"] and r["result"] for r in buyer_feed)


def test_forbidden_attempts_leave_audit_rows() -> None:
    karim, huaxin, judge = as_user(KARIM), as_user(HUAXIN_USER), as_user(JUDGE)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    assert huaxin.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 403
    assert release(huaxin, ms)[0] == 403
    assert huaxin.post(f"/deals/{d['id']}/milestones/propose", json={}).status_code == 403
    assert judge.post(f"/deals/{d['id']}/milestones/confirm", json={}).status_code == 403
    assert karim.post(f"/milestones/{ms}/refund", json={"reason": "not allowed"}).status_code == 403
    assert as_user(HUAXIN_USER).post("/deals", json=payload(party_id(HUAXIN))).status_code == 403
    actions = audit_actions(d["id"])
    for expected in (
        "FUND_FORBIDDEN",
        "RELEASE_FORBIDDEN",
        "PROPOSE_FORBIDDEN",
        "CONFIRM_FORBIDDEN",
        "REFUND_FORBIDDEN",
    ):
        assert expected in actions, expected
    # a foreign buyer is 404 and leaves no row on the deal
    before = len(audit_actions(d["id"]))
    assert as_user(RAHIMA).post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 404
    assert len(audit_actions(d["id"])) == before


def test_goods_value_is_capped() -> None:
    karim = as_user(KARIM)
    body = payload(party_id(HUAXIN), qty="10000000000", price="1000")
    res = karim.post("/deals", json=body)
    assert res.status_code == 400 and res.json()["code"] == "INVALID_AMOUNT"
    ok = karim.post("/deals", json=payload(party_id(HUAXIN), qty="1000000", price="100"))
    assert ok.status_code == 201
