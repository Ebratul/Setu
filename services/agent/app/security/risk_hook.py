"""The plug point between the escrow service and the risk-tier engine (Phase 5.1).

The escrow service calls `evaluate(action, context)` AFTER its own hard checks (evidence VERIFIED,
funds, ACTIVE beneficiary) and obeys the answer:

- ALLOW (tier 0 or 1): the release is posted in the same request.
- REQUIRE_APPROVAL (tier 2 or 3): no money moves. The service creates an `ApprovalRequest` bound
  with `approval_binding_hash`, and the milestone goes to PENDING_APPROVAL. Only a human HTTP
  endpoint (Phase 5.5) can execute it, and execution re-runs this hook (tier recomputed).
- BLOCK: the release is refused (409 RELEASE_BLOCKED).

Fail closed: an ALLOW that carries tier >= 2 is treated as REQUIRE_APPROVAL, and a REQUIRE_APPROVAL
below tier 2 is raised to tier 2. Tests inject a fake hook through `set_hook` / the `risk_hook=`
argument of the service.
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskAction(StrEnum):
    RELEASE_TRANCHE = "RELEASE_TRANCHE"


class RiskDecision(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskReason(_Model):
    code: str = Field(min_length=1, max_length=48)
    message: str = Field(max_length=300)


class ReleaseContext(_Model):
    """Everything the engine may look at for a tranche release. Facts only, no free text from
    documents. Phase 5.1 may add fields (fraud score, duplicate-hash hit, document-instruction
    flag) by extending this model."""

    deal_id: uuid.UUID
    deal_ref: str
    milestone_id: uuid.UUID
    milestone_seq: int
    amount: Decimal
    currency: str
    amount_usd: Decimal
    settlement_currency: str
    fx_rate: Decimal | None
    beneficiary_account_id: uuid.UUID
    beneficiary_status: str
    beneficiary_verified: bool
    beneficiary_changed_recently: bool
    supplier_kyb_status: str
    supplier_deal_count: int
    evidence_status: str
    escrow_balance: Decimal
    advance_over_20k: bool
    requested_by_user_id: uuid.UUID
    requested_by_role: str


class RiskResult(_Model):
    decision: RiskDecision
    tier: int = Field(ge=0, le=3)
    reasons: list[RiskReason] = []


RiskHook = Callable[[RiskAction, ReleaseContext], RiskResult]


def default_evaluate(action: RiskAction, context: ReleaseContext) -> RiskResult:
    """Interim fail-closed policy until Phase 5.1 replaces it with `tiers.classify`.

    Tier 3: amount above USD 20,000 (strict, on the UNROUNDED USD amount), money held ahead of
    release above USD 20,000, or a receiving account opened in the last 30 days.
    Tier 2: first deal with this supplier, or a conversion to another currency (needs an FX lock).
    Otherwise ALLOW at tier 1 (auto + notice). Highest tier wins.
    TODO(5.1): replace with app.security.tiers.classify(...) and its full trigger set."""
    from app.security.policy import TIER1_MAX_USD

    t3: list[RiskReason] = []
    t2: list[RiskReason] = []
    if context.amount_usd > TIER1_MAX_USD:
        t3.append(RiskReason(code="AMOUNT_OVER_20K", message="Amount is above USD 20,000."))
    if context.advance_over_20k:
        t3.append(RiskReason(code="ADVANCE_OVER_20K", message="Advance held is above USD 20,000."))
    if context.beneficiary_changed_recently:
        t3.append(
            RiskReason(code="NEW_BENEFICIARY", message="Receiving account was opened recently.")
        )
    if context.supplier_deal_count == 0:
        t2.append(RiskReason(code="FIRST_DEAL", message="First deal with this supplier."))
    if context.settlement_currency != context.currency:
        t2.append(
            RiskReason(
                code="FX_RATE_LOCK",
                message=f"Release converts {context.currency} to {context.settlement_currency}; "
                "the rate must be locked.",
            )
        )
    if t3:
        return RiskResult(decision=RiskDecision.REQUIRE_APPROVAL, tier=3, reasons=t3 + t2)
    if t2:
        return RiskResult(decision=RiskDecision.REQUIRE_APPROVAL, tier=2, reasons=t2)
    return RiskResult(decision=RiskDecision.ALLOW, tier=1, reasons=[])


_hook: RiskHook = default_evaluate


def evaluate(action: RiskAction, context: ReleaseContext) -> RiskResult:
    return _hook(action, context)


def set_hook(hook: RiskHook | None) -> None:
    global _hook
    _hook = hook or default_evaluate


@contextmanager
def use_hook(hook: RiskHook) -> Iterator[None]:
    global _hook
    previous = _hook
    _hook = hook
    try:
        yield
    finally:
        _hook = previous


def normalise(result: RiskResult) -> RiskResult:
    """Fail closed on inconsistent answers (see module docstring)."""
    if result.decision == RiskDecision.ALLOW and result.tier >= 2:
        return result.model_copy(update={"decision": RiskDecision.REQUIRE_APPROVAL})
    if result.decision == RiskDecision.REQUIRE_APPROVAL and result.tier < 2:
        return result.model_copy(update={"tier": 2})
    return result
