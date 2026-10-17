"""The risk-hook contract between the escrow service and Phase 5.1."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.security import risk_hook
from app.security.policy import TIER1_MAX_USD
from app.security.risk_hook import (
    ReleaseContext,
    RiskAction,
    RiskDecision,
    RiskReason,
    RiskResult,
)


def context(**over: object) -> ReleaseContext:
    base = dict(
        deal_id=uuid.uuid4(),
        deal_ref="SETU-2026-0001",
        milestone_id=uuid.uuid4(),
        milestone_seq=1,
        amount=Decimal("2880.00"),
        currency="USD",
        amount_usd=Decimal("2880.00"),
        settlement_currency="CNY",
        fx_rate=Decimal("7.099"),
        beneficiary_account_id=uuid.uuid4(),
        beneficiary_status="ACTIVE",
        beneficiary_verified=True,
        beneficiary_changed_recently=False,
        supplier_kyb_status="VERIFIED",
        supplier_deal_count=2,
        evidence_status="VERIFIED",
        escrow_balance=Decimal("2880.00"),
        advance_over_20k=False,
        requested_by_user_id=uuid.uuid4(),
        requested_by_role="BUYER",
    )
    return ReleaseContext(**{**base, **over})


USD_SAME = {"settlement_currency": "USD", "fx_rate": None}


def decide(**over: object) -> RiskResult:
    return risk_hook.default_evaluate(RiskAction.RELEASE_TRANCHE, context(**over))


def test_interim_policy_allows_a_clean_release_at_tier_one() -> None:
    # TODO(5.1): replaced by classify(); this pins the interim fail-closed policy.
    res = decide(**USD_SAME)
    assert (res.decision, res.tier, res.reasons) == (RiskDecision.ALLOW, 1, [])


def test_interim_policy_tier_two_triggers() -> None:
    fx = decide()  # CNY settlement of a USD deal: needs a rate lock
    assert (fx.decision, fx.tier) == (RiskDecision.REQUIRE_APPROVAL, 2)
    assert [r.code for r in fx.reasons] == ["FX_RATE_LOCK"]
    first = decide(**USD_SAME, supplier_deal_count=0)
    assert (first.decision, first.tier) == (RiskDecision.REQUIRE_APPROVAL, 2)
    assert [r.code for r in first.reasons] == ["FIRST_DEAL"]
    both = decide(supplier_deal_count=0)
    assert both.tier == 2 and {r.code for r in both.reasons} == {"FIRST_DEAL", "FX_RATE_LOCK"}


@pytest.mark.parametrize(
    ("amount_usd", "tier"),
    [
        ("20000.00", 1),  # the limit itself is Tier 1
        ("20000.0000", 1),
        ("20000.01", 3),
        ("20000.0014", 3),  # rounds to 20000.00 but is above the limit: never round it away
        ("19999.9999", 1),
    ],
)
def test_amount_limit_boundary_is_strict_on_the_unrounded_value(amount_usd: str, tier: int) -> None:
    res = decide(**USD_SAME, amount_usd=Decimal(amount_usd), amount=Decimal(amount_usd))
    assert res.tier == tier
    assert res.decision == (RiskDecision.ALLOW if tier == 1 else RiskDecision.REQUIRE_APPROVAL)


def test_interim_policy_tier_three_triggers_win_over_tier_two() -> None:
    adv = decide(advance_over_20k=True)
    assert adv.tier == 3 and {r.code for r in adv.reasons} == {"ADVANCE_OVER_20K", "FX_RATE_LOCK"}
    new = decide(**USD_SAME, beneficiary_changed_recently=True, supplier_deal_count=0)
    assert new.tier == 3 and new.reasons[0].code == "NEW_BENEFICIARY"
    assert decide(**USD_SAME, advance_over_20k=True).decision == RiskDecision.REQUIRE_APPROVAL


def test_models_are_strict_and_frozen() -> None:
    ctx = context()
    with pytest.raises(ValidationError):
        ReleaseContext(**{**ctx.model_dump(), "extra_field": 1})
    with pytest.raises(ValidationError):
        ctx.amount = Decimal("1")  # type: ignore[misc]
    with pytest.raises(ValidationError):
        RiskResult(decision=RiskDecision.ALLOW, tier=4)
    with pytest.raises(ValidationError):
        RiskReason(code="", message="x")


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ((RiskDecision.ALLOW, 0), (RiskDecision.ALLOW, 0)),
        ((RiskDecision.ALLOW, 1), (RiskDecision.ALLOW, 1)),
        ((RiskDecision.ALLOW, 2), (RiskDecision.REQUIRE_APPROVAL, 2)),
        ((RiskDecision.ALLOW, 3), (RiskDecision.REQUIRE_APPROVAL, 3)),
        ((RiskDecision.REQUIRE_APPROVAL, 0), (RiskDecision.REQUIRE_APPROVAL, 2)),
        ((RiskDecision.REQUIRE_APPROVAL, 1), (RiskDecision.REQUIRE_APPROVAL, 2)),
        ((RiskDecision.REQUIRE_APPROVAL, 3), (RiskDecision.REQUIRE_APPROVAL, 3)),
        ((RiskDecision.BLOCK, 3), (RiskDecision.BLOCK, 3)),
    ],
)
def test_normalise_fails_closed(
    given: tuple[RiskDecision, int], expected: tuple[RiskDecision, int]
) -> None:
    out = risk_hook.normalise(RiskResult(decision=given[0], tier=given[1]))
    assert (out.decision, out.tier) == expected


def test_set_hook_and_use_hook_swap_and_restore() -> None:
    block = RiskResult(decision=RiskDecision.BLOCK, tier=3)
    with risk_hook.use_hook(lambda a, c: block):
        assert risk_hook.evaluate(RiskAction.RELEASE_TRANCHE, context()) == block
    default = risk_hook.default_evaluate(RiskAction.RELEASE_TRANCHE, context())
    assert risk_hook.evaluate(RiskAction.RELEASE_TRANCHE, context()) == default
    risk_hook.set_hook(lambda a, c: block)
    try:
        assert risk_hook.evaluate(RiskAction.RELEASE_TRANCHE, context()) == block
    finally:
        risk_hook.set_hook(None)
    assert risk_hook.evaluate(RiskAction.RELEASE_TRANCHE, context()) == default


def test_tier1_limit_constant() -> None:
    assert Decimal("20000") == TIER1_MAX_USD
