"""FR-5 simulated escrow: fund, release, refund, evidence status. Pure rules live in
app/domain/escrow.py; this module loads rows, takes the locks, posts the ledger and audits.

Concurrency: every money operation locks the deal row (`SELECT ... FOR UPDATE`) first, then the
milestone and escrow rows, re-reads them (`populate_existing`) and only then decides. Two requests
for the same tranche therefore run one after the other, and the second sees the first's result.

Release check order (each failure is audited as TRANCHE_RELEASE_REFUSED and raises a 409 with a
stable `code`):
  a. milestone READY and evidence VERIFIED        EVIDENCE_NOT_VERIFIED / MILESTONE_NOT_READY
  b. escrow balance >= tranche amount              INSUFFICIENT_ESCROW
  c. beneficiary = the supplier's ACTIVE, KYB-checked account   BENEFICIARY_*, KYB_BLOCKED
  d. risk hook (app/security/risk_hook.py)         ALLOW | REQUIRE_APPROVAL | BLOCK
  e. post in one transaction (ledger, escrow, milestone, deal, alerts, audit)

Idempotency: the key is stored on the released milestone. The same key replays the original result
(no second release); a different key on a RELEASED milestone is refused.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import CurrentUser
from app.db.enums import (
    AccountStatus,
    Actor,
    ApprovalAction,
    ApprovalStatus,
    DealStatus,
    EscrowStatus,
    EvidenceStatus,
    FxLockStatus,
    KybStatus,
    LedgerDirection,
    LedgerKind,
    MilestoneStatus,
    Role,
)
from app.db.models import (
    ApprovalRequest,
    BankAccount,
    Deal,
    EscrowAccount,
    FxLock,
    LedgerEntry,
    Milestone,
    Party,
)
from app.domain import escrow as rules
from app.domain.fx import FxRateMissing, FxTable
from app.domain.money import CURRENCIES, ZERO, Currency, Money, q2
from app.errors import Conflict, DomainError, Forbidden, NotFound, ServiceUnavailable
from app.security import risk_hook
from app.security.approvals import approval_binding_hash
from app.security.audit import sha256_hex
from app.security.policy import TIER1_MAX_USD, load_policy
from app.security.risk_hook import ReleaseContext, RiskAction, RiskDecision, RiskHook, RiskResult
from app.services import alerts as alert_service
from app.services import approval_otp, credit_record, hash_registry
from app.services import kyb as kyb_service
from app.services.analysis import fx_table
from app.services.cashflow import load_book
from app.services.risk import adapter as risk_adapter
from app.services.risk import context as risk_context
from app.services.risk import gate as risk_gate
from app.services.risk.context import ACCOUNT_KYB_CHECKS, prior_deal_count
from app.services.risk.engine import Action, Origin
from app.services.scope import demo_today

log = structlog.get_logger("setu.escrow")

PARTNER = "Simulated Escrow Partner"
NEW_ACCOUNT_DAYS = load_policy().new_beneficiary_days
Clock = Callable[[], datetime]
OPEN_APPROVAL = (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Refusal(Conflict):
    """A precondition failed. `code` is stable and machine-readable."""


# --- access -----------------------------------------------------------------------------------


def viewer_role(user: CurrentUser, deal: Deal) -> str | None:
    if user.role == Role.ADMIN:
        return "ADMIN"
    if user.role == Role.JUDGE:
        return "JUDGE"
    if user.party_id is None:
        return None
    if user.role == Role.BUYER and user.party_id == deal.buyer_id:
        return "BUYER"
    if user.role == Role.SUPPLIER and user.party_id == deal.supplier_id:
        return "SUPPLIER"
    return None


def require_view(user: CurrentUser, deal: Deal) -> str:
    """Anyone who may not see the deal gets 404 (no existence oracle)."""
    role = viewer_role(user, deal)
    if role is None:
        raise NotFound("deal not found")
    return role


def require_buyer_side(user: CurrentUser, deal: Deal) -> str:
    """Fund, release and propose: the deal's buyer, or an admin. Suppliers and judges can see the
    deal but not move money."""
    role = require_view(user, deal)
    if role not in ("BUYER", "ADMIN"):
        raise Forbidden("only the buyer of this deal (or an admin) can do this")
    return role


def require_admin(user: CurrentUser, deal: Deal) -> None:
    if require_view(user, deal) != "ADMIN":
        raise Forbidden("only an admin can do this")


def authorize(
    db: Session, user: CurrentUser, deal: Deal, action: str, *, admin: bool = False
) -> None:
    """Role check that leaves an audit row when it says 403 (`<ACTION>_FORBIDDEN`). A caller who
    cannot see the deal gets 404 and no row (no existence oracle)."""
    try:
        require_admin(user, deal) if admin else require_buyer_side(user, deal)
    except Forbidden:
        audit(
            db,
            deal,
            f"{action}_FORBIDDEN",
            0,
            {"deal_id": str(deal.id), "user_id": str(user.id), "role": user.role.value},
            "FORBIDDEN",
        )
        db.commit()
        raise


# --- loading and locking ----------------------------------------------------------------------


def lock_deal(db: Session, deal_id: uuid.UUID) -> Deal:
    deal = db.scalars(
        select(Deal)
        .where(Deal.id == deal_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if deal is None:
        raise NotFound("deal not found")
    return deal


def lock_escrow(db: Session, deal: Deal) -> EscrowAccount | None:
    return db.scalars(
        select(EscrowAccount)
        .where(EscrowAccount.deal_id == deal.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def milestones_of(db: Session, deal_id: uuid.UUID, *, lock: bool = False) -> list[Milestone]:
    stmt = select(Milestone).where(Milestone.deal_id == deal_id).order_by(Milestone.seq)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list(db.scalars(stmt).all())


def ensure_escrow(db: Session, deal: Deal) -> EscrowAccount:
    escrow = lock_escrow(db, deal)
    if escrow is None:
        escrow = EscrowAccount(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:escrow:{deal.id}"),
            deal_id=deal.id,
            currency=deal.currency,
            funded_total=ZERO,
            released_total=ZERO,
            refunded_total=ZERO,
            balance=ZERO,
            status=EscrowStatus.DRAFT,
            simulated=True,
            partner=PARTNER,
            advance_over_20k=False,
        )
        db.add(escrow)
        db.flush()
    return escrow


def verify_invariant(escrow: EscrowAccount) -> None:
    rules.check_invariant(
        escrow.funded_total, escrow.released_total, escrow.refunded_total, escrow.balance
    )


def audit(
    db: Session,
    deal: Deal | None,
    action: str,
    tier: int,
    params: dict[str, Any],
    result: str,
    *,
    actor: str = "user",
    ts: datetime | None = None,
) -> int:
    return write_audit(
        db,
        actor=actor,
        action=action,
        tier=tier,
        params=params,
        result=result,
        ts=ts,
        deal_id=deal.id if deal else None,
    )


def set_milestone_status(m: Milestone, dst: MilestoneStatus) -> None:
    rules.check_milestone_transition(m.status, dst)
    m.status = dst


def set_deal_status(deal: Deal, dst: DealStatus) -> None:
    rules.check_deal_transition(deal.status, dst)
    deal.status = dst


def refresh_ready(ms: list[Milestone], escrow: EscrowAccount | None) -> None:
    """Make exactly the right tranche READY (covered by deposits, previous ones settled)."""
    funded = escrow.funded_total if escrow else ZERO
    target = rules.ready_seq([(m.seq, m.amount, m.status) for m in ms], funded)
    for m in ms:
        if m.seq == target and m.status == MilestoneStatus.PENDING:
            set_milestone_status(m, MilestoneStatus.READY)


def recompute_alerts(db: Session, deal: Deal) -> None:
    buyer = db.get(Party, deal.buyer_id)
    if buyer is not None:
        alert_service.recompute_book(db, load_book(db, buyer))


def _money(amount: Decimal, currency: str) -> Money:
    return Money(amount, cast(Currency, currency))


def _post(
    db: Session,
    deal: Deal,
    txn: str,
    kind: LedgerKind,
    postings: list[rules.Posting],
    memo: str,
    now: datetime,
    *,
    milestone: Milestone | None = None,
    settlement: rules.Settlement | None = None,
) -> list[LedgerEntry]:
    rules.assert_balanced(postings)
    rows = []
    for p in postings:
        side = "dr" if p.direction == LedgerDirection.DEBIT else "cr"
        rows.append(
            LedgerEntry(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:ledger:{txn}:{side}"),
                txn_ref=txn,
                deal_id=deal.id,
                account=p.account,
                direction=p.direction,
                amount=p.amount.amount,
                currency=p.amount.currency,
                memo=f"Simulated · {memo}"[:200],
                posted_at=now,
                simulated=True,
                kind=kind,
                milestone_id=milestone.id if milestone else None,
                fx_rate=settlement.rate if settlement else None,
                counter_amount=settlement.counter.amount
                if settlement and settlement.counter
                else None,
                counter_currency=settlement.counter.currency
                if settlement and settlement.counter
                else None,
            )
        )
    db.add_all(rows)
    db.flush()
    return rows


def lock_party(db: Session, party_id: uuid.UUID) -> Party:
    """SELECT ... FOR UPDATE on the party row (always taken after the deal lock): the buyer's cash
    balance is shared by all of its deals, so concurrent fund/refund calls must serialise."""
    p = db.scalars(
        select(Party)
        .where(Party.id == party_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if p is None:
        raise NotFound("party not found")
    return p


def _party(db: Session, party_id: uuid.UUID) -> Party:
    p = db.get(Party, party_id)
    if p is None:
        raise NotFound("party not found")
    return p


def _to_usd(fx: FxTable, amount: Decimal, currency: str) -> Decimal:
    return fx.convert(_money(amount, currency), "USD").amount


# --- fund -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FundOutcome:
    deal: Deal
    escrow: EscrowAccount
    ledger: list[LedgerEntry]
    advance_over_20k: bool


def fund_escrow(
    db: Session,
    user: CurrentUser,
    deal_id: uuid.UUID,
    amount: Decimal | None = None,
    *,
    origin: Origin = Origin.USER_UI,
    approval_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> FundOutcome:
    """Buyer deposits `amount` (deal currency) into the deal's simulated escrow.

    Decision on `amount` (documented in docs/escrow.md): any positive amount up to the goods value
    still undeposited, so the buyer may deposit tranche by tranche (what the seed does) or the full
    value at once. Omitted = the next tranche that is not yet covered. Tranches turn READY as the
    cumulative deposits cover them. `advance_over_20k` is set when the total deposited exceeds
    USD 20,000 (Phase 5.1 makes that a Tier 3 trigger)."""
    now = now or utcnow()
    probe = db.get(Deal, deal_id)
    if probe is None:
        raise NotFound("deal not found")
    authorize(db, user, probe, "FUND")
    deal = lock_deal(db, deal_id)
    escrow = ensure_escrow(db, deal)
    ms = milestones_of(db, deal.id, lock=True)
    if deal.status not in rules.FUNDABLE_DEAL:
        raise Refusal(
            f"a deal in status {deal.status.value} cannot be funded; both parties must confirm "
            "the milestone schedule first",
            "DEAL_NOT_FUNDABLE",
        )
    remaining = deal.goods_value - escrow.funded_total
    if remaining <= ZERO:
        raise Refusal("the escrow already holds the full goods value", "ALREADY_FULLY_FUNDED")
    deposit = amount
    if deposit is None:
        deposit = rules.default_deposit([(m.amount, m.status) for m in ms], escrow.funded_total)
    if deposit <= ZERO:
        raise DomainError("the deposit must be greater than 0", "INVALID_AMOUNT")
    if deposit != q2(deposit):
        raise DomainError("the deposit may have at most 2 decimal places", "INVALID_AMOUNT")
    if deposit > remaining:
        raise Refusal(
            f"the deposit exceeds the goods value still to be funded ({q2(remaining)})",
            "AMOUNT_EXCEEDS_GOODS_VALUE",
        )

    gate = risk_gate.run_gate(
        db,
        user=user,
        deal=deal,
        ctx=risk_context.deal_context(
            db, deal, Action.FUND_ESCROW, origin, amount=deposit, currency=deal.currency
        ),
        approval_action=ApprovalAction.FUND_ESCROW,
        params={
            "deal_ref": deal.reference,
            "amount": str(q2(deposit)),
            "currency": deal.currency,
        },
        approval_id=approval_id,
        now=now,
    )
    if not gate.proceed:
        assert gate.approval is not None
        raise risk_gate.ApprovalPending(gate.approval, gate.decision)

    buyer = lock_party(db, deal.buyer_id)
    fx = fx_table(db, demo_today(db))
    if buyer.cash_balance is not None:
        cash_ccy = cast(Currency, buyer.cash_currency or deal.currency)
        needed = fx.convert(_money(deposit, deal.currency), cash_ccy).amount
        if buyer.cash_balance < needed:
            raise Refusal("the buyer's cash balance is below the deposit", "INSUFFICIENT_CASH")
        buyer.cash_balance = buyer.cash_balance - q2(needed)

    n = (
        db.scalar(
            select(func.count(func.distinct(LedgerEntry.txn_ref))).where(
                LedgerEntry.deal_id == deal.id, LedgerEntry.kind == LedgerKind.FUND
            )
        )
        or 0
    )
    rows = _post(
        db,
        deal,
        f"{deal.reference}:fund:t{n + 1}",
        LedgerKind.FUND,
        rules.fund_postings(deal.reference, buyer.code, _money(deposit, deal.currency)),
        f"buyer funds {q2(deposit)} {deal.currency} into escrow",
        now,
    )
    escrow.funded_total += deposit
    escrow.balance += deposit
    if escrow.status == EscrowStatus.DRAFT:
        escrow.status = EscrowStatus.FUNDED
    escrow.advance_over_20k = rules.over_advance_limit(
        _to_usd(fx, escrow.funded_total, deal.currency), TIER1_MAX_USD
    )
    if deal.status == DealStatus.CONFIRMED:
        set_deal_status(deal, DealStatus.FUNDED)
        deal.funded_on = demo_today(db)
    refresh_ready(ms, escrow)
    verify_invariant(escrow)
    recompute_alerts(db, deal)
    if gate.approval is not None:
        gate.approval.status = ApprovalStatus.EXECUTED
    audit(
        db,
        deal,
        "ESCROW_FUNDED",
        0,
        {
            "deal_id": str(deal.id),
            "amount": str(q2(deposit)),
            "currency": deal.currency,
            "funded_total": str(q2(escrow.funded_total)),
            "advance_over_20k": escrow.advance_over_20k,
            "user_id": str(user.id),
        },
        "FUNDED",
        ts=now,
    )
    db.commit()
    log.info("escrow_funded", deal=deal.reference, advance_over_20k=escrow.advance_over_20k)
    return FundOutcome(deal, escrow, rows, escrow.advance_over_20k)


# --- evidence ---------------------------------------------------------------------------------


def set_evidence_status(
    db: Session,
    milestone_id: uuid.UUID,
    status: EvidenceStatus,
    *,
    actor: CurrentUser | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> Milestone:
    """Record the evidence verdict for a tranche. Internal: Phase 14's document pipeline calls this
    once every required document passed (VERIFIED) or something failed. Not exposed to the LLM, and
    the HTTP wrapper is dev/test only."""
    probe = db.get(Milestone, milestone_id)
    if probe is None:
        raise NotFound("milestone not found")
    deal = lock_deal(db, probe.deal_id)
    ms = db.scalars(
        select(Milestone)
        .where(Milestone.id == milestone_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if ms.status in rules.SETTLED:
        raise Refusal("this tranche is already settled", "MILESTONE_SETTLED")
    previous = ms.evidence_status
    ms.evidence_status = status
    audit(
        db,
        deal,
        "EVIDENCE_STATUS_SET",
        0,
        {
            "milestone_id": str(ms.id),
            "seq": ms.seq,
            "from": previous.value,
            "to": status.value,
            "user_id": str(actor.id) if actor else None,
        },
        status.value,
        actor="user" if actor else "system",
        ts=now,
    )
    if commit:
        db.commit()
    return ms


# --- release ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Beneficiary:
    account: BankAccount
    currency: Currency
    kyb_status: str
    recently_opened: bool
    kyb_account_warning: bool = False
    sanctions_hit: bool = False


@dataclass(slots=True)
class ReleaseOutcome:
    deal: Deal
    milestone: Milestone
    outcome: str  # RELEASED | PENDING_APPROVAL
    replay: bool = False
    ledger: list[LedgerEntry] = field(default_factory=list)
    approval: ApprovalRequest | None = None
    risk: RiskResult | None = None


def _refuse(
    db: Session,
    deal: Deal,
    ms: Milestone,
    user: CurrentUser,
    code: str,
    detail: str,
    now: datetime,
) -> Refusal:
    """Audit the refusal (it commits only that row) and return the exception to raise."""
    audit(
        db,
        deal,
        "TRANCHE_RELEASE_REFUSED",
        0,
        {"milestone_id": str(ms.id), "seq": ms.seq, "code": code, "user_id": str(user.id)},
        f"REFUSED:{code}",
        ts=now,
    )
    db.commit()
    return Refusal(detail, code)


class _Reject(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def find_beneficiary(db: Session, deal: Deal, supplier: Party, today_: date) -> Beneficiary:
    acct = db.get(BankAccount, deal.beneficiary_account_id) if deal.beneficiary_account_id else None
    if acct is None:
        raise _Reject("BENEFICIARY_MISSING", "the deal has no receiving account")
    if acct.party_id != supplier.id:
        raise _Reject("BENEFICIARY_NOT_SUPPLIERS", "the receiving account is not the supplier's")
    if acct.status != AccountStatus.ACTIVE:
        raise _Reject(
            "BENEFICIARY_NOT_ACTIVE",
            f"the receiving account is {acct.status.value}; only an ACTIVE account can be paid "
            "(a beneficiary change needs its own approval)",
        )
    if supplier.kyb_status == KybStatus.FAILED:
        raise _Reject("KYB_BLOCKED", "the supplier failed KYB and is blocked")
    kyb = kyb_service.evaluate(db, supplier, deal=deal)
    if kyb.status == "BLOCKED":
        raise _Reject("KYB_BLOCKED", "the supplier is blocked by the KYB checks")
    if acct.currency not in CURRENCIES:
        raise _Reject("BENEFICIARY_CURRENCY", f"cannot settle in {acct.currency}")
    failing = {c.code for c in kyb.checks if c.status != "PASS"}
    return Beneficiary(
        acct,
        cast(Currency, acct.currency),
        kyb.status,
        (today_ - acct.first_seen_on).days < NEW_ACCOUNT_DAYS,
        kyb_account_warning=bool(failing & ACCOUNT_KYB_CHECKS),
        sanctions_hit="SANCTIONS_SCREEN" in failing,
    )


def _active_fx_lock(db: Session, deal: Deal, now: datetime, quote: str, amount: Decimal) -> bool:
    return (
        db.scalar(
            select(FxLock.id)
            .where(
                FxLock.deal_id == deal.id,
                FxLock.status == FxLockStatus.ACTIVE,
                FxLock.expires_at > now,
                FxLock.quote == quote,
                FxLock.amount >= amount,
            )
            .limit(1)
        )
        is not None
    )


def release_params(
    deal: Deal, ms: Milestone, acct: BankAccount, settlement_currency: str
) -> dict[str, Any]:
    """What a release approval authorises. Same shape as the seeded Tier 2 approval."""
    return {
        "deal_ref": deal.reference,
        "milestone_seq": ms.seq,
        "amount": str(q2(ms.amount)),
        "currency": ms.currency,
        "beneficiary_account_id": str(acct.id),
        "pay_currency": settlement_currency,
    }


def _binding(
    deal: Deal, ms: Milestone, acct: BankAccount, tier: int, params: dict[str, Any]
) -> str:
    return approval_binding_hash(
        action=ApprovalAction.RELEASE_MILESTONE.value,
        tier=tier,
        deal_id=deal.id,
        milestone_id=ms.id,
        bank_account_id=acct.id,
        params=params,
    )


def _pending_approval(db: Session, ms: Milestone) -> ApprovalRequest | None:
    return db.scalars(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.milestone_id == ms.id,
            ApprovalRequest.action == ApprovalAction.RELEASE_MILESTONE,
            ApprovalRequest.status.in_(OPEN_APPROVAL),
        )
        .order_by(ApprovalRequest.tier.desc(), ApprovalRequest.created_at.desc())
    ).first()


def open_tier3(db: Session, deal: Deal, supplier: Party) -> ApprovalRequest | None:
    """An undecided or approved-but-unexecuted Tier 3 approval on this deal or on any of the
    supplier's accounts (e.g. a beneficiary change): money must not move meanwhile."""
    accounts = select(BankAccount.id).where(BankAccount.party_id == supplier.id)
    return db.scalars(
        select(ApprovalRequest)
        .join(Deal, Deal.id == ApprovalRequest.deal_id)
        .where(
            Deal.buyer_id == deal.buyer_id,  # another buyer's request must not freeze this one
            ApprovalRequest.tier == 3,
            ApprovalRequest.status.in_(OPEN_APPROVAL),
            or_(ApprovalRequest.deal_id == deal.id, ApprovalRequest.bank_account_id.in_(accounts)),
        )
        .limit(1)
    ).first()


