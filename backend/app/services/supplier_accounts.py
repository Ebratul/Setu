"""A supplier asks for a new receiving account, in the supplier portal only (SR-6).

1. the account is stored as PENDING_CHANGE (never used for payment),
2. KYB is re-run on it,
3. the same service as the buyer's own change creates a Tier 3 ApprovalRequest for the BUYER.
Nothing moves until the buyer approves it with a code and after the cooling-off.
An e-mail can never start this: see `services/inbox.py`."""

import uuid
from dataclasses import replace
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, ensure_verified, to_current
from app.db.enums import (
    AccountStatus,
    AccountType,
    ApprovalAction,
    ApprovalStatus,
    Role,
    UserStatus,
)
from app.db.models import ApprovalRequest, BankAccount, Deal, Party, User
from app.errors import Forbidden, NotFound
from app.schemas.approvals import (
    AccountChangeIn,
    AccountChangeList,
    AccountChangeRequestOut,
    ChangeStep,
)
from app.services import beneficiary
from app.services import escrow as escrow_service
from app.services import kyb as kyb_service
from app.services.escrow import Refusal
from app.services.risk.gate import RiskBlocked
from app.services.scope import demo_today

CLOSED_DEALS = ("COMPLETED", "CANCELLED")
OPEN = (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)


def _system_admin(db: Session) -> CurrentUser:
    """The platform's own KYB re-check on a supplier's request. Runs are recorded against a real
    admin row (preferring an ACTIVE, non-demo one), but the actor is an explicit system actor
    that passes the user gates (status, 2FA, demo flags): it is never a person's session."""
    admins = list(db.scalars(select(User).where(User.role == Role.ADMIN).order_by(User.email)))
    if not admins:
        raise NotFound("no admin account to run the KYB re-check")
    row = next((a for a in admins if a.status == UserStatus.ACTIVE and not a.is_demo), admins[0])
    return replace(
        to_current(row),
        account_status=UserStatus.ACTIVE,
        mfa_enabled=True,
        is_demo=False,
        party_blocked=False,
    )


def _label(a: BankAccount) -> str:
    return f"{a.bank_name} · …{a.account_number[-4:]} · {a.currency}"


def _require_supplier(user: CurrentUser) -> uuid.UUID:
    if user.role != Role.SUPPLIER or user.party_id is None:
        raise Forbidden("only a supplier can request a payout account change here")
    return user.party_id


def _approval_for(db: Session, account: BankAccount) -> ApprovalRequest | None:
    return db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.action == ApprovalAction.CHANGE_BENEFICIARY,
            ApprovalRequest.bank_account_id == account.id,
        )
        .order_by(ApprovalRequest.created_at.desc())
    ).first()


def _view(db: Session, account: BankAccount, appr: ApprovalRequest) -> AccountChangeRequestOut:
    deal = db.get(Deal, appr.deal_id) if appr.deal_id else None
    if deal is None:
        raise NotFound("deal not found")
    buyer = db.get(Party, deal.buyer_id)
    status = appr.status
    stage = {
        ApprovalStatus.PENDING: "WAITING_BUYER",
        ApprovalStatus.APPROVED: "WAITING_BUYER",
        ApprovalStatus.EXECUTED: "APPROVED",
        ApprovalStatus.REJECTED: "REJECTED",
        ApprovalStatus.EXPIRED: "EXPIRED",
        ApprovalStatus.LOCKED: "LOCKED",
        ApprovalStatus.CANCELLED: "CANCELLED",
    }[status]
    ended = status in (
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.LOCKED,
        ApprovalStatus.CANCELLED,
    )
    done = status == ApprovalStatus.EXECUTED
    steps = [
        ChangeStep(key="SUBMITTED", state="DONE"),
        ChangeStep(key="KYB", state="DONE"),
        ChangeStep(key="BUYER", state="DONE" if done else "FAILED" if ended else "CURRENT"),
        ChangeStep(key="DONE", state="DONE" if done else "FAILED" if ended else "UPCOMING"),
    ]
    return AccountChangeRequestOut(
        account_id=account.id,
        deal_id=deal.id,
        deal_reference=deal.reference,
        buyer_name=buyer.legal_name if buyer else "",
        account_label=_label(account),
        account_status=account.status.value,  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        tier=appr.tier,
        requested_at=account.change_requested_at,
        decided_at=appr.decided_at,
        steps=steps,
    )


