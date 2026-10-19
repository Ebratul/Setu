"""FR-5 deals, milestone schedule and simulated escrow. Humans only: these endpoints are the
Tier 2/3 execution paths and are never exposed as agent tools. Foreign deals look missing (404);
a supplier may confirm the schedule and read its deals, never fund, release or refund (403)."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
from app.db.enums import DealStatus, EvidenceStatus
from app.db.session import get_db
from app.errors import NotFound
from app.schemas.deals import (
    ActivityOut,
    ChangeBeneficiaryRequest,
    ChangeBeneficiaryResult,
    ConfirmRequest,
    CreateDealRequest,
    DealDetail,
    DealList,
    EvidenceRequest,
    EvidenceResult,
    FundRequest,
    FxLockRequest,
    FxLockResult,
    HintOut,
    LedgerOut,
    ProposeRequest,
    RefundRequest,
    RefundResult,
    ReleaseRequest,
    ReleaseResult,
    RiskOut,
    TraceItemOut,
)
from app.services import beneficiary, deals, escrow, fx_lock
from app.services.risk.engine import TEXT, RiskDecision

router = APIRouter(tags=["deals"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
DealRef = Annotated[str, Query(max_length=64, pattern=r"^[A-Za-z0-9-]+$")]


@router.post("/deals", response_model=DealDetail, status_code=201)
def create_deal(body: CreateDealRequest, db: Db, user: User) -> DealDetail:
    """Create a DRAFT deal and run KYB on the supplier for it (buyer or admin)."""
    deal = deals.create_deal(db, user, body)
    return deals.detail(db, user, deal)


@router.get("/deals", response_model=DealList)
def list_deals(db: Db, user: User, status: DealStatus | None = None) -> DealList:
    """Deals the caller may see: a buyer's own, a supplier's own, or all for admin and judge."""
    return deals.list_deals(db, user, status)


@router.get("/deals/{deal_id}", response_model=DealDetail)
def get_deal(deal_id: str, db: Db, user: User) -> DealDetail:
    """Deal header, KYB, milestones with evidence status, escrow card and `can_*` flags."""
    return deals.detail(db, user, deals.find_deal(db, user, deal_id))


@router.post("/deals/{deal_id}/milestones/propose", response_model=DealDetail)
def propose(deal_id: str, body: ProposeRequest, db: Db, user: User) -> DealDetail:
    """Propose the 30/60/10 template or custom percents; resets any confirmations."""
    deal = deals.find_deal(db, user, deal_id)
    deals.propose_milestones(db, user, deal.id, body)
    return deals.detail(db, user, deal)


@router.post("/deals/{deal_id}/milestones/confirm", response_model=DealDetail)
def confirm(deal_id: str, body: ConfirmRequest, db: Db, user: User) -> DealDetail:
    """Confirm the proposed schedule for your side; the deal is CONFIRMED when both have."""
    deal = deals.find_deal(db, user, deal_id)
    deals.confirm_milestones(db, user, deal.id, body.party_role)
    return deals.detail(db, user, deal)


@router.post("/deals/{deal_id}/escrow/fund", response_model=DealDetail)
def fund(deal_id: str, body: FundRequest, db: Db, user: User) -> DealDetail:
    """Deposit into the simulated escrow (buyer or admin). Omit `amount` for the next tranche."""
    deal = deals.find_deal(db, user, deal_id)
    amount = None if body.amount is None else Decimal(body.amount)
    escrow.fund_escrow(db, user, deal.id, amount)
    return deals.detail(db, user, deal)


def _risk(d: RiskDecision) -> RiskOut:
    return RiskOut(
        decision=d.decision.value,  # type: ignore[arg-type]
        tier=d.tier,
        reasons=[TEXT[c][0] for c in d.reason_codes],
        explanation_en=d.explanation_en,
        explanation_bn=d.explanation_bn,
        context_hash=d.context_hash,
        decided_by=d.decided_by,
        trace=[TraceItemOut.model_validate(t.model_dump()) for t in d.trace],
        hints=[HintOut.model_validate(h.model_dump()) for h in d.hints],
    )


@router.post(
    "/deals/{deal_id}/fx-lock",
    response_model=FxLockResult,
    responses={202: {"model": FxLockResult, "description": "Waiting for human approval"}},
)
def lock_fx(
    deal_id: str, body: FxLockRequest, response: Response, db: Db, user: User
) -> FxLockResult:
    """Lock today's simulated FX rate (Tier 2: a person's own request is the one-tap)."""
    deal = deals.find_deal(db, user, deal_id)
    out = fx_lock.lock_fx(db, user, deal.id, None if body.amount is None else Decimal(body.amount))
    if out.outcome == "PENDING_APPROVAL":
        response.status_code = 202
    lock = out.lock
    return FxLockResult(
        outcome=out.outcome,  # type: ignore[arg-type]
        base=lock.base if lock else None,  # type: ignore[arg-type]
        quote=lock.quote if lock else None,  # type: ignore[arg-type]
        rate=str(lock.rate) if lock else None,
        amount=str(lock.amount) if lock else None,
        expires_at=lock.expires_at if lock else None,
        approval=deals.approval_ref(out.approval) if out.approval else None,
        risk=_risk(out.decision),
    )


@router.post(
    "/deals/{deal_id}/beneficiary",
    response_model=ChangeBeneficiaryResult,
    responses={202: {"model": ChangeBeneficiaryResult, "description": "Waiting for approval"}},
)
def change_beneficiary(
    deal_id: str, body: ChangeBeneficiaryRequest, response: Response, db: Db, user: User
) -> ChangeBeneficiaryResult:
    """Ask to change the receiving account. Always Tier 3 (OTP + cooling-off): this only creates
    the approval request; nothing changes until a person approves it."""
    deal = deals.find_deal(db, user, deal_id)
    out = beneficiary.change_beneficiary(db, user, deal.id, body.bank_account_id)
    if out.outcome == "PENDING_APPROVAL":
        response.status_code = 202
    return ChangeBeneficiaryResult(
        outcome=out.outcome,  # type: ignore[arg-type]
        approval=deals.approval_ref(out.approval) if out.approval else None,
        risk=_risk(out.decision),
        deal=deals.detail(db, user, deal),
    )


@router.get("/deals/{deal_id}/ledger", response_model=LedgerOut)
def deal_ledger(deal_id: str, db: Db, user: User) -> LedgerOut:
    """Simulated double-entry postings of the deal (read-only for supplier and judge)."""
    return deals.ledger(db, user, deals.find_deal(db, user, deal_id))


@router.get("/deals/{deal_id}/activity", response_model=ActivityOut)
def deal_activity(deal_id: str, db: Db, user: User) -> ActivityOut:
    """Signed audit entries recorded for this deal, newest first."""
    return deals.activity(db, user, deals.find_deal(db, user, deal_id))


@router.post("/deals/{deal_id}/refund", response_model=RefundResult)
def refund_deal(deal_id: str, body: RefundRequest, db: Db, user: User) -> RefundResult:
    """Admin dispute path: return the whole escrow balance to the buyer and cancel the deal."""
    deal = deals.find_deal(db, user, deal_id)
    out = escrow.refund(db, user, reason=body.reason, deal_id=deal.id)
    return deals.refund_result(db, user, out)


@router.post(
    "/milestones/{milestone_id}/release",
    response_model=ReleaseResult,
    responses={202: {"model": ReleaseResult, "description": "Waiting for human approval"}},
)
def release(
    milestone_id: uuid.UUID, body: ReleaseRequest, response: Response, db: Db, user: User
) -> ReleaseResult:
    """Release a tranche to the supplier (buyer or admin). Idempotent per `idempotency_key`.
    202 when the risk engine requires approval: no money moves until a human approves."""
    ms, _ = deals.find_milestone(db, user, milestone_id)
    out = escrow.release_tranche(db, ms.id, user, body.idempotency_key)
    if out.outcome == "PENDING_APPROVAL":
        response.status_code = 202
    return deals.release_result(db, user, out)


@router.post("/milestones/{milestone_id}/refund", response_model=RefundResult)
def refund_milestone(
    milestone_id: uuid.UUID, body: RefundRequest, db: Db, user: User
) -> RefundResult:
    """Admin dispute path: return one funded, unreleased tranche to the buyer."""
    ms, _ = deals.find_milestone(db, user, milestone_id)
    out = escrow.refund(db, user, reason=body.reason, milestone_id=ms.id)
    return deals.refund_result(db, user, out)


@router.post("/milestones/{milestone_id}/evidence", response_model=EvidenceResult)
def set_evidence(
    milestone_id: uuid.UUID, body: EvidenceRequest, db: Db, user: User
) -> EvidenceResult:
    """DEV/TEST ONLY (404 unless ENABLE_DEV_EVIDENCE=true and APP_ENV is not prod): set the
    evidence verdict that Phase 14's document pipeline will set."""
    settings = get_settings()
    if not settings.enable_dev_evidence or settings.app_env == "prod":
        raise NotFound("not found")
    ms, deal = deals.find_milestone(db, user, milestone_id)
    escrow.authorize(db, user, deal, "EVIDENCE")
    escrow.set_evidence_status(db, ms.id, EvidenceStatus(body.status), actor=user)
    detail = deals.detail(db, user, deal)
    return EvidenceResult(milestone=next(m for m in detail.milestones if m.id == ms.id))
