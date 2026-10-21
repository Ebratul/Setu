"""FR-5 deals: create (with KYB), propose and confirm the milestone schedule, and the read models
the UI needs (detail, list, ledger, activity) with per-role `can_*` action flags.

Money movement (fund, release, refund) is in app/services/escrow.py. Schedule rules are in
app/domain/escrow.py. Responses never compute: amounts arrive as strings and flags carry a reason.
"""

import contextlib
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit.timeline import describe_entry
from app.auth.deps import CurrentUser, ensure_verified
from app.config import get_settings
from app.db import tenancy
from app.db.enums import (
    ApprovalAction,
    ApprovalStatus,
    CheckStatus,
    ConfirmRole,
    DealStatus,
    DocStatus,
    EvidenceStatus,
    KybStatus,
    LedgerKind,
    MilestoneStatus,
    PartyKind,
    Role,
)
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    BankAccount,
    Deal,
    DealCost,
    Document,
    EscrowAccount,
    KybRun,
    LedgerEntry,
    Milestone,
    MilestoneConfirmation,
    Party,
    User,
)
from app.domain import escrow as rules
from app.domain.money import ZERO, Currency, Money
from app.errors import DomainError, Forbidden, NotFound
from app.schemas.deals import (
    ActionFlag,
    ActivityOut,
    ActivityRow,
    ApprovalRef,
    ConfirmationOut,
    CostOut,
    CreateDealRequest,
    DealActions,
    DealDetail,
    DealList,
    DealListItem,
    EscrowCard,
    EvidenceItem,
    HintOut,
    KybSummary,
    LedgerOut,
    LedgerRow,
    MilestoneActions,
    MilestoneOut,
    NextMilestone,
    ProposeRequest,
    RefundResult,
    ReleaseResult,
    RiskOut,
    SettlementOut,
    TraceItemOut,
)
from app.security.risk_hook import RiskResult
from app.services import escrow as escrow_service
from app.services import kyb as kyb_service
from app.services.analysis import fmt
from app.services.escrow import Refusal
from app.services.risk import context as risk_context
from app.services.risk import gate as risk_gate
from app.services.risk.engine import Action, Origin
from app.services.scope import demo_today

REF_LOCK_KEY = 5_400_002  # pg_advisory_xact_lock: one reference allocator at a time
PARTY_STATUS_KYB = {"VERIFIED": "VERIFIED", "WARNING": "WARNING", "FAILED": "BLOCKED"}
ACTIVITY_LIMIT = 200
MAX_GOODS_VALUE = Decimal(10) ** 12


def _dec(value: str) -> Decimal:
    return Decimal(value)


# --- lookup -----------------------------------------------------------------------------------


def find_deal(db: Session, user: CurrentUser, ref: str) -> Deal:
    """A deal the caller may see, by id or reference. Anything else looks missing."""
    cond = Deal.reference == ref
    with contextlib.suppress(ValueError):
        cond = cond | (Deal.id == uuid.UUID(ref))
    deal = db.scalars(select(Deal).where(cond)).first()
    if deal is None:
        raise NotFound("deal not found")
    escrow_service.require_view(user, deal)
    return deal


def find_milestone(
    db: Session, user: CurrentUser, milestone_id: uuid.UUID
) -> tuple[Milestone, Deal]:
    ms = db.get(Milestone, milestone_id)
    deal = db.get(Deal, ms.deal_id) if ms else None
    if ms is None or deal is None:
        raise NotFound("milestone not found")
    try:
        escrow_service.require_view(user, deal)
    except NotFound as exc:
        raise NotFound("milestone not found") from exc
    return ms, deal


# --- create -----------------------------------------------------------------------------------


