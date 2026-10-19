"""The contract between the escrow service and the risk-tier engine (Phase 5.1).

The escrow service calls `evaluate(action, context)` AFTER its own hard checks (evidence VERIFIED,
funds, ACTIVE beneficiary) and obeys the answer:

- ALLOW (tier 0 or 1): the release is posted in the same request.
- REQUIRE_APPROVAL (tier 2 or 3): no money moves. The service creates an `ApprovalRequest` bound
  with `approval_binding_hash`, and the milestone goes to PENDING_APPROVAL. Only a human HTTP
  endpoint (Phase 5.5) can execute it, and execution re-runs this hook (tier recomputed).
- BLOCK: the release is refused (409 RELEASE_BLOCKED).

Fail closed: an ALLOW that carries tier >= 2 is treated as REQUIRE_APPROVAL, and a REQUIRE_APPROVAL
below tier 2 is raised to tier 2. Tests inject a fake hook through `use_hook` / the `hook=`
argument of the service; production always uses `app.services.risk.adapter.evaluate_release`.
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from enum import StrEnum
from typing import Any

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
    # Document forensics (P14), deal-wide: any document, on any milestone or none.
    document_instruction: bool = False
    document_duplicate: bool = False
    # Phase 5.1: facts for the tier engine. Built by code from the DB, never from request fields.
    origin: str = "USER_UI"  # USER_UI | AGENT | SYSTEM
    buyer_id: str = ""
    supplier_id: str = ""
    max_document_fraud_score: int = Field(default=0, ge=0, le=100)  # this tranche's documents
    any_document_warning: bool = False
    any_document_failed: bool = False
    sanctions_hit: bool = False
    kyb_account_warning: bool = False
    fx_lock_missing: bool = False


class RiskResult(_Model):
    decision: RiskDecision
    tier: int = Field(ge=0, le=3)
    reasons: list[RiskReason] = []
    context_hash: str = ""
    decided_by: list[str] = []
    trace: list[dict[str, Any]] = []
    hints: list[dict[str, Any]] = []
    explanation_en: str = ""
    explanation_bn: str = ""


RiskHook = Callable[[RiskAction, ReleaseContext], RiskResult]


_hook: RiskHook | None = None


def get_hook() -> RiskHook | None:
    """The injected test hook, if any. The service falls back to the real engine
    (`app.services.risk.adapter.evaluate_release`); security never imports services."""
    return _hook


def set_hook(hook: RiskHook | None) -> None:
    global _hook
    _hook = hook


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
