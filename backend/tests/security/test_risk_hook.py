"""The risk-hook contract between the escrow service and the engine (the rules themselves are in
tests/risk/test_engine.py)."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.security import risk_hook
from app.security.risk_hook import (
    ReleaseContext,
    RiskAction,
    RiskDecision,
    RiskReason,
    RiskResult,
)
from app.services.risk import adapter


def context(**over: object) -> ReleaseContext:
    base = dict(
        deal_id=uuid.uuid4(),
        deal_ref="SETU-2026-0001",
        milestone_id=uuid.uuid4(),
        milestone_seq=1,
        amount=Decimal("2880.00"),
        currency="USD",
        amount_usd=Decimal("2880.00"),
        settlement_currency="USD",
        fx_rate=None,
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


def test_context_is_frozen_and_rejects_unknown_fields() -> None:
    c = context()
    with pytest.raises(ValidationError):
        c.amount = Decimal("1")  # type: ignore[misc]
    with pytest.raises(ValidationError):
        context(tier=0)
    with pytest.raises(ValidationError):
        context(approved=True)


def test_no_default_hook_lives_in_security() -> None:
    assert risk_hook.get_hook() is None


def test_normalise_fails_closed() -> None:
    allow_t3 = RiskResult(decision=RiskDecision.ALLOW, tier=3)
    assert risk_hook.normalise(allow_t3).decision == RiskDecision.REQUIRE_APPROVAL
    approve_t1 = RiskResult(decision=RiskDecision.REQUIRE_APPROVAL, tier=1)
    assert risk_hook.normalise(approve_t1).tier == 2
    block = RiskResult(decision=RiskDecision.BLOCK, tier=3)
    assert risk_hook.normalise(block) == block


def test_use_hook_restores_the_previous_hook() -> None:
    def fake(action: RiskAction, c: ReleaseContext) -> RiskResult:
        return RiskResult(
            decision=RiskDecision.BLOCK, tier=3, reasons=[RiskReason(code="X", message="x")]
        )

    with risk_hook.use_hook(fake):
        assert risk_hook.get_hook() is fake
    assert risk_hook.get_hook() is None


def test_the_adapter_maps_the_context_and_is_deterministic() -> None:
    c = context()
    first = adapter.evaluate_release(RiskAction.RELEASE_TRANCHE, c)
    second = adapter.evaluate_release(RiskAction.RELEASE_TRANCHE, c)
    assert first == second
    assert (first.decision, first.tier) == (RiskDecision.ALLOW, 1)
    assert len(first.context_hash) == 64