def _release_ledger(db: Session, ms: Milestone) -> list[LedgerEntry]:
    return list(
        db.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.milestone_id == ms.id, LedgerEntry.kind == LedgerKind.RELEASE)
            .order_by(LedgerEntry.direction.desc(), LedgerEntry.id)
        ).all()
    )


def release_tranche(
    db: Session,
    milestone_id: uuid.UUID,
    requested_by: CurrentUser,
    idempotency_key: str,
    *,
    approval_id: uuid.UUID | None = None,
    hook: RiskHook | None = None,
    origin: Origin = Origin.USER_UI,
    now: datetime | None = None,
) -> ReleaseOutcome:
    """Release one tranche from escrow to the supplier (simulated). See the module docstring for
    the check order. `approval_id` is for Phase 5.5's execution endpoint only: it carries an
    APPROVED `ApprovalRequest` whose binding hash and tier are re-verified here. `origin` says who
    asked (the HTTP endpoints leave it USER_UI; the agent tools pass AGENT): an agent request can
    only ever create an ApprovalRequest, and an approval can only be executed by a person."""
    now = now or utcnow()
    if approval_id is not None and origin != Origin.USER_UI:
        raise Forbidden("only a person can execute an approval", "APPROVAL_NOT_HUMAN")
    probe = db.get(Milestone, milestone_id)
    if probe is None:
        raise NotFound("milestone not found")
    deal_probe = db.get(Deal, probe.deal_id)
    if deal_probe is None:
        raise NotFound("deal not found")
    authorize(db, requested_by, deal_probe, "RELEASE")

    deal = lock_deal(db, probe.deal_id)
    ms_all = milestones_of(db, deal.id, lock=True)
    ms = next(m for m in ms_all if m.id == milestone_id)
    escrow = lock_escrow(db, deal)

    # Idempotency first: a replay must work even after the deal moved on.
    if ms.status == MilestoneStatus.RELEASED:
        if ms.release_idempotency_key == idempotency_key:
            return ReleaseOutcome(deal, ms, "RELEASED", True, _release_ledger(db, ms))
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "MILESTONE_ALREADY_RELEASED",
            "this tranche has already been released",
            now,
        )
    if ms.status == MilestoneStatus.PENDING_APPROVAL and approval_id is None:
        pending = _pending_approval(db, ms)
        if pending is not None:
            return ReleaseOutcome(deal, ms, "PENDING_APPROVAL", True, [], pending)

    # a. status and evidence
    runnable = (MilestoneStatus.READY, MilestoneStatus.PENDING_APPROVAL)
    if ms.status not in runnable:
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "MILESTONE_NOT_READY",
            f"the tranche is {ms.status.value}, not READY",
            now,
        )
    if deal.status not in rules.LIVE_DEAL:
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "DEAL_NOT_ACTIVE",
            f"the deal is {deal.status.value}; tranches cannot be released",
            now,
        )
    if ms.evidence_status != EvidenceStatus.VERIFIED:
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "EVIDENCE_NOT_VERIFIED",
            "the required evidence has not been verified",
            now,
        )

    from app.services.documents import release_facts  # lazy: documents import this module

    doc_facts = release_facts.facts(db, deal.id, ms.id)
    if doc_facts.pending:
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "DOCUMENTS_PENDING",
            "a document for this tranche has not finished its checks",
            now,
        )

    # b. funds
    if escrow is None or escrow.balance < ms.amount:
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "INSUFFICIENT_ESCROW",
            "the escrow balance is below the tranche amount",
            now,
        )

    # c. beneficiary
    supplier = _party(db, deal.supplier_id)
    today_ = demo_today(db)
    try:
        ben = find_beneficiary(db, deal, supplier, today_)
    except _Reject as exc:
        raise _refuse(db, deal, ms, requested_by, exc.code, exc.detail, now) from exc

    if approval_id is None:
        if escrow is not None and escrow.status == EscrowStatus.FROZEN:
            raise _refuse(
                db, deal, ms, requested_by, "ESCROW_FROZEN",
                "the escrow is frozen while an approval or dispute is open", now,
            )  # fmt: skip
        if open_tier3(db, deal, supplier) is not None:
            raise _refuse(
                db, deal, ms, requested_by, "TIER3_APPROVAL_PENDING",
                "a Tier 3 approval is open for this deal or supplier; money cannot move yet", now,
            )  # fmt: skip

    fx = fx_table(db, today_)
    amount = _money(ms.amount, ms.currency)
    try:
        settlement = rules.settle(amount, ben.currency, fx)
    except FxRateMissing as exc:
        raise ServiceUnavailable(f"no FX rate for {ms.currency}/{ben.currency}") from exc
    prior = prior_deal_count(db, deal)

    fx_lock_missing = settlement.currency != ms.currency and not _active_fx_lock(
        db, deal, now, settlement.currency, ms.amount
    )

    # d. risk hook
    context = ReleaseContext(
        deal_id=deal.id,
        deal_ref=deal.reference,
        milestone_id=ms.id,
        milestone_seq=ms.seq,
        amount=q2(ms.amount),
        currency=ms.currency,
        amount_usd=_to_usd(fx, ms.amount, ms.currency),  # unrounded: never round a limit away
        settlement_currency=ben.currency,
        fx_rate=settlement.rate,
        beneficiary_account_id=ben.account.id,
        beneficiary_status=ben.account.status.value,
        beneficiary_verified=ben.account.verified,
        beneficiary_changed_recently=ben.recently_opened,
        supplier_kyb_status=ben.kyb_status,
        supplier_deal_count=prior,
        evidence_status=ms.evidence_status.value,
        escrow_balance=q2(escrow.balance),
        advance_over_20k=escrow.advance_over_20k,
        requested_by_user_id=requested_by.id,
        requested_by_role=requested_by.role.value,
        document_instruction=doc_facts.instruction,
        document_duplicate=doc_facts.duplicate,
        origin=origin.value,
        buyer_id=str(deal.buyer_id),
        supplier_id=str(deal.supplier_id),
        max_document_fraud_score=doc_facts.max_score,
        any_document_warning=doc_facts.warning,
        any_document_failed=doc_facts.failed,
        sanctions_hit=ben.sanctions_hit,
        kyb_account_warning=ben.kyb_account_warning,
        fx_lock_missing=fx_lock_missing,
    )
    evaluate = hook or risk_hook.get_hook() or risk_adapter.evaluate_release
    result = risk_hook.normalise(evaluate(RiskAction.RELEASE_TRANCHE, context))
    if (
        origin != Origin.USER_UI and approval_id is None and result.decision == RiskDecision.ALLOW
    ):  # belt and braces: whatever the hook said, a non-human origin never auto-executes
        result = result.model_copy(
            update={"decision": RiskDecision.REQUIRE_APPROVAL, "tier": max(result.tier, 2)}
        )
    decision = risk_adapter.to_decision(result, context)
    risk_gate.record(
        db,
        ctx=risk_adapter.release_risk_context(context),
        decision=decision,
        user=requested_by,
        deal=deal,
        milestone_id=ms.id,
        now=now,
    )
    params = release_params(deal, ms, ben.account, ben.currency)

    if result.decision == RiskDecision.BLOCK:
        risk_gate.block_alert(db, deal, decision, ms.id)
        raise _refuse(
            db,
            deal,
            ms,
            requested_by,
            "RELEASE_BLOCKED",
            "the risk engine blocked this release: "
            + "; ".join(r.message for r in result.reasons)[:200],
            now,
        )

    approval: ApprovalRequest | None = None
    if approval_id is not None:
        other = open_tier3(db, deal, supplier)
        if other is not None and other.id != approval_id:
            raise _refuse(
                db, deal, ms, requested_by, "TIER3_APPROVAL_PENDING",
                "another Tier 3 approval is open for this deal or supplier; money cannot move yet",
                now,
            )  # fmt: skip
        approval = _verify_approval(db, approval_id, deal, ms, ben.account, params, result, now)
    elif result.decision == RiskDecision.REQUIRE_APPROVAL:
        return _request_approval(
            db, deal, ms, escrow, ben.account, params, result, requested_by, now, origin
        )
    else:
        pending = _pending_approval(db, ms)
        if pending is not None:  # never ALLOW past a human approval that is still open
            if ms.status == MilestoneStatus.READY:
                set_milestone_status(ms, MilestoneStatus.PENDING_APPROVAL)
                audit(
                    db, deal, "RELEASE_PENDING_APPROVAL_RESYNC", pending.tier,
                    {"milestone_id": str(ms.id), "approval_id": str(pending.id),
                     "user_id": str(requested_by.id)},
                    "PENDING_APPROVAL", ts=now,
                )  # fmt: skip
                db.commit()
            return ReleaseOutcome(deal, ms, "PENDING_APPROVAL", True, [], pending, result)

    # e. post
    return _post_release(
        db,
        deal,
        ms,
        ms_all,
        escrow,
        supplier,
        settlement,
        result,
        requested_by,
        idempotency_key,
        approval,
        now,
    )