def create_deal(db: Session, user: CurrentUser, req: CreateDealRequest) -> Deal:
    """New DRAFT deal with its landed-cost lines, then a KYB run for the supplier on this deal
    (stored as `kyb_run_id`). A buyer creates for its own business; an admin names the buyer."""
    ensure_verified(user)
    if user.role == Role.BUYER and user.party_id is not None:
        if req.buyer_id not in (None, user.party_id):
            raise Forbidden("you can only create deals for your own business")
        buyer_id = user.party_id
    elif user.role == Role.ADMIN:
        if req.buyer_id is None:
            raise DomainError("buyer_id is required for admin users", "BUYER_REQUIRED")
        buyer_id = req.buyer_id
    else:
        escrow_service.audit(
            db,
            None,
            "DEAL_CREATE_FORBIDDEN",
            0,
            {"user_id": str(user.id), "role": user.role.value},
            "FORBIDDEN",
        )
        db.commit()
        raise Forbidden("only buyers and admins can create deals")
    buyer = db.get(Party, buyer_id)
    if buyer is None or buyer.kind != PartyKind.BUYER:
        raise NotFound("buyer not found")
    supplier = db.get(Party, req.supplier_id)
    if supplier is None or supplier.kind != PartyKind.SUPPLIER:
        raise NotFound("supplier not found")
    if get_settings().auth_mode == "neon" and supplier.kyb_status in (
        KybStatus.PENDING,
        KybStatus.FAILED,
    ):
        raise DomainError(
            "this supplier has not passed onboarding verification yet", "SUPPLIER_NOT_VERIFIED"
        )

    quantity, unit_price = _dec(req.quantity), _dec(req.unit_price)
    if quantity <= ZERO or unit_price <= ZERO:
        raise DomainError("quantity and unit price must be greater than 0", "INVALID_AMOUNT")
    goods = Money(quantity * unit_price, cast(Currency, req.currency)).quantized()
    if goods.amount <= ZERO:
        raise DomainError("the goods value rounds to zero", "INVALID_AMOUNT")
    if goods.amount >= MAX_GOODS_VALUE:
        raise DomainError(
            "the goods value is too large (limit 1,000,000,000,000)", "INVALID_AMOUNT"
        )

    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": tenancy.lock_key(REF_LOCK_KEY)})
    today = demo_today(db)
    last = db.scalar(
        select(Deal.reference)
        .where(Deal.reference.like(f"SETU-{today.year}-%"))
        .order_by(Deal.reference.desc())
        .limit(1)
    )
    accounts = list(db.scalars(select(BankAccount).where(BankAccount.party_id == supplier.id)))
    beneficiary = kyb_service.active_account(accounts, None)
    deal = Deal(
        id=uuid.uuid4(),
        reference=rules.next_reference(last, today.year),
        buyer_id=buyer.id,
        supplier_id=supplier.id,
        beneficiary_account_id=beneficiary.id if beneficiary else None,
        title=req.title.strip(),
        hs_code=req.hs_code,
        quantity=quantity,
        unit=req.unit,
        unit_price=unit_price,
        currency=req.currency,
        goods_value=goods.amount,
        incoterm=req.incoterm,
        port_of_loading=req.port_of_loading,
        port_of_discharge=req.port_of_discharge,
        expected_sale_value=_dec(req.expected_sale_value) if req.expected_sale_value else None,
        status=DealStatus.DRAFT,
        opened_on=today,
        dispute_count=0,
    )
    db.add(deal)
    db.flush()
    for c in req.costs:
        db.add(
            DealCost(
                id=uuid.uuid4(),
                deal_id=deal.id,
                kind=c.kind,
                amount=_dec(c.amount),
                currency=c.currency,
                due_on=c.due_on,
                note=c.note,
            )
        )
    escrow_service.audit(
        db,
        deal,
        "DEAL_CREATED",
        0,
        {
            "deal_id": str(deal.id),
            "reference": deal.reference,
            "supplier_id": str(supplier.id),
            "goods_value": str(goods.amount),
            "currency": goods.currency,
            "user_id": str(user.id),
        },
        "DRAFT",
    )
    # verify() commits the deal together with its KYB run, audit rows and alerts. If KYB cannot
    # run (e.g. the sanctions list is unavailable) nothing is saved: fail closed.
    kyb_service.verify(db, user, supplier.id, deal.reference)
    run_id = db.scalar(
        select(KybRun.id)
        .where(KybRun.deal_id == deal.id)
        .order_by(KybRun.checked_at.desc())
        .limit(1)
    )
    deal.kyb_run_id = run_id
    db.commit()
    return deal


# --- schedule ---------------------------------------------------------------------------------


