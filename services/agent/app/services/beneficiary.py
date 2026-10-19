"""Change the receiving account of a deal (SR-1: always Tier 3). The request creates an
ApprovalRequest with OTP and a 10-minute cooling-off and changes nothing; only the human approval
endpoint (Phase 17) calls this again with an APPROVED `approval_id`, which executes the change.
A change also cancels open release approvals of the deal: they were bound to the old account."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import AccountStatus, ApprovalAction, ApprovalStatus, Role
from app.db.models import ApprovalRequest, BankAccount, Deal
from app.errors import Forbidden, NotFound
from app.services import escrow as escrow_service
from app.services.escrow import Refusal
from app.services.risk import context as risk_context
from app.services.risk import engine
from app.services.risk import gate as risk_gate
from app.services.risk.engine import Action, Origin

CLOSED_DEALS = ("COMPLETED", "CANCELLED")


@dataclass(frozen=True, slots=True)
class BeneficiaryOutcome:
    deal: Deal
    outcome: str  # CHANGED | PENDING_APPROVAL
    approval: ApprovalRequest | None
    decision: engine.RiskDecision


def change_beneficiary(
    db: Session,
    user: CurrentUser,
    deal_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    *,
    origin: Origin = Origin.USER_UI,
    approval_id: uuid.UUID | None = None,
    supplier_request: bool = False,
    now: datetime | None = None,
) -> BeneficiaryOutcome:
    """`supplier_request`: the supplier asked for the new account through its portal; the caller is
    that supplier, who may only open the request (a human buyer must still approve it)."""
    now = now or escrow_service.utcnow()
    probe = db.get(Deal, deal_id)
    if probe is None:
        raise NotFound("deal not found")
    if supplier_request:
        if user.role != Role.SUPPLIER or user.party_id != probe.supplier_id:
            raise NotFound("deal not found")
        if approval_id is not None:
            raise Forbidden("a supplier cannot execute an approval", "APPROVAL_NOT_HUMAN")
    else:
        escrow_service.authorize(db, user, probe, "CHANGE_BENEFICIARY")
    deal = escrow_service.lock_deal(db, deal_id)
    if deal.status.value in CLOSED_DEALS:
        raise Refusal(f"a deal in status {deal.status.value} cannot change account", "DEAL_CLOSED")
    new = db.get(BankAccount, bank_account_id)
    if new is None or new.party_id != deal.supplier_id:
        raise NotFound("account not found")  # not the supplier's: looks missing
    if new.id == deal.beneficiary_account_id:
        raise Refusal("this is already the receiving account", "BENEFICIARY_UNCHANGED")
    if new.change_requested_via == "email":
        raise Refusal(
            "Setu never changes a payment account because of an email. Ask the supplier to "
            "request it in the supplier portal and verify by video call.",
            "BENEFICIARY_VIA_EMAIL",
        )

    ctx = risk_context.deal_context(
        db,
        deal,
        Action.CHANGE_BENEFICIARY,
        origin,
        amount=deal.goods_value,
        currency=deal.currency,
        beneficiary=new,
        now=now,
    )
    gate = risk_gate.run_gate(
        db,
        user=user,
        deal=deal,
        ctx=ctx,
        approval_action=ApprovalAction.CHANGE_BENEFICIARY,
        params={
            "deal_ref": deal.reference,
            "from_account_id": str(deal.beneficiary_account_id),
            "to_account_id": str(new.id),
            "requested_via": new.change_requested_via or "buyer",
        },
        bank_account_id=new.id,
        approval_id=approval_id,
        now=now,
    )
    if supplier_request and gate.proceed:
        db.rollback()
        raise Forbidden("a supplier cannot change the paid account by itself")
    if not gate.proceed:
        return BeneficiaryOutcome(deal, "PENDING_APPROVAL", gate.approval, gate.decision)

    # Only this deal's pointer moves; other accounts of the supplier (and other buyers' deals that
    # rely on them) are left alone.
    new.status = AccountStatus.ACTIVE
    deal.beneficiary_account_id = new.id
    stale = list(
        db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.deal_id == deal.id,
                ApprovalRequest.action == ApprovalAction.RELEASE_MILESTONE,
                ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.APPROVED)),
            )
        ).all()
    )
    for appr in stale:
        appr.status = ApprovalStatus.CANCELLED
        appr.decided_at = now
    if gate.approval is not None:
        gate.approval.status = ApprovalStatus.EXECUTED
    escrow_service.audit(
        db,
        deal,
        "BENEFICIARY_CHANGED",
        gate.decision.tier,
        {
            "deal_id": str(deal.id),
            "to_account_id": str(new.id),
            "approval_id": str(gate.approval.id) if gate.approval else None,
            "cancelled_release_approvals": [str(a.id) for a in stale],
            "user_id": str(user.id),
        },
        "CHANGED",
        actor=risk_gate.actor_of(origin),
        ts=now,
    )
    db.commit()
    for appr in stale:
        escrow_service.release_approval_closed(db, appr.id)
    return BeneficiaryOutcome(deal, "CHANGED", gate.approval, gate.decision)