def _verify_approval(
    db: Session,
    approval_id: uuid.UUID,
    deal: Deal,
    ms: Milestone,
    acct: BankAccount,
    params: dict[str, Any],
    result: RiskResult,
    now: datetime,
) -> ApprovalRequest:
    """An approval authorises exactly what it was bound to; tier and params are recomputed now."""
    appr = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
    ).first()

    def bad(code: str, detail: str) -> Refusal:
        return Refusal(detail, code)

    if appr is None or appr.milestone_id != ms.id or appr.deal_id != deal.id:
        raise bad("APPROVAL_MISMATCH", "this approval does not belong to this tranche")
    if appr.action != ApprovalAction.RELEASE_MILESTONE or appr.status != ApprovalStatus.APPROVED:
        raise bad("APPROVAL_NOT_APPROVED", "the approval has not been approved")
    if appr.params != params or appr.bank_account_id != acct.id:
        raise bad("APPROVAL_PARAMS_CHANGED", "the tranche changed after it was approved")
    if appr.params_hash != _binding(deal, ms, acct, appr.tier, appr.params):
        raise bad("APPROVAL_HASH_MISMATCH", "the approval no longer matches what was approved")
    if result.tier > appr.tier:
        raise bad("APPROVAL_TIER_STALE", "the release now needs a higher approval tier")
    if appr.cooling_off_until is not None and appr.cooling_off_until > now:
        raise bad("COOLING_OFF", "the cooling-off period has not ended")
    return appr