def propose_milestones(
    db: Session,
    user: CurrentUser,
    deal_id: uuid.UUID,
    req: ProposeRequest,
    *,
    origin: Origin = Origin.USER_UI,
    approval_id: uuid.UUID | None = None,
) -> Deal:
    """Create or replace the milestone schedule (DRAFT/PROPOSED/CONFIRMED, nothing deposited yet).
    Replacing resets both confirmations. SR-1 lists schedule creation/change as Tier 2: a person's
    own request here is the one-tap (audited as a RISK_DECISION); from the agent it only creates an
    ApprovalRequest (`ApprovalPending`). Both parties must still confirm."""
    ensure_verified(user)
    probe = db.get(Deal, deal_id)
    if probe is None:
        raise NotFound("deal not found")
    escrow_service.authorize(db, user, probe, "PROPOSE")
    deal = escrow_service.lock_deal(db, deal_id)
    if deal.status not in (DealStatus.DRAFT, DealStatus.PROPOSED, DealStatus.CONFIRMED):
        raise Refusal(
            f"the schedule of a deal in status {deal.status.value} cannot be changed",
            "DEAL_NOT_EDITABLE",
        )
    escrow = escrow_service.lock_escrow(db, deal)
    if escrow is not None and escrow.funded_total > ZERO:
        raise Refusal("money is already in escrow; the schedule is locked", "ESCROW_FUNDED")
    supplier = db.get(Party, deal.supplier_id)
    assert supplier is not None
    if kyb_service.evaluate(db, supplier, deal=deal).status == "BLOCKED":
        raise Refusal("the supplier is blocked by the KYB checks", "KYB_BLOCKED")

    if req.template == "custom":
        percents = [_dec(p) for p in req.percents or []]
    else:
        percents = list(rules.TEMPLATES[req.template])
    plan = rules.plan_milestones(Money(deal.goods_value, cast(Currency, deal.currency)), percents)
    today = demo_today(db)
    gate = risk_gate.run_gate(
        db,
        user=user,
        deal=deal,
        ctx=risk_context.deal_context(
            db,
            deal,
            Action.PROPOSE_MILESTONES,
            origin,
            amount=deal.goods_value,
            currency=deal.currency,
        ),
        approval_action=ApprovalAction.CHANGE_MILESTONE_SCHEDULE,
        params={
            "deal_ref": deal.reference,
            "template": req.template,
            "percents": [str(p) for p in percents],
        },
        approval_id=approval_id,
    )
    if not gate.proceed:
        assert gate.approval is not None
        raise risk_gate.ApprovalPending(gate.approval, gate.decision)

    existing = {m.seq: m for m in escrow_service.milestones_of(db, deal.id, lock=True)}
    for item in plan:
        row = existing.pop(item.seq, None)
        values: dict[str, Any] = {
            "trigger": item.trigger,
            "percent": item.percent,
            "amount": item.amount.amount,
            "currency": deal.currency,
            "due_on": today + timedelta(days=item.due_offset_days),
            "status": MilestoneStatus.PROPOSED,
            "required_evidence": [str(e) for e in item.required_evidence],
            "condition_text": item.condition_text,
            "evidence_status": EvidenceStatus.PENDING,
            "release_idempotency_key": None,
            "released_at": None,
        }
        if row is None:
            db.add(Milestone(id=uuid.uuid4(), deal_id=deal.id, seq=item.seq, **values))
        else:
            for k, v in values.items():
                setattr(row, k, v)
    for extra in existing.values():
        db.delete(extra)
    for c in db.scalars(
        select(MilestoneConfirmation).where(MilestoneConfirmation.deal_id == deal.id)
    ).all():
        db.delete(c)
    escrow_service.set_deal_status(deal, DealStatus.PROPOSED)
    if gate.approval is not None:
        gate.approval.status = ApprovalStatus.EXECUTED
    db.flush()
    escrow_service.audit(
        db,
        deal,
        "MILESTONES_PROPOSED",
        2,
        {
            "deal_id": str(deal.id),
            "percents": [str(p) for p in percents],
            "amounts": [str(i.amount.amount) for i in plan],
            "user_id": str(user.id),
        },
        "PROPOSED",
    )
    db.commit()
    return deal


def _confirm_role(user: CurrentUser, deal: Deal, requested: str | None) -> ConfirmRole:
    role = escrow_service.require_view(user, deal)
    if role == "JUDGE":
        raise Forbidden("this demo user is read-only")
    if role == "ADMIN":
        if requested is None:
            raise DomainError("say which side to confirm for (party_role)", "ROLE_REQUIRED")
        return ConfirmRole(requested)
    if requested not in (None, role):
        raise Forbidden("you can only confirm for your own side")
    return ConfirmRole(role)


