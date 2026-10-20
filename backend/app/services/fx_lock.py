"""FX rate lock (FR-7, Tier 2). Simulated: the rate is today's recorded MOCK rate, held for
`LOCK_HOURS`. The risk engine decides who may lock: a person's own request is the one-tap and the
lock is created inline; the agent can only create an ApprovalRequest. While an ACTIVE lock exists a
conversion release no longer needs the extra Tier 2 for "rate not locked"."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import ApprovalAction, ApprovalStatus, FxLockStatus
from app.db.models import ApprovalRequest, BankAccount, Deal, FxLock
from app.domain import escrow as rules
from app.domain.money import CURRENCIES, ZERO, Currency, q2
from app.errors import DomainError, NotFound
from app.services import escrow as escrow_service
from app.services.analysis import fx_table
from app.services.escrow import Refusal
from app.services.risk import context as risk_context
from app.services.risk import engine
from app.services.risk import gate as risk_gate
from app.services.risk.engine import Action, Origin
from app.services.scope import demo_today

LOCK_HOURS = 24
RATE_DP = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class FxLockOutcome:
    deal: Deal
    outcome: str  # LOCKED | PENDING_APPROVAL
    lock: FxLock | None
    approval: ApprovalRequest | None
    decision: engine.RiskDecision


def lock_fx(
    db: Session,
    user: CurrentUser,
    deal_id: uuid.UUID,
    amount: Decimal | None = None,
    *,
    origin: Origin = Origin.USER_UI,
    approval_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> FxLockOutcome:
    now = now or escrow_service.utcnow()
    probe = db.get(Deal, deal_id)
    if probe is None:
        raise NotFound("deal not found")
    escrow_service.authorize(db, user, probe, "FX_LOCK")
    deal = escrow_service.lock_deal(db, deal_id)
    if deal.status not in rules.FUNDABLE_DEAL and deal.status not in rules.LIVE_DEAL:
        raise Refusal(f"a deal in status {deal.status.value} cannot lock a rate", "DEAL_NOT_ACTIVE")
    acct = db.get(BankAccount, deal.beneficiary_account_id) if deal.beneficiary_account_id else None
    if acct is None or acct.currency not in CURRENCIES:
        raise Refusal("the deal has no receiving account to convert to", "BENEFICIARY_MISSING")
    if acct.currency == deal.currency:
        raise Refusal("the receiving account is in the deal currency", "NO_CONVERSION")
    if amount is None:
        amount = sum(
            (m.amount for m in escrow_service.milestones_of(db, deal.id) if m.released_at is None),
            ZERO,
        )
    if amount <= ZERO or amount != q2(amount):
        raise DomainError("the amount must be positive with at most 2 decimals", "INVALID_AMOUNT")

    gate = risk_gate.run_gate(
        db,
        user=user,
        deal=deal,
        ctx=risk_context.deal_context(
            db, deal, Action.LOCK_FX, origin, amount=amount, currency=deal.currency, now=now
        ),
        approval_action=ApprovalAction.LOCK_FX_RATE,
        params={
            "deal_ref": deal.reference,
            "base": deal.currency,
            "quote": acct.currency,
            "amount": str(q2(amount)),
        },
        bank_account_id=None,
        approval_id=approval_id,
        now=now,
    )
    if not gate.proceed:
        return FxLockOutcome(deal, "PENDING_APPROVAL", None, gate.approval, gate.decision)

    base, quote = cast(Currency, deal.currency), cast(Currency, acct.currency)
    rate = fx_table(db, demo_today(db)).rate(base, quote).quantize(RATE_DP)
    for old in db.scalars(
        select(FxLock).where(FxLock.deal_id == deal.id, FxLock.status == FxLockStatus.ACTIVE)
    ).all():
        old.status = FxLockStatus.CANCELLED
    lock = FxLock(
        id=uuid.uuid4(),
        deal_id=deal.id,
        party_id=deal.buyer_id,
        base=base,
        quote=quote,
        rate=rate,
        amount=q2(amount),
        locked_at=now,
        expires_at=now + timedelta(hours=LOCK_HOURS),
        status=FxLockStatus.ACTIVE,
    )
    db.add(lock)
    if gate.approval is not None:
        gate.approval.status = ApprovalStatus.EXECUTED
    escrow_service.audit(
        db,
        deal,
        "FX_LOCKED",
        gate.decision.tier,
        {
            "deal_id": str(deal.id),
            "base": base,
            "quote": quote,
            "rate": str(rate),
            "amount": str(q2(amount)),
            "approval_id": str(gate.approval.id) if gate.approval else None,
            "user_id": str(user.id),
        },
        "LOCKED",
        actor=risk_gate.actor_of(origin),
        ts=now,
    )
    db.commit()
    return FxLockOutcome(deal, "LOCKED", lock, gate.approval, gate.decision)