def _request_approval(
    db: Session,
    deal: Deal,
    ms: Milestone,
    escrow: EscrowAccount,
    acct: BankAccount,
    params: dict[str, Any],
    result: RiskResult,
    user: CurrentUser,
    now: datetime,
    origin: Origin = Origin.USER_UI,
) -> ReleaseOutcome:
    """Park the tranche: milestone PENDING_APPROVAL plus an ApprovalRequest bound to the exact
    release. No ledger entry. A tier 3 request freezes the escrow until it is decided."""
    existing = _pending_approval(db, ms)
    tier = result.tier
    if existing is not None and existing.tier < tier:
        existing.status = ApprovalStatus.CANCELLED  # superseded by a stricter request
        existing.decided_at = now
        audit(
            db, deal, "APPROVAL_SUPERSEDED", existing.tier,
            {"approval_id": str(existing.id), "by_tier": tier}, "CANCELLED", ts=now,
        )  # fmt: skip
        existing = None
    if existing is None:
        binding = _binding(deal, ms, acct, tier, params)
        existing = ApprovalRequest(
            id=uuid.uuid4(),
            key=f"approval:{deal.reference}:release-m{ms.seq}:{binding[:12]}:{uuid.uuid4().hex[:8]}",
            deal_id=deal.id,
            milestone_id=ms.id,
            bank_account_id=acct.id,
            action=ApprovalAction.RELEASE_MILESTONE,
            tier=tier,
            params=params,
            params_hash=binding,
            reasons=[r.model_dump() for r in result.reasons],
            status=ApprovalStatus.PENDING,
            requested_by=Actor.LLM if origin == Origin.AGENT else Actor.USER,
            requested_by_user_id=user.id if origin == Origin.USER_UI else None,
            otp_required=tier == 3,
            cooling_off_until=approval_otp.cooling_off_until(now, tier),
            created_at=now,
        )
        db.add(existing)
    if ms.status == MilestoneStatus.READY:
        set_milestone_status(ms, MilestoneStatus.PENDING_APPROVAL)
    if tier == 3:
        escrow.status = EscrowStatus.FROZEN
    db.flush()
    seq = audit(
        db,
        deal,
        "RELEASE_APPROVAL_REQUESTED",
        tier,
        {
            "milestone_id": str(ms.id),
            "seq": ms.seq,
            "approval_id": str(existing.id),
            "params_hash": existing.params_hash,
            "reasons": [r.code for r in result.reasons],
            "user_id": str(user.id),
        },
        f"PENDING_APPROVAL:T{tier}",
        ts=now,
    )
    if existing.context_hash is None and existing.otp_hash is None and existing.expires_at is None:
        approval_otp.on_created(
            db,
            existing,
            deal,
            context_hash=result.context_hash,
            now=now,
            actor="llm" if origin == Origin.AGENT else "user",
            audit_seq=seq,
            summary=(result.explanation_en, result.explanation_bn),
        )
    db.commit()
    return ReleaseOutcome(deal, ms, "PENDING_APPROVAL", False, [], existing, result)