def confirm_milestones(
    db: Session,
    user: CurrentUser,
    deal_id: uuid.UUID,
    party_role: str | None,
    *,
    origin: Origin = Origin.USER_UI,
    approval_id: uuid.UUID | None = None,
) -> Deal:
    """Record this party's confirmation of the current schedule (idempotent per party). When both
    BUYER and SUPPLIER have confirmed the deal becomes CONFIRMED and the tranches are locked."""
    ensure_verified(user)
    probe = db.get(Deal, deal_id)
    if probe is None:
        raise NotFound("deal not found")
    try:
        role = _confirm_role(user, probe, party_role)
    except Forbidden:
        escrow_service.audit(
            db,
            probe,
            "CONFIRM_FORBIDDEN",
            0,
            {"deal_id": str(probe.id), "user_id": str(user.id), "role": user.role.value},
            "FORBIDDEN",
        )
        db.commit()
        raise
    deal = escrow_service.lock_deal(db, deal_id)
    if deal.status not in (DealStatus.PROPOSED, DealStatus.CONFIRMED):
        raise Refusal("there is no proposed schedule to confirm", "DEAL_NOT_PROPOSED")
    rows = {
        c.party_role: c
        for c in db.scalars(
            select(MilestoneConfirmation).where(MilestoneConfirmation.deal_id == deal.id)
        ).all()
    }
    if role in rows:  # idempotent
        return deal
    now = escrow_service.utcnow()
    gate = risk_gate.run_gate(
        db,
        user=user,
        deal=deal,
        ctx=risk_context.deal_context(
            db,
            deal,
            Action.CONFIRM_MILESTONES,
            origin,
            amount=deal.goods_value,
            currency=deal.currency,
        ),
        approval_action=ApprovalAction.CONFIRM_MILESTONES,
        params={"deal_ref": deal.reference, "party_role": role.value},
        approval_id=approval_id,
        now=now,
    )
    if not gate.proceed:
        assert gate.approval is not None
        raise risk_gate.ApprovalPending(gate.approval, gate.decision)
    if gate.approval is not None:
        gate.approval.status = ApprovalStatus.EXECUTED
    db.add(
        MilestoneConfirmation(
            id=uuid.uuid4(), deal_id=deal.id, party_role=role, user_id=user.id, confirmed_at=now
        )
    )
    both = {ConfirmRole.BUYER, ConfirmRole.SUPPLIER} <= (set(rows) | {role})
    if both:
        escrow_service.set_deal_status(deal, DealStatus.CONFIRMED)
        for m in escrow_service.milestones_of(db, deal.id, lock=True):
            if m.status == MilestoneStatus.PROPOSED:
                escrow_service.set_milestone_status(m, MilestoneStatus.PENDING)
    escrow_service.audit(
        db,
        deal,
        "MILESTONES_CONFIRMED",
        0,
        {"deal_id": str(deal.id), "party_role": role.value, "user_id": str(user.id)},
        "CONFIRMED" if both else f"CONFIRMED_BY_{role.value}",
        ts=now,
    )
    db.commit()
    return deal


# --- read models ------------------------------------------------------------------------------


def _status_str(value: Any) -> str:
    return str(getattr(value, "value", value))


def _flag(ok: bool, reason: str | None = None) -> ActionFlag:
    return ActionFlag(allowed=ok, reason=None if ok else reason)


def escrow_card(deal: Deal, escrow: EscrowAccount | None) -> EscrowCard:
    funded = escrow.funded_total if escrow else ZERO
    released = escrow.released_total if escrow else ZERO
    refunded = escrow.refunded_total if escrow else ZERO
    balance = escrow.balance if escrow else ZERO
    return EscrowCard(
        deal_id=deal.id,
        exists=escrow is not None,
        currency=deal.currency,  # type: ignore[arg-type]
        partner=escrow.partner if escrow else escrow_service.PARTNER,
        status=_status_str(escrow.status) if escrow else "DRAFT",
        funded=fmt(funded),
        released=fmt(released),
        refunded=fmt(refunded),
        balance=fmt(balance),
        remaining_to_fund=fmt(max(deal.goods_value - funded, ZERO)),
        advance_over_20k=escrow.advance_over_20k if escrow else False,
        invariant_ok=funded == released + refunded + balance,
    )


def _evidence_items(db: Session, ms: Milestone) -> list[EvidenceItem]:
    docs = db.scalars(
        select(Document).where(
            Document.milestone_id == ms.id, Document.status == DocStatus.UPLOADED
        )
    ).all()
    out = []
    for doc_type in ms.required_evidence:
        mine = [d for d in docs if d.doc_type.value == doc_type]
        if ms.evidence_status == EvidenceStatus.VERIFIED:
            status = "VERIFIED"
        elif not mine:
            status = "MISSING"
        elif any(d.check_status == CheckStatus.FAILED for d in mine):
            status = "REJECTED"
        elif any(d.check_status == CheckStatus.WARNING for d in mine):
            status = "FLAGGED"
        elif all(d.check_status == CheckStatus.PASSED for d in mine):
            status = "VERIFIED"
        else:
            status = "PENDING"
        out.append(EvidenceItem(doc_type=doc_type, status=status, documents=len(mine)))  # type: ignore[arg-type]
    return out


def _approval_ref(db: Session, ms: Milestone) -> ApprovalRef | None:
    a = db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.milestone_id == ms.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
        .order_by(ApprovalRequest.created_at.desc())
    ).first()
    return approval_ref(a) if a else None


def approval_ref(a: ApprovalRequest) -> ApprovalRef:
    return ApprovalRef(
        id=a.id,
        key=a.key,
        tier=a.tier,
        status=_status_str(a.status),
        reasons=[str(r.get("message") or r.get("code")) for r in a.reasons],
        otp_required=a.otp_required,
        cooling_off_until=a.cooling_off_until,
    )