def request_change(
    db: Session, user: CurrentUser, body: AccountChangeIn, *, now: datetime | None = None
) -> AccountChangeRequestOut:
    ensure_verified(user)
    party_id = _require_supplier(user)
    now = now or escrow_service.utcnow()
    deal = db.get(Deal, body.deal_id)
    if deal is None or deal.supplier_id != party_id:
        raise NotFound("deal not found")
    if deal.status.value in CLOSED_DEALS:
        raise Refusal(f"a deal in status {deal.status.value} cannot change account", "DEAL_CLOSED")

    number = body.account_number.strip()
    number = number if number.upper().startswith("SIM-") else f"SIM-{number}"
    existing = db.scalars(
        select(BankAccount).where(
            BankAccount.party_id == party_id,
            BankAccount.account_number == number,
            BankAccount.status != AccountStatus.RETIRED,
        )
    ).first()
    if existing is not None:
        appr = _approval_for(db, existing)
        if existing.status == AccountStatus.PENDING_CHANGE and appr and appr.status in OPEN:
            return _view(db, existing, appr)  # idempotent: the same request is still waiting
        raise Refusal("this account is already on file", "ACCOUNT_EXISTS")

    today = demo_today(db)
    account = BankAccount(
        id=uuid.uuid4(),
        party_id=party_id,
        bank_name=body.bank_name.strip(),
        bank_country=body.bank_country.upper(),
        account_number=number,
        holder_name=body.holder_name.strip(),
        account_type=AccountType(body.account_type),
        currency=body.currency,
        status=AccountStatus.PENDING_CHANGE,
        opened_on=today,  # unknown to us, so treated as brand new (SR-1: < 30 days is Tier 3)
        first_seen_on=today,
        verified=False,
        change_requested_via="portal",
        change_requested_at=now,
    )
    db.add(account)
    db.flush()
    escrow_service.audit(
        db,
        deal,
        "BENEFICIARY_CHANGE_REQUESTED",
        3,
        {
            "deal_id": str(deal.id),
            "account_id": str(account.id),
            "via": "portal",
            "user_id": str(user.id),
        },
        "PENDING_CHANGE",
        ts=now,
    )
    db.commit()

    supplier = db.get(Party, party_id)
    assert supplier is not None
    try:
        kyb_service.verify(db, _system_admin(db), supplier.id, deal.reference, now=now)
    except Exception:
        # never leave a parked account behind that blocks a retry with ACCOUNT_EXISTS
        db.rollback()
        parked = db.get(BankAccount, account.id)
        if parked is not None:
            parked.status = AccountStatus.RETIRED
            db.commit()
        raise

    try:
        out = beneficiary.change_beneficiary(
            db, user, deal.id, account.id, supplier_request=True, now=now
        )
    except RiskBlocked:
        account = db.get(BankAccount, account.id)  # type: ignore[assignment]
        account.status = AccountStatus.RETIRED
        db.commit()
        raise
    assert out.approval is not None
    return _view(db, db.get(BankAccount, account.id), out.approval)  # type: ignore[arg-type]


def list_requests(db: Session, user: CurrentUser) -> AccountChangeList:
    party_id = _require_supplier(user)
    accounts = db.scalars(
        select(BankAccount)
        .where(BankAccount.party_id == party_id, BankAccount.change_requested_via == "portal")
        .order_by(BankAccount.change_requested_at.desc())
    ).all()
    items: list[AccountChangeRequestOut] = []
    for acct in accounts:
        appr = _approval_for(db, acct)
        if appr is not None:
            items.append(_view(db, acct, appr))
    return AccountChangeList(items=items)