def release_approval_closed(db: Session, approval_id: uuid.UUID) -> None:
    """For Phase 5.5: when a release approval is rejected, cancelled or expired, the tranche goes
    back to READY and a frozen escrow is thawed."""
    appr = db.get(ApprovalRequest, approval_id)
    if appr is None or appr.milestone_id is None or appr.deal_id is None:
        raise NotFound("approval not found")
    if appr.status in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED):
        raise Refusal("the approval is still open or already executed", "APPROVAL_STILL_OPEN")
    deal = lock_deal(db, appr.deal_id)
    ms = db.scalars(
        select(Milestone).where(Milestone.id == appr.milestone_id).with_for_update()
    ).one()
    escrow = lock_escrow(db, deal)
    if ms.status == MilestoneStatus.PENDING_APPROVAL and _pending_approval(db, ms) is None:
        set_milestone_status(ms, MilestoneStatus.READY)
    if (
        escrow is not None
        and escrow.status == EscrowStatus.FROZEN
        and deal.status != DealStatus.DISPUTED
    ):
        escrow.status = (
            EscrowStatus.TRANCHE_RELEASED if escrow.released_total > 0 else EscrowStatus.FUNDED
        )
    audit(
        db,
        deal,
        "RELEASE_APPROVAL_CLOSED",
        appr.tier,
        {"approval_id": str(appr.id), "status": appr.status.value},
        appr.status.value,
    )
    db.commit()