def _settlement(db: Session, ms: Milestone) -> SettlementOut | None:
    if ms.status != MilestoneStatus.RELEASED:
        return None
    row = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.milestone_id == ms.id, LedgerEntry.kind == LedgerKind.RELEASE)
        .limit(1)
    ).first()
    if row is None:
        return None
    return SettlementOut(
        currency=(row.counter_currency or row.currency),  # type: ignore[arg-type]
        fx_rate=f"{row.fx_rate:f}" if row.fx_rate is not None else None,
        counter_amount=fmt(row.counter_amount) if row.counter_amount is not None else None,
    )


def milestone_actions(
    role: str, deal: Deal, ms: Milestone, escrow: EscrowAccount | None, covered: bool
) -> MilestoneActions:
    if role not in ("BUYER", "ADMIN"):
        why = "Only the buyer can release a tranche"
        release = _flag(False, why)
    elif ms.status == MilestoneStatus.RELEASED:
        release = _flag(False, "This tranche has already been released")
    elif ms.status == MilestoneStatus.PENDING_APPROVAL:
        release = _flag(False, "Waiting for approval")
    elif ms.status != MilestoneStatus.READY:
        release = _flag(False, "Not ready: deposit the tranche and release the earlier ones first")
    elif deal.status not in rules.LIVE_DEAL:
        release = _flag(False, f"The deal is {deal.status.value}")
    elif ms.evidence_status != EvidenceStatus.VERIFIED:
        release = _flag(False, "The required evidence has not been verified yet")
    elif escrow is None or escrow.balance < ms.amount:
        release = _flag(False, "The escrow balance is below this tranche")
    else:
        release = _flag(True)
    refundable = (
        MilestoneStatus.READY,
        MilestoneStatus.PENDING_APPROVAL,
        MilestoneStatus.FROZEN,
    )
    if role != "ADMIN":
        refund = _flag(False, "Only an admin can refund")
    elif ms.status not in refundable or not covered:
        refund = _flag(False, "Only a funded, unreleased tranche can be refunded")
    else:
        refund = _flag(True)
    return MilestoneActions(can_release=release, can_refund=refund)


def _milestone_out(
    db: Session,
    role: str,
    deal: Deal,
    ms: Milestone,
    escrow: EscrowAccount | None,
    cumulative: Decimal,
) -> MilestoneOut:
    funded = escrow is not None and cumulative <= escrow.funded_total
    return MilestoneOut(
        id=ms.id,
        seq=ms.seq,
        trigger=_status_str(ms.trigger),  # type: ignore[arg-type]
        percent=f"{ms.percent:f}",
        percent_label=f"{format((ms.percent * 100).normalize(), 'f')}%",
        amount=fmt(ms.amount),
        currency=ms.currency,  # type: ignore[arg-type]
        condition_text=ms.condition_text or rules.CONDITIONS[ms.trigger],
        required_evidence=_evidence_items(db, ms),
        evidence_status=_status_str(ms.evidence_status),  # type: ignore[arg-type]
        status=_status_str(ms.status),  # type: ignore[arg-type]
        due_on=ms.due_on,
        released_at=ms.released_at,
        funded=funded,
        settlement=_settlement(db, ms),
        approval=_approval_ref(db, ms),
        can=milestone_actions(role, deal, ms, escrow, funded),
    )


def _next(ms_list: list[Milestone]) -> NextMilestone | None:
    for m in ms_list:
        if m.status not in rules.SETTLED:
            return NextMilestone(
                id=m.id,
                seq=m.seq,
                amount=fmt(m.amount),
                currency=m.currency,  # type: ignore[arg-type]
                status=_status_str(m.status),  # type: ignore[arg-type]
                due_on=m.due_on,
                trigger=_status_str(m.trigger),  # type: ignore[arg-type]
            )
    return None


def _kyb_summary(db: Session, deal: Deal, supplier: Party) -> KybSummary:
    run = db.get(KybRun, deal.kyb_run_id) if deal.kyb_run_id else None
    route = f"/app/suppliers/{supplier.id}"
    if run is not None:
        return KybSummary(
            status=run.status,
            score=run.score,
            run_id=run.id,
            checked_at=run.checked_at,
            reason_codes=list(run.reason_codes),
            supplier_route=route,
        )
    return KybSummary(
        status=PARTY_STATUS_KYB.get(supplier.kyb_status.value, supplier.kyb_status.value),
        score=None,
        run_id=None,
        checked_at=None,
        reason_codes=[],
        supplier_route=route,
    )


def deal_actions(
    role: str,
    deal: Deal,
    escrow: EscrowAccount | None,
    ms_list: list[Milestone],
    ms_out: list[MilestoneOut],
    confirmed: set[ConfirmRole],
    kyb_status: str,
) -> DealActions:
    buyer_side = role in ("BUYER", "ADMIN")
    funded = escrow.funded_total if escrow else ZERO
    if not buyer_side:
        propose = _flag(False, "Only the buyer can propose a schedule")
    elif deal.status not in (DealStatus.DRAFT, DealStatus.PROPOSED, DealStatus.CONFIRMED):
        propose = _flag(False, f"The schedule is locked once the deal is {deal.status.value}")
    elif funded > ZERO:
        propose = _flag(False, "Money is already in escrow")
    elif kyb_status == "BLOCKED":
        propose = _flag(False, "The supplier is blocked by KYB")
    else:
        propose = _flag(True)

    if role == "JUDGE":
        confirm = _flag(False, "This demo user is read-only")
    elif role in ("BUYER", "SUPPLIER") and ConfirmRole(role) in confirmed:
        confirm = _flag(False, "You already confirmed this schedule")
    elif deal.status != DealStatus.PROPOSED:
        confirm = _flag(False, "There is no proposed schedule to confirm")
    elif role == "ADMIN" and len(confirmed) == 2:
        confirm = _flag(False, "Both parties already confirmed")
    else:
        confirm = _flag(True)

    if not buyer_side:
        fund = _flag(False, "Only the buyer can fund the escrow")
    elif deal.status not in rules.FUNDABLE_DEAL:
        fund = _flag(False, "Both parties must confirm the schedule before funding")
    elif deal.goods_value - funded <= ZERO:
        fund = _flag(False, "The escrow already holds the full goods value")
    else:
        fund = _flag(True)

    ready = next((m for m in ms_out if m.status == "READY"), None)
    pending = next((m for m in ms_out if m.status == "PENDING_APPROVAL"), None)
    if ready is not None:
        release = ready.can.can_release
    elif pending is not None:
        release = _flag(False, "Waiting for approval")
    elif not buyer_side:
        release = _flag(False, "Only the buyer can release a tranche")
    else:
        release = _flag(False, "No tranche is ready for release")

    balance = escrow.balance if escrow else ZERO
    if role != "ADMIN":
        refund = _flag(False, "Only an admin can refund")
    elif deal.status not in rules.REFUNDABLE_DEAL or balance <= ZERO:
        refund = _flag(False, "There is nothing in escrow to refund")
    else:
        refund = _flag(True)
    return DealActions(
        can_propose=propose,
        can_confirm=confirm,
        can_fund=fund,
        can_release=release,
        can_refund=refund,
    )


def project_for_supplier(d: DealDetail) -> DealDetail:
    """A supplier sees its deal and the escrow it is paid from, not the buyer's business: expected
    sale value, landed-cost lines, dispute narrative, KYB internals and approval reasons are
    blanked. Fields stay present (null / empty) so the response shape never changes."""
    d.expected_sale_value = None
    d.costs = []
    d.dispute_reason = None
    d.kyb.score = None
    d.kyb.reason_codes = []
    for m in d.milestones:
        if m.approval is not None:
            m.approval.reasons = []
    return d