def _post_release(
    db: Session,
    deal: Deal,
    ms: Milestone,
    ms_all: list[Milestone],
    escrow: EscrowAccount,
    supplier: Party,
    settlement: rules.Settlement,
    result: RiskResult,
    user: CurrentUser,
    key: str,
    approval: ApprovalRequest | None,
    now: datetime,
) -> ReleaseOutcome:
    amount = _money(ms.amount, ms.currency)
    rows = _post(
        db,
        deal,
        f"{deal.reference}:release:m{ms.seq}",
        LedgerKind.RELEASE,
        rules.release_postings(deal.reference, supplier.code, amount),
        f"release milestone {ms.seq} to supplier",
        now,
        milestone=ms,
        settlement=settlement,
    )
    escrow.balance -= ms.amount
    escrow.released_total += ms.amount
    set_milestone_status(ms, MilestoneStatus.RELEASED)
    ms.released_at = now
    ms.release_idempotency_key = key
    if approval is not None:
        approval.status = ApprovalStatus.EXECUTED
    all_settled = all(m.status in rules.SETTLED for m in ms_all)
    for status in rules.release_path(deal.status, ms.trigger, all_settled):
        set_deal_status(deal, status)
    if deal.status == DealStatus.COMPLETED:
        deal.completed_on = demo_today(db)
        hash_registry.release_for_deal(db, deal.id, now=now)
        credit_record.issue(db, deal, ms_all, deal.completed_on.isoformat(), now)
    escrow.status = (
        EscrowStatus.COMPLETED
        if all_settled and escrow.balance == ZERO
        else EscrowStatus.TRANCHE_RELEASED
    )
    if approval is None and result.tier <= 1:
        risk_gate.tier1_notice(
            db, deal, milestone_id=ms.id, amount=q2(ms.amount), currency=ms.currency,
            to=supplier.legal_name,
        )  # fmt: skip
    refresh_ready(ms_all, escrow)
    verify_invariant(escrow)
    recompute_alerts(db, deal)
    audit(
        db,
        deal,
        "TRANCHE_RELEASED",
        result.tier,
        {
            "milestone_id": str(ms.id),
            "seq": ms.seq,
            "amount": str(q2(ms.amount)),
            "currency": ms.currency,
            "settlement_currency": settlement.currency,
            "fx_rate": str(settlement.rate) if settlement.rate else None,
            "counter_amount": str(settlement.counter.amount) if settlement.counter else None,
            "idempotency_key": key,
            "approval_id": str(approval.id) if approval else None,
            "reasons": [r.code for r in result.reasons],
            "user_id": str(user.id),
        },
        "RELEASED",
        ts=now,
    )
    db.commit()
    log.info("tranche_released", deal=deal.reference, seq=ms.seq, tier=result.tier)
    return ReleaseOutcome(deal, ms, "RELEASED", False, rows, approval, result)