def detail(db: Session, user: CurrentUser, deal: Deal) -> DealDetail:
    role = escrow_service.require_view(user, deal)
    escrow = db.scalars(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id)).first()
    ms_list = escrow_service.milestones_of(db, deal.id)
    buyer, supplier = db.get(Party, deal.buyer_id), db.get(Party, deal.supplier_id)
    assert buyer is not None and supplier is not None
    cumulative = ZERO
    ms_out = []
    for m in ms_list:
        cumulative += m.amount
        ms_out.append(_milestone_out(db, role, deal, m, escrow, cumulative))
    confs = {
        c.party_role: c
        for c in db.scalars(
            select(MilestoneConfirmation).where(MilestoneConfirmation.deal_id == deal.id)
        ).all()
    }
    names = {
        u.id: u.display_name
        for u in db.scalars(
            select(User).where(User.id.in_([c.user_id for c in confs.values() if c.user_id]))
        ).all()
    }
    acct = db.get(BankAccount, deal.beneficiary_account_id) if deal.beneficiary_account_id else None
    kyb = _kyb_summary(db, deal, supplier)
    costs = db.scalars(select(DealCost).where(DealCost.deal_id == deal.id)).all()
    out = DealDetail(
        viewer_role=role,  # type: ignore[arg-type]
        id=deal.id,
        reference=deal.reference,
        title=deal.title,
        status=_status_str(deal.status),  # type: ignore[arg-type]
        buyer_id=buyer.id,
        buyer_name=buyer.legal_name,
        supplier_id=supplier.id,
        supplier_name=supplier.legal_name,
        beneficiary_account_id=acct.id if acct else None,
        beneficiary_masked=kyb_service.mask_account(acct.account_number) if acct else None,
        settlement_currency=acct.currency if acct else None,  # type: ignore[arg-type]
        hs_code=deal.hs_code,
        quantity=f"{deal.quantity.normalize():f}",
        unit=deal.unit,
        unit_price=fmt(deal.unit_price),
        currency=deal.currency,  # type: ignore[arg-type]
        goods_value=fmt(deal.goods_value),
        incoterm=deal.incoterm,
        port_of_loading=deal.port_of_loading,
        port_of_discharge=deal.port_of_discharge,
        expected_sale_value=fmt(deal.expected_sale_value) if deal.expected_sale_value else None,
        opened_on=deal.opened_on,
        funded_on=deal.funded_on,
        completed_on=deal.completed_on,
        dispute_count=deal.dispute_count,
        dispute_reason=deal.dispute_reason,
        costs=[
            CostOut(
                kind=_status_str(c.kind),  # type: ignore[arg-type]
                amount=fmt(c.amount),
                currency=c.currency,  # type: ignore[arg-type]
                due_on=c.due_on,
                note=c.note,
            )
            for c in costs
        ],
        kyb=kyb,
        milestones=ms_out,
        confirmations=[
            ConfirmationOut(
                party_role=r.value,  # type: ignore[arg-type]
                confirmed=r in confs,
                confirmed_at=confs[r].confirmed_at if r in confs else None,
                confirmed_by=names.get(confs[r].user_id)
                if r in confs and confs[r].user_id
                else None,
            )
            for r in (ConfirmRole.BUYER, ConfirmRole.SUPPLIER)
        ],
        escrow=escrow_card(deal, escrow),
        next_milestone=_next(ms_list),
        can=deal_actions(role, deal, escrow, ms_list, ms_out, set(confs), kyb.status),
    )
    return project_for_supplier(out) if role == "SUPPLIER" else out


def list_deals(db: Session, user: CurrentUser, status: DealStatus | None) -> DealList:
    stmt = select(Deal)
    if user.role == Role.BUYER and user.party_id is not None:
        stmt = stmt.where(Deal.buyer_id == user.party_id)
    elif user.role == Role.SUPPLIER and user.party_id is not None:
        stmt = stmt.where(Deal.supplier_id == user.party_id)
    elif user.role not in (Role.ADMIN, Role.JUDGE):
        stmt = stmt.where(Deal.id.is_(None))
    if status is not None:
        stmt = stmt.where(Deal.status == status)
    deals = db.scalars(stmt.order_by(Deal.opened_on.desc(), Deal.reference.desc())).all()
    items = []
    for d in deals:
        escrow = db.scalars(select(EscrowAccount).where(EscrowAccount.deal_id == d.id)).first()
        ms_list = escrow_service.milestones_of(db, d.id)
        buyer, supplier = db.get(Party, d.buyer_id), db.get(Party, d.supplier_id)
        assert buyer is not None and supplier is not None
        card = escrow_card(d, escrow)
        items.append(
            DealListItem(
                id=d.id,
                reference=d.reference,
                title=d.title,
                status=_status_str(d.status),  # type: ignore[arg-type]
                buyer_id=buyer.id,
                buyer_name=buyer.legal_name,
                supplier_id=supplier.id,
                supplier_name=supplier.legal_name,
                goods_value=fmt(d.goods_value),
                currency=d.currency,  # type: ignore[arg-type]
                opened_on=d.opened_on,
                funded=card.funded,
                released=card.released,
                balance=card.balance,
                milestones_total=len(ms_list),
                milestones_released=sum(m.status == MilestoneStatus.RELEASED for m in ms_list),
                next_milestone=_next(ms_list),
                supplier_kyb_status=PARTY_STATUS_KYB.get(
                    supplier.kyb_status.value, supplier.kyb_status.value
                ),
            )
        )
    role = "ADMIN" if user.role == Role.ADMIN else user.role.value
    return DealList(viewer_role=role, deals=items)  # type: ignore[arg-type]


def ledger_row(row: LedgerEntry, seq_by_id: dict[uuid.UUID, int]) -> LedgerRow:
    return LedgerRow(
        id=row.id,
        txn_ref=row.txn_ref,
        kind=_status_str(row.kind),  # type: ignore[arg-type]
        account=row.account,
        direction=_status_str(row.direction),  # type: ignore[arg-type]
        amount=fmt(row.amount),
        currency=row.currency,  # type: ignore[arg-type]
        memo=row.memo,
        posted_at=row.posted_at,
        milestone_id=row.milestone_id,
        milestone_seq=seq_by_id.get(row.milestone_id) if row.milestone_id else None,
        fx_rate=f"{row.fx_rate:f}" if row.fx_rate is not None else None,
        counter_amount=fmt(row.counter_amount) if row.counter_amount is not None else None,
        counter_currency=row.counter_currency,  # type: ignore[arg-type]
        simulated=row.simulated,
    )


def _seqs(db: Session, deal_id: uuid.UUID) -> dict[uuid.UUID, int]:
    return {m.id: m.seq for m in escrow_service.milestones_of(db, deal_id)}


def _supplier_row(row: LedgerRow) -> LedgerRow:
    """The buyer's cash account and refund reasons are not the supplier's business."""
    if row.account.startswith("buyer:"):
        row.account = "buyer:cash"
    if row.kind == "REFUND":
        row.memo = "Simulated · refund to buyer"
    return row


def ledger(db: Session, user: CurrentUser, deal: Deal) -> LedgerOut:
    is_supplier = escrow_service.require_view(user, deal) == "SUPPLIER"
    rows = db.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.deal_id == deal.id)
        .order_by(LedgerEntry.posted_at, LedgerEntry.txn_ref, LedgerEntry.direction.desc())
    ).all()
    balances: dict[str, Decimal] = {}
    for r in rows:
        sign = 1 if r.direction.value == "DEBIT" else -1
        balances[r.txn_ref] = balances.get(r.txn_ref, ZERO) + sign * r.amount
    escrow = db.scalars(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id)).first()
    seqs = _seqs(db, deal.id)
    return LedgerOut(
        deal_id=deal.id,
        reference=deal.reference,
        rows=[
            _supplier_row(ledger_row(r, seqs)) if is_supplier else ledger_row(r, seqs) for r in rows
        ],
        balanced=all(v == ZERO for v in balances.values()),
        escrow=escrow_card(deal, escrow),
    )


def activity(db: Session, user: CurrentUser, deal: Deal) -> ActivityOut:
    is_supplier = escrow_service.require_view(user, deal) == "SUPPLIER"
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.deal_id == deal.id)
        .order_by(AuditLog.seq.desc())
        .limit(ACTIVITY_LIMIT)
    ).all()
    out: list[ActivityRow] = []
    for r in rows:
        # suppliers see what happened, not the buyer-private payload behind it
        text = describe_entry(r.action, {} if is_supplier else r.payload, r.decision)
        out.append(
            ActivityRow(
                seq=r.seq,
                ts=r.ts,
                actor=r.actor.value,  # type: ignore[arg-type]
                action=r.action,
                tier=r.tier,
                result="" if is_supplier else r.decision,
                text_en=text["en"],
                text_bn=text["bn"],
                payload_hash="" if is_supplier else r.payload_hash,
                entry_hash="" if is_supplier else r.entry_hash,
                key_id="" if is_supplier else r.key_id,
            )
        )
    return ActivityOut(deal_id=deal.id, rows=out)


def risk_out(risk: RiskResult) -> RiskOut:
    return RiskOut(
        decision=risk.decision.value,  # type: ignore[arg-type]
        tier=risk.tier,
        reasons=[r.message for r in risk.reasons],
        explanation_en=risk.explanation_en,
        explanation_bn=risk.explanation_bn,
        context_hash=risk.context_hash,
        decided_by=risk.decided_by,
        trace=[TraceItemOut.model_validate(t) for t in risk.trace],
        hints=[HintOut.model_validate(h) for h in risk.hints],
    )


def release_result(
    db: Session, user: CurrentUser, out: escrow_service.ReleaseOutcome
) -> ReleaseResult:
    seqs = _seqs(db, out.deal.id)
    d = detail(db, user, out.deal)
    ms = next(m for m in d.milestones if m.id == out.milestone.id)
    risk: RiskResult | None = out.risk
    notice = None
    if out.outcome == "RELEASED" and not out.replay and risk is not None and risk.tier == 1:
        notice = "Released automatically under Tier 1; this notice is for your records."
    return ReleaseResult(
        outcome=out.outcome,  # type: ignore[arg-type]
        idempotent_replay=out.replay,
        milestone=ms,
        ledger=[ledger_row(r, seqs) for r in out.ledger],
        approval=approval_ref(out.approval) if out.approval and out.outcome != "RELEASED" else None,
        risk=risk_out(risk) if risk else None,
        notice=notice,
        deal=d,
    )


def refund_result(
    db: Session, user: CurrentUser, out: escrow_service.RefundOutcome
) -> RefundResult:
    seqs = _seqs(db, out.deal.id)
    return RefundResult(
        refunded_amount=fmt(out.amount),
        currency=out.currency,  # type: ignore[arg-type]
        ledger=[ledger_row(r, seqs) for r in out.ledger],
        deal=detail(db, user, out.deal),
    )