# --- refund -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefundOutcome:
    deal: Deal
    amount: Decimal
    currency: str
    ledger: list[LedgerEntry]


def refund(
    db: Session,
    user: CurrentUser,
    *,
    reason: str,
    milestone_id: uuid.UUID | None = None,
    deal_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> RefundOutcome:
    """Admin / dispute path. A milestone refund returns that funded tranche to the buyer and puts
    the deal in DISPUTED (remaining open tranches FROZEN). A deal refund returns the whole escrow
    balance, REFUNDS the funded unsettled tranches, CANCELS the unfunded ones and cancels the
    deal."""
    if (milestone_id is None) == (deal_id is None):
        raise DomainError("give a milestone or a deal to refund", "INVALID_TARGET")
    now = now or utcnow()
    if milestone_id is not None:
        probe = db.get(Milestone, milestone_id)
        if probe is None:
            raise NotFound("milestone not found")
        deal_id = probe.deal_id
    assert deal_id is not None
    deal_probe = db.get(Deal, deal_id)
    if deal_probe is None:
        raise NotFound("deal not found")
    authorize(db, user, deal_probe, "REFUND", admin=True)

    deal = lock_deal(db, deal_id)
    escrow = lock_escrow(db, deal)
    ms_all = milestones_of(db, deal.id, lock=True)
    if escrow is None or deal.status not in rules.REFUNDABLE_DEAL:
        raise Refusal(
            f"a deal in status {deal.status.value} has nothing to refund", "NOT_REFUNDABLE"
        )
    buyer = lock_party(db, deal.buyer_id)
    fx = fx_table(db, demo_today(db))

    if milestone_id is not None:
        ms = next(m for m in ms_all if m.id == milestone_id)
        covered = sum((m.amount for m in ms_all if m.seq <= ms.seq), ZERO) <= escrow.funded_total
        if (
            ms.status
            not in (MilestoneStatus.READY, MilestoneStatus.PENDING_APPROVAL, MilestoneStatus.FROZEN)
            or not covered
        ):
            raise Refusal("only a funded, unreleased tranche can be refunded", "NOT_REFUNDABLE")
        amount = ms.amount
        txn = f"{deal.reference}:refund:m{ms.seq}"
    else:
        ms = None
        amount = escrow.balance
        txn = f"{deal.reference}:refund:deal"
    if amount <= ZERO or amount > escrow.balance:
        raise Refusal("the escrow balance does not cover this refund", "NOTHING_TO_REFUND")

    rows = _post(
        db,
        deal,
        txn,
        LedgerKind.REFUND,
        rules.refund_postings(deal.reference, buyer.code, _money(amount, deal.currency)),
        f"refund to buyer: {reason}"[:150],
        now,
        milestone=ms,
    )
    escrow.balance -= amount
    escrow.refunded_total += amount
    if buyer.cash_balance is not None:
        cash_ccy = cast(Currency, buyer.cash_currency or deal.currency)
        buyer.cash_balance += q2(fx.convert(_money(amount, deal.currency), cash_ccy).amount)

    for appr in db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.deal_id == deal.id,
            ApprovalRequest.action == ApprovalAction.RELEASE_MILESTONE,
            ApprovalRequest.status.in_(OPEN_APPROVAL),
        )
    ).all():
        appr.status = ApprovalStatus.CANCELLED
        appr.decided_at = now
        audit(
            db, deal, "APPROVAL_CANCELLED_BY_REFUND", appr.tier,
            {"approval_id": str(appr.id), "user_id": str(user.id)}, "CANCELLED", ts=now,
        )  # fmt: skip

    if ms is not None:
        set_milestone_status(ms, MilestoneStatus.REFUNDED)
        for other in ms_all:
            if other.status in (MilestoneStatus.READY, MilestoneStatus.PENDING_APPROVAL):
                set_milestone_status(other, MilestoneStatus.FROZEN)
        if deal.status != DealStatus.DISPUTED:
            set_deal_status(deal, DealStatus.DISPUTED)
        deal.dispute_count += 1
        deal.dispute_reason = reason
        escrow.status = EscrowStatus.FROZEN
    else:
        cumulative = ZERO
        for m in ms_all:
            cumulative += m.amount
            if m.status in rules.SETTLED:
                continue
            funded = cumulative <= escrow.funded_total
            target = MilestoneStatus.REFUNDED if funded else MilestoneStatus.CANCELLED
            if m.status == MilestoneStatus.PENDING and funded:
                set_milestone_status(m, MilestoneStatus.READY)
            set_milestone_status(m, target)
        set_deal_status(deal, DealStatus.CANCELLED)
        hash_registry.release_for_deal(db, deal.id)
        escrow.status = EscrowStatus.REFUNDED
    verify_invariant(escrow)
    recompute_alerts(db, deal)
    audit(
        db,
        deal,
        "ESCROW_REFUNDED",
        0,
        {
            "deal_id": str(deal.id),
            "milestone_id": str(ms.id) if ms else None,
            "amount": str(q2(amount)),
            "currency": deal.currency,
            "reason_hash": sha256_hex(reason),
            "user_id": str(user.id),
        },
        "REFUNDED",
        ts=now,
    )
    db.commit()
    return RefundOutcome(deal, amount, deal.currency, rows)
