"""Human approval of what the risk engine escalated (SR-1, SR-2, SR-9). Phase 17.

Only these functions (behind `/approvals/*`) execute a Tier 2/3 request, and only for a person:
the deal's buyer, or an admin. The request body carries at most an OTP: the action and its
parameters are whatever was stored when the engine escalated, and the same service function that
created the request executes it, which re-runs the risk engine on fresh facts.

- Tier 3: a 6-digit code (kept as a hash, 5 minutes, 3 wrong tries lock the request) and
  `now >= cooling_off_until`.
- If the world changed so that the action now needs a higher tier, nothing is executed: the old
  request is closed and a new, stricter one is created (`RE_ESCALATED`).
- Idempotent: an executed request answers the same again; a request that was approved but could not
  run (e.g. evidence missing) can be retried without a new code.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import (
    AccountStatus,
    ApprovalAction,
    ApprovalStatus,
    FxLockStatus,
    MemberRole,
    Role,
)
from app.db.models import (
    ApprovalEvent,
    ApprovalRequest,
    BankAccount,
    Deal,
    DemoPhoneMessage,
    Document,
    ForensicFinding,
    FxLock,
    HashRegistry,
    KybCheck,
    Party,
    RiskEvent,
)
from app.domain.money import q2
from app.errors import DomainError, Forbidden, NotFound, ServiceUnavailable
from app.schemas.approvals import (
    ApprovalList,
    ApprovalOut,
    ApproveResult,
    DocumentEvidence,
    EventOut,
    EvidenceSnapshot,
    FxEvidence,
    NotificationsOut,
    ReasonOut,
    SupplierEvidence,
    TimelineOut,
    TimelineStep,
)
from app.schemas.deals import ProposeRequest, TraceItemOut
from app.services import approval_otp, stepup
from app.services import beneficiary as beneficiary_service
from app.services import deals as deals_service
from app.services import escrow as escrow_service
from app.services import fx_lock as fx_lock_service
from app.services.analysis import fx_table
from app.services.escrow import Refusal
from app.services.risk.gate import ApprovalPending, RiskBlocked
from app.services.scope import demo_today

log = structlog.get_logger("setu.approvals")
OPEN = (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
DECIDER_ROLES = ("BUYER", "ADMIN")
FEED_KINDS = (
    "CREATED",
    "APPROVED",
    "EXECUTED",
    "REJECTED",
    "EXPIRED",
    "CANCELLED",
    "LOCKED",
    "BLOCKED",
    "RE_ESCALATED",
)
MAX_RESENDS = 5

ACTION_LABELS = approval_otp.ACTION_LABELS
ENGINE_ACTION = {
    ApprovalAction.RELEASE_MILESTONE: "RELEASE_TRANCHE",
    ApprovalAction.CHANGE_BENEFICIARY: "CHANGE_BENEFICIARY",
    ApprovalAction.FUND_ESCROW: "FUND_ESCROW",
    ApprovalAction.LOCK_FX_RATE: "LOCK_FX",
    ApprovalAction.CONFIRM_MILESTONES: "CONFIRM_MILESTONES",
    ApprovalAction.CHANGE_MILESTONE_SCHEDULE: "PROPOSE_MILESTONES",
}
WHY_PAUSE = (
    "This pause protects you from rushed payment-redirection scams: a fraudster's favourite "
    "trick is urgency. Take the time to check the details.",
    "এই বিরতি তাড়াহুড়োয় পেমেন্ট অন্যত্র পাঠানোর প্রতারণা থেকে আপনাকে রক্ষা করে। বিস্তারিত যাচাই করার সময় নিন।",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _money(amount: str | None, currency: str | None) -> str:
    if not amount:
        return ""
    value = Decimal(amount)
    text = f"{q2(value):,.2f}"
    return f"{currency or ''} {text[:-3] if text.endswith('.00') else text}".strip()


# --- access -------------------------------------------------------------------------------------


def _load(
    db: Session, user: CurrentUser, approval_id: uuid.UUID, *, decide: bool, lock: bool = False
) -> tuple[ApprovalRequest, Deal, str]:
    """404 for a missing request; 403 when the caller may not decide (or, for reading, may not
    see it). A supplier is never the decider of a payment."""
    stmt = select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    appr = db.scalars(stmt.with_for_update() if lock else stmt).first()
    deal = db.get(Deal, appr.deal_id) if appr is not None and appr.deal_id else None
    if appr is None or deal is None:
        raise NotFound("approval not found")
    role = escrow_service.viewer_role(user, deal)
    if decide:
        if user.member_role == MemberRole.VIEWER:
            raise Forbidden("viewers can read but not change anything", code="VIEWER_READ_ONLY")
        if role not in DECIDER_ROLES:
            raise Forbidden("only the buyer of this deal (or an admin) can decide this approval")
    elif role not in ("BUYER", "ADMIN", "JUDGE"):
        raise NotFound("approval not found")
    return appr, deal, _seen_as(user, role or "")


def _seen_as(user: CurrentUser, role: str) -> str:
    """A party VIEWER sees the buyer's approvals but is never a decider."""
    if role == "BUYER" and user.member_role == MemberRole.VIEWER:
        return "VIEWER"
    return role


def _requested_via(appr: ApprovalRequest) -> str | None:
    value = appr.params.get("requested_via")
    return str(value) if value else None


# --- expiry and closing -------------------------------------------------------------------------


def _audit(
    db: Session,
    deal: Deal,
    action: str,
    appr: ApprovalRequest,
    user: CurrentUser | None,
    result: str,
    now: datetime,
    **extra: Any,
) -> int:
    return escrow_service.audit(
        db,
        deal,
        action,
        appr.tier,
        {
            "approval_id": str(appr.id),
            "approval_action": appr.action.value,
            "params_hash": appr.params_hash,
            "user_id": str(user.id) if user else None,
            **extra,
        },
        result,
        actor="user" if user else "system",
        ts=now,
    )


def _parties(deal: Deal, appr: ApprovalRequest) -> list[uuid.UUID | None]:
    out: list[uuid.UUID | None] = [deal.buyer_id]
    if appr.action == ApprovalAction.CHANGE_BENEFICIARY:
        out.append(deal.supplier_id)
    return out


def _close_effects(db: Session, appr: ApprovalRequest, deal: Deal, now: datetime) -> None:
    """After a request ended without executing: thaw the tranche, retire the never-approved
    account. Commits."""
    db.commit()
    if appr.action == ApprovalAction.RELEASE_MILESTONE and appr.milestone_id is not None:
        escrow_service.release_approval_closed(db, appr.id)
    if appr.action == ApprovalAction.CHANGE_BENEFICIARY and appr.bank_account_id is not None:
        acct = db.get(BankAccount, appr.bank_account_id)
        others = db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(
                ApprovalRequest.bank_account_id == appr.bank_account_id,
                ApprovalRequest.id != appr.id,
                ApprovalRequest.status.in_(OPEN),
            )
        )
        if acct is not None and acct.status == AccountStatus.PENDING_CHANGE and not others:
            acct.status = AccountStatus.RETIRED
            db.commit()


def _end(
    db: Session,
    appr: ApprovalRequest,
    deal: Deal,
    user: CurrentUser | None,
    status: ApprovalStatus,
    now: datetime,
    note: str | None = None,
) -> None:
    kind = {
        ApprovalStatus.REJECTED: "REJECTED",
        ApprovalStatus.CANCELLED: "CANCELLED",
        ApprovalStatus.EXPIRED: "EXPIRED",
        ApprovalStatus.LOCKED: "LOCKED",
    }[status]
    appr.status = status
    appr.decided_at = now
    appr.decision_note = (note or "")[:300] or None
    if user is not None and status in (ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED):
        appr.decided_by_user_id = user.id
    seq = _audit(db, deal, f"APPROVAL_{kind}", appr, user, status.value, now)
    label = ACTION_LABELS[appr.action]
    titles = {
        "REJECTED": ("Request rejected", "অনুরোধ প্রত্যাখ্যাত"),
        "CANCELLED": ("Request cancelled", "অনুরোধ বাতিল"),
        "EXPIRED": ("Request expired", "অনুরোধের মেয়াদ শেষ"),
        "LOCKED": ("Request locked after 3 wrong codes", "৩ বার ভুল কোডের পর অনুরোধ লক"),
    }
    approval_otp.emit(
        db,
        kind=kind,
        now=now,
        deal=deal,
        approval=appr,
        parties=_parties(deal, appr),
        tier=appr.tier,
        actor="user" if user else "system",
        title=titles[kind],
        detail=(f"{label[0]} · {deal.reference}", f"{label[1]} · {deal.reference}"),
        audit_seq=seq,
    )
    _close_effects(db, appr, deal, now)


def expire_due(db: Session, now: datetime | None = None) -> int:
    """Close every open request whose time is up. Cheap; called lazily by the read endpoints."""
    now = now or utcnow()
    due = list(
        db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.status.in_(OPEN),
                ApprovalRequest.expires_at.is_not(None),
                ApprovalRequest.expires_at < now,
            )
            .with_for_update(skip_locked=True)
        ).all()
    )
    for appr in due:
        deal = db.get(Deal, appr.deal_id) if appr.deal_id else None
        if deal is None:
            continue
        _end(db, appr, deal, None, ApprovalStatus.EXPIRED, now, "Not decided in time")
    return len(due)


# --- read models --------------------------------------------------------------------------------


def _summary(
    db: Session, appr: ApprovalRequest, deal: Deal
) -> tuple[str | None, str | None, int | None, str | None, str | None]:
    """supplier name, milestone seq, amount, currency, (unused)."""
    supplier = db.get(Party, deal.supplier_id)
    ms_seq = appr.params.get("milestone_seq")
    amount = appr.params.get("amount")
    currency = appr.params.get("currency") or appr.params.get("base")
    if appr.action in (ApprovalAction.CHANGE_BENEFICIARY, ApprovalAction.CONFIRM_MILESTONES):
        amount, currency = None, None
    if appr.action == ApprovalAction.CHANGE_MILESTONE_SCHEDULE:
        amount, currency = str(q2(deal.goods_value)), deal.currency
    return (
        supplier.legal_name if supplier else None,
        int(ms_seq) if ms_seq is not None else None,
        str(amount) if amount is not None else None,
        currency,
        None,
    )


def _what_happens(
    appr: ApprovalRequest, supplier: str | None, seq: int | None, money: str, deal: Deal
) -> tuple[str, str]:
    who = supplier or "the supplier"
    match appr.action:
        case ApprovalAction.RELEASE_MILESTONE:
            return (
                f"{money} for tranche M{seq} moves from escrow to {who} (Simulated).",
                f"এসক্রো থেকে {who}-কে M{seq} কিস্তির {money} যাবে (সিমুলেটেড)।",
            )
        case ApprovalAction.FUND_ESCROW:
            return (
                f"{money} moves from your cash into the escrow of {deal.reference} (Simulated).",
                f"আপনার নগদ থেকে {deal.reference}-এর এসক্রোতে {money} যাবে (সিমুলেটেড)।",
            )
        case ApprovalAction.CHANGE_BENEFICIARY:
            return (
                f"From now on this deal pays {who} into the NEW account. Past payments are not "
                "affected.",
                f"এখন থেকে এই ডিলের পেমেন্ট {who}-এর নতুন অ্যাকাউন্টে যাবে। আগের পেমেন্ট অপরিবর্তিত।",
            )
        case ApprovalAction.LOCK_FX_RATE:
            return (
                f"The USD/CNY rate is fixed for {money} for 24 hours (Simulated).",
                f"২৪ ঘণ্টার জন্য {money}-এর হার স্থির হবে (সিমুলেটেড)।",
            )
        case ApprovalAction.CONFIRM_MILESTONES:
            return (
                "Your confirmation of the milestone schedule is recorded.",
                "মাইলস্টোন সূচিতে আপনার নিশ্চিতকরণ নথিভুক্ত হবে।",
            )
        case _:
            return (
                "The proposed schedule is saved; both parties must still confirm it.",
                "প্রস্তাবিত সূচি সংরক্ষিত হবে; দুই পক্ষকেই নিশ্চিত করতে হবে।",
            )


def _tier3_pause(appr: ApprovalRequest, now: datetime) -> int | None:
    if appr.tier < 3 or appr.cooling_off_until is None:
        return None
    return max(0, int((appr.cooling_off_until - now).total_seconds() + 0.999))


def _blocked_reason(
    appr: ApprovalRequest, role: str, now: datetime, left: int | None
) -> str | None:
    if appr.status not in OPEN:
        return "ALREADY_DECIDED"
    if role not in DECIDER_ROLES:
        return "NOT_DECIDER"
    if appr.expires_at is not None and appr.expires_at < now:
        return "EXPIRED"
    if _requested_via(appr) == "email":
        return "EMAIL_ORIGIN"
    if appr.tier == 3 and left:
        return "COOLING_OFF"
    return None


def to_out(
    db: Session,
    appr: ApprovalRequest,
    deal: Deal,
    role: str,
    now: datetime,
    *,
    with_evidence: bool = False,
) -> ApprovalOut:
    supplier, seq, amount, currency, _ = _summary(db, appr, deal)
    label = ACTION_LABELS[appr.action]
    money = _money(amount, currency)
    what = _what_happens(appr, supplier, seq, money, deal)
    left = _tier3_pause(appr, now)
    blocked = _blocked_reason(appr, role, now, left)
    is_open = appr.status in OPEN
    total = get_settings().cooling_off_seconds if appr.tier == 3 else None
    if appr.tier == 3 and appr.cooling_off_until is not None:
        total = max(1, int((appr.cooling_off_until - appr.created_at).total_seconds()))
    return ApprovalOut(
        id=appr.id,
        action=appr.action.value,
        action_label_en=label[0],
        action_label_bn=label[1],
        what_happens_en=what[0],
        what_happens_bn=what[1],
        tier=appr.tier,
        status=appr.status.value,  # type: ignore[arg-type]
        deal_id=deal.id,
        deal_reference=deal.reference,
        supplier_name=supplier,
        milestone_seq=seq,
        amount=amount,
        currency=currency,
        reasons=[
            ReasonOut(
                code=str(r.get("code")),
                message=str(r.get("message") or r.get("code")),
                message_bn=str(r.get("message_bn") or r.get("message") or r.get("code")),
            )
            for r in appr.reasons
        ],
        requested_by=appr.requested_by.value,
        requested_via=_requested_via(appr),
        otp_required=appr.otp_required,
        created_at=appr.created_at,
        expires_at=appr.expires_at,
        cooling_off_until=appr.cooling_off_until,
        seconds_to_cooling_off_end=left if is_open else None,
        cooling_off_total_seconds=total,
        otp_attempts_left=(
            max(0, get_settings().otp_max_attempts - appr.otp_attempts) if appr.tier == 3 else None
        ),
        otp_sent=appr.otp_hash is not None,
        decided_at=appr.decided_at,
        decision_note=appr.decision_note,
        can_approve=is_open and blocked in (None, "COOLING_OFF"),
        can_reject=is_open and role in DECIDER_ROLES,
        can_cancel=is_open and appr.tier == 3 and role in DECIDER_ROLES,
        blocked_reason=blocked,
        why_pause_en=WHY_PAUSE[0] if appr.tier == 3 else None,
        why_pause_bn=WHY_PAUSE[1] if appr.tier == 3 else None,
        evidence=evidence(db, appr, deal) if with_evidence else None,
    )


def evidence(db: Session, appr: ApprovalRequest, deal: Deal) -> EvidenceSnapshot:
    """One-card summary for the approver. Read-only; nothing here decides anything."""
    today = demo_today(db)
    party = db.get(Party, deal.supplier_id)
    acct_id = appr.bank_account_id or deal.beneficiary_account_id
    acct = db.get(BankAccount, acct_id) if acct_id else None
    supplier: SupplierEvidence | None = None
    if party is not None:
        score = None
        if acct is not None:
            chk = db.scalars(
                select(KybCheck)
                .where(KybCheck.bank_account_id == acct.id)
                .order_by(KybCheck.checked_at.desc())
            ).first()
            score = round(float(chk.score) * 100) if chk is not None else None
        supplier = SupplierEvidence(
            id=party.id,
            name=party.legal_name,
            kyb_status=party.kyb_status.value,
            kyb_score=score,
            account_label=(
                f"{acct.bank_name} · …{acct.account_number[-4:]} · {acct.currency}"
                if acct
                else None
            ),
            account_status=acct.status.value if acct else None,
            account_age_days=(today - acct.first_seen_on).days if acct else None,
        )

    doc_stmt = select(Document).where(Document.deal_id == deal.id)
    if appr.milestone_id is not None:
        doc_stmt = doc_stmt.where(Document.milestone_id == appr.milestone_id)
    docs = list(db.scalars(doc_stmt.order_by(Document.uploaded_at.desc().nullslast()).limit(8)))
    out_docs: list[DocumentEvidence] = []
    any_dup = False
    for d in docs:
        findings = list(
            db.scalars(select(ForensicFinding).where(ForensicFinding.document_id == d.id))
        )
        issues = [f.check_code for f in findings if f.status.value != "PASS"]
        dup = "DUPLICATE_HASH" in issues
        any_dup = any_dup or dup
        registered = (
            (
                d.sha256 is not None
                and db.scalar(
                    select(func.count())
                    .select_from(HashRegistry)
                    .where(HashRegistry.sha256 == d.sha256, HashRegistry.status == "ACTIVE")
                )
            )
            or 0
        ) > 0
        out_docs.append(
            DocumentEvidence(
                id=d.id,
                doc_type=d.doc_type.value,
                file_name=d.file_name,
                status=d.status.value,
                check_status=d.check_status.value,
                issues=issues,
                registry="DUPLICATE" if dup else ("REGISTERED" if registered else "NEW"),
                sha_short=d.sha256[:10] if d.sha256 else None,
            )
        )
    registry = "NOT_APPLICABLE" if not out_docs else ("DUPLICATE_FOUND" if any_dup else "CLEAR")

    fx: FxEvidence | None = None
    quote = appr.params.get("pay_currency") or appr.params.get("quote")
    base = appr.params.get("currency") or appr.params.get("base") or deal.currency
    if quote and quote != base:
        lock = db.scalars(
            select(FxLock)
            .where(FxLock.deal_id == deal.id, FxLock.status == FxLockStatus.ACTIVE)
            .order_by(FxLock.locked_at.desc())
        ).first()
        rate: str | None = None
        try:
            rate = str(fx_table(db, today).rate(base, quote))  # type: ignore[arg-type]
        except Exception:
            rate = None
        fx = FxEvidence(
            pair=f"{base}/{quote}",
            rate=str(lock.rate) if lock else rate,
            amount=str(appr.params.get("amount")) if appr.params.get("amount") else None,
            locked=lock is not None,
            lock_expires_at=lock.expires_at if lock else None,
        )

    wanted = ENGINE_ACTION.get(appr.action)
    ev = None
    if wanted:
        stmt = select(RiskEvent).where(RiskEvent.deal_id == deal.id, RiskEvent.action == wanted)
        if appr.context_hash:
            ev = db.scalars(
                stmt.where(RiskEvent.context_hash == appr.context_hash).order_by(
                    RiskEvent.ts.desc()
                )
            ).first()
        ev = ev or db.scalars(stmt.order_by(RiskEvent.ts.desc())).first()
    trace = [TraceItemOut.model_validate(t) for t in (ev.trace if ev else [])]
    return EvidenceSnapshot(
        supplier=supplier,
        documents=out_docs,
        registry_status=registry,  # type: ignore[arg-type]
        fx=fx,
        trace=trace,
        risk_event_id=ev.id if ev else None,
        audit_seq=ev.audit_seq if ev else None,
    )


def _scope(user: CurrentUser) -> Any:
    if user.role in (Role.ADMIN, Role.JUDGE):
        return None
    if user.role == Role.BUYER and user.party_id is not None:
        return user.party_id
    raise Forbidden("the approval inbox is for buyers, admins and judges")


def list_approvals(
    db: Session, user: CurrentUser, status: str | None = None, *, now: datetime | None = None
) -> ApprovalList:
    now = now or utcnow()
    buyer = _scope(user)
    expire_due(db, now)
    stmt = select(ApprovalRequest, Deal).join(Deal, Deal.id == ApprovalRequest.deal_id)
    if buyer is not None:
        stmt = stmt.where(Deal.buyer_id == buyer)
    if status == "pending":
        stmt = stmt.where(ApprovalRequest.status.in_(OPEN))
    elif status == "history":
        stmt = stmt.where(ApprovalRequest.status.not_in(OPEN))
    elif status:
        try:
            stmt = stmt.where(ApprovalRequest.status == ApprovalStatus(status.upper()))
        except ValueError:
            raise DomainError("unknown status filter", "INVALID_STATUS") from None
    rows = db.execute(stmt.order_by(ApprovalRequest.created_at.desc()).limit(200)).all()
    items: list[ApprovalOut] = []
    for appr, deal in rows:
        role = _seen_as(user, escrow_service.viewer_role(user, deal) or "")
        if appr.tier == 3 and appr.status == ApprovalStatus.PENDING and role in DECIDER_ROLES:
            _ensure_otp(db, appr, deal, now)
        items.append(to_out(db, appr, deal, role, now))
    pending = db.scalar(
        select(func.count())
        .select_from(ApprovalRequest)
        .join(Deal, Deal.id == ApprovalRequest.deal_id)
        .where(
            ApprovalRequest.status.in_(OPEN),
            *([Deal.buyer_id == buyer] if buyer is not None else []),
        )
    )
    return ApprovalList(items=items, pending_count=pending or 0)


def _ensure_otp(db: Session, appr: ApprovalRequest, deal: Deal, now: datetime) -> None:
    """Requests created before the OTP flow existed (the seeded one) get their code, expiry and a
    fresh cooling-off the first time the buyer looks at them: the pause starts when the person
    can actually see the request."""
    if appr.otp_hash is not None and appr.expires_at is not None:
        return
    if appr.expires_at is None:
        appr.expires_at = approval_otp.expiry(now)
    if appr.otp_hash is None and _requested_via(appr) != "email":
        appr.cooling_off_until = approval_otp.cooling_off_until(now, 3)
        approval_otp.issue_otp_quietly(db, appr, deal, now)
    db.commit()


def get_approval(
    db: Session, user: CurrentUser, approval_id: uuid.UUID, *, now: datetime | None = None
) -> ApprovalOut:
    now = now or utcnow()
    expire_due(db, now)
    appr, deal, role = _load(db, user, approval_id, decide=False)
    if appr.tier == 3 and appr.status == ApprovalStatus.PENDING and role in DECIDER_ROLES:
        _ensure_otp(db, appr, deal, now)
    return to_out(db, appr, deal, role, now, with_evidence=True)


# --- decisions ----------------------------------------------------------------------------------


@dataclass(slots=True)
class Ran:
    done: bool  # the action was carried out
    approval: ApprovalRequest | None = None  # the request now waiting (not done)


def _run(
    db: Session,
    user: CurrentUser,
    appr: ApprovalRequest,
    deal: Deal,
    approval_id: uuid.UUID | None,
) -> Ran:
    """Call the service function that created this request, with exactly the stored parameters."""
    p = appr.params
    try:
        match appr.action:
            case ApprovalAction.RELEASE_MILESTONE:
                assert appr.milestone_id is not None
                out = escrow_service.release_tranche(
                    db,
                    appr.milestone_id,
                    user,
                    f"approval-{appr.id}",
                    approval_id=approval_id,
                )
                return Ran(out.outcome == "RELEASED", out.approval)
            case ApprovalAction.FUND_ESCROW:
                escrow_service.fund_escrow(
                    db, user, deal.id, Decimal(str(p["amount"])), approval_id=approval_id
                )
                return Ran(True)
            case ApprovalAction.LOCK_FX_RATE:
                lk = fx_lock_service.lock_fx(
                    db, user, deal.id, Decimal(str(p["amount"])), approval_id=approval_id
                )
                return Ran(lk.outcome != "PENDING_APPROVAL", lk.approval)
            case ApprovalAction.CONFIRM_MILESTONES:
                deals_service.confirm_milestones(
                    db, user, deal.id, str(p["party_role"]), approval_id=approval_id
                )
                return Ran(True)
            case ApprovalAction.CHANGE_MILESTONE_SCHEDULE:
                custom = p.get("template") == "custom"
                deals_service.propose_milestones(
                    db,
                    user,
                    deal.id,
                    ProposeRequest(
                        template=p["template"],
                        percents=[str(x) for x in p["percents"]] if custom else None,
                    ),
                    approval_id=approval_id,
                )
                return Ran(True)
            case ApprovalAction.CHANGE_BENEFICIARY:
                assert appr.bank_account_id is not None
                bo = beneficiary_service.change_beneficiary(
                    db, user, deal.id, appr.bank_account_id, approval_id=approval_id
                )
                return Ran(bo.outcome == "CHANGED", bo.approval)
            case _:
                raise Refusal("this kind of request cannot be executed here", "NOT_EXECUTABLE")
    except ApprovalPending as pending:
        return Ran(False, pending.approval)


def _fresh_context_changed(db: Session, appr: ApprovalRequest, deal: Deal) -> bool:
    wanted = ENGINE_ACTION.get(appr.action)
    if not wanted or not appr.context_hash:
        return False
    latest = db.scalars(
        select(RiskEvent)
        .where(RiskEvent.deal_id == deal.id, RiskEvent.action == wanted)
        .order_by(RiskEvent.ts.desc())
    ).first()
    return latest is not None and latest.context_hash != appr.context_hash


def _message(kind: str, appr: ApprovalRequest) -> tuple[str, str]:
    label = ACTION_LABELS[appr.action]
    if kind == "EXECUTED":
        return (f"Done: {label[0].lower()} (Simulated).", f"সম্পন্ন: {label[1]} (সিমুলেটেড)।")
    if kind == "RE_ESCALATED":
        return (
            "Things changed since this request was made, so it needs a stricter approval. "
            "Nothing was executed. Review the new request.",
            "অনুরোধের পর পরিস্থিতি বদলেছে, তাই কঠোর অনুমোদন দরকার। কিছুই কার্যকর হয়নি। নতুন অনুরোধটি দেখুন।",
        )
    return (
        "Your approval is recorded, but the action could not run yet. Fix the issue and tap "
        "Approve again; you will not need a new code.",
        "আপনার অনুমোদন নথিভুক্ত, তবে কাজটি এখনো চলেনি। সমস্যা মিটিয়ে আবার অনুমোদন চাপুন; নতুন কোড লাগবে না।",
    )


def approve(
    db: Session,
    user: CurrentUser,
    approval_id: uuid.UUID,
    otp: str | None = None,
    *,
    stepup_token: str | None = None,
    now: datetime | None = None,
) -> ApproveResult:
    now = now or utcnow()
    appr, deal, role = _load(db, user, approval_id, decide=True, lock=True)

    if appr.status == ApprovalStatus.EXECUTED:  # idempotent replay
        return ApproveResult(
            outcome="EXECUTED",
            idempotent_replay=True,
            approval=to_out(db, appr, deal, role, now),
            message_en=_message("EXECUTED", appr)[0],
            message_bn=_message("EXECUTED", appr)[1],
        )
    if appr.status in OPEN and appr.expires_at is not None and appr.expires_at < now:
        _end(db, appr, deal, None, ApprovalStatus.EXPIRED, now, "Not decided in time")
        raise Refusal("this request has expired; ask for a new one", "APPROVAL_EXPIRED")
    if appr.status not in OPEN:
        raise Refusal(
            f"this request is {appr.status.value.lower()}", f"APPROVAL_{appr.status.value}"
        )
    if _requested_via(appr) == "email":
        raise Refusal(
            "Setu never changes a payment account because of an email. Reject this request.",
            "BENEFICIARY_VIA_EMAIL",
        )

    waived = False
    if appr.status == ApprovalStatus.PENDING:
        if appr.tier == 2:
            stepup.require(db, user, stepup_token)  # Tier 3 has its own OTP: no double prompt
        waived = _four_eyes(db, appr, deal, user, now)
        if appr.tier == 3:
            _check_step_up(db, appr, deal, user, otp, now)
        appr.status = ApprovalStatus.APPROVED
        appr.decided_by_user_id = user.id
        appr.decided_at = now
        seq = _audit(
            db,
            deal,
            "APPROVAL_APPROVED",
            appr,
            user,
            f"APPROVED:T{appr.tier}",
            now,
            otp_verified=appr.tier == 3,
            role=role,
            **({"four_eyes_waived": True} if waived else {}),
        )
        approval_otp.emit(
            db,
            kind="APPROVED",
            now=now,
            deal=deal,
            approval=appr,
            parties=_parties(deal, appr),
            tier=appr.tier,
            actor="user",
            title=(
                "Approved with OTP" if appr.tier == 3 else "Approved with one tap",
                "ওটিপি দিয়ে অনুমোদিত" if appr.tier == 3 else "এক ট্যাপে অনুমোদিত",
            ),
            detail=(f"{ACTION_LABELS[appr.action][0]} · {deal.reference}",) * 2,
            audit_seq=seq,
        )
        db.commit()
    return _execute(db, user, appr, deal, role, now)


def _four_eyes(
    db: Session, appr: ApprovalRequest, deal: Deal, user: CurrentUser, now: datetime
) -> bool:
    """The person who asked for this approval may not approve it, if someone else could. Returns
    True when the rule was waived because the requester is the party's only OWNER/FINANCE member
    (so a one-person company is not deadlocked); the caller records that in the audit row."""
    if not get_settings().four_eyes_active or appr.requested_by_user_id != user.id:
        return False
    others = [u for u in approval_otp.approvers(db, deal.buyer_id) if u.id != user.id]
    if others:
        _audit(db, deal, "APPROVAL_FOUR_EYES_REFUSED", appr, user, "FOUR_EYES", now)
        db.commit()
        raise Forbidden(
            "you asked for this action, so a colleague must approve it", code="FOUR_EYES"
        )
    return True


def _check_step_up(
    db: Session,
    appr: ApprovalRequest,
    deal: Deal,
    user: CurrentUser,
    otp: str | None,
    now: datetime,
) -> None:
    """Tier 3: cooling-off first (a wrong code is not counted before the pause is over), then the
    one-time code. Three wrong codes lock the request for good."""
    if appr.cooling_off_until is not None and now < appr.cooling_off_until:
        left = int((appr.cooling_off_until - now).total_seconds() + 0.999)
        _audit(db, deal, "APPROVAL_TOO_EARLY", appr, user, "COOLING_OFF", now)
        db.commit()
        raise Refusal(
            f"The cooling-off period ends in {left} s. Approve after that.",
            "COOLING_OFF",
        )
    if appr.otp_hash is None:
        raise Refusal("no code has been sent yet; ask for one", "OTP_NOT_ISSUED")
    if otp is None:
        raise DomainError("enter the 6-digit code", "OTP_REQUIRED")
    if appr.otp_expires_at is not None and appr.otp_expires_at < now:
        raise Refusal("the code has expired; ask for a new one", "OTP_EXPIRED")
    if approval_otp.code_matches(appr, otp):
        appr.otp_verified_at = now
        return
    appr.otp_attempts += 1
    left = get_settings().otp_max_attempts - appr.otp_attempts
    if left <= 0:
        _end(db, appr, deal, user, ApprovalStatus.LOCKED, now, "Three wrong codes")
        raise Refusal("three wrong codes: this request is locked", "OTP_LOCKED")
    seq = _audit(db, deal, "APPROVAL_OTP_FAILED", appr, user, f"WRONG_CODE:{left}_LEFT", now)
    approval_otp.emit(
        db,
        kind="OTP_FAILED",
        now=now,
        deal=deal,
        approval=appr,
        parties=[None],
        tier=appr.tier,
        actor="user",
        title=("Wrong code entered", "ভুল কোড দেওয়া হয়েছে"),
        detail=(f"{left} tries left", f"আর {left} বার চেষ্টা বাকি"),
        audit_seq=seq,
    )
    db.commit()
    raise Refusal(f"wrong code, {left} tries left", "OTP_INVALID")


def _execute(
    db: Session,
    user: CurrentUser,
    appr: ApprovalRequest,
    deal: Deal,
    role: str,
    now: datetime,
) -> ApproveResult:
    appr_id, old_hash = appr.id, appr.context_hash
    try:
        _run(db, user, appr, deal, appr_id)
    except DomainError as exc:
        db.rollback()
        appr = db.get(ApprovalRequest, appr_id)  # type: ignore[assignment]
        deal = db.get(Deal, appr.deal_id)  # type: ignore[assignment,union-attr]
        if exc.code == "APPROVAL_TIER_STALE":
            return _re_escalate(db, user, appr, deal, role, now, old_hash)
        if isinstance(exc, RiskBlocked) or exc.code in ("RISK_BLOCKED", "RELEASE_BLOCKED"):
            _end(db, appr, deal, user, ApprovalStatus.CANCELLED, now, "Blocked by the risk engine")
        raise

    db.refresh(appr)
    deal = db.get(Deal, deal.id)  # type: ignore[assignment]
    if appr.status != ApprovalStatus.EXECUTED:
        appr.status = ApprovalStatus.EXECUTED
    changed = _fresh_context_changed(db, appr, deal)
    seq = _audit(db, deal, "APPROVAL_EXECUTED", appr, user, f"EXECUTED:T{appr.tier}", now)
    msg = _message("EXECUTED", appr)
    approval_otp.emit(
        db,
        kind="EXECUTED",
        now=now,
        deal=deal,
        approval=appr,
        parties=_parties(deal, appr),
        tier=appr.tier,
        actor="user",
        title=("Executed", "কার্যকর হয়েছে"),
        detail=msg,
        audit_seq=seq,
    )
    db.commit()
    return ApproveResult(
        outcome="EXECUTED",
        approval=to_out(db, appr, deal, role, now, with_evidence=True),
        message_en=msg[0],
        message_bn=msg[1],
        context_changed=changed,
    )


def _re_escalate(
    db: Session,
    user: CurrentUser,
    old: ApprovalRequest,
    deal: Deal,
    role: str,
    now: datetime,
    old_hash: str | None,
) -> ApproveResult:
    """Conditions changed and the action now needs a higher tier: close the old request without
    executing and let the same service function open the stricter one."""
    old.status = ApprovalStatus.CANCELLED
    old.decided_at = now
    old.decision_note = "Superseded: conditions changed, a stricter approval is needed"
    db.commit()
    try:
        ran = _run(db, user, old, deal, None)
    except DomainError:
        _close_effects(db, old, deal, now)
        raise
    new = ran.approval
    if new is None or new.id == old.id:
        raise Refusal("the stricter request could not be created", "REESCALATION_FAILED")
    old = db.get(ApprovalRequest, old.id)  # type: ignore[assignment]
    old.superseded_by = new.id
    seq = _audit(
        db,
        deal,
        "APPROVAL_REESCALATED",
        old,
        user,
        f"RE_ESCALATED:T{old.tier}->T{new.tier}",
        now,
        new_approval_id=str(new.id),
        old_context_hash=old_hash,
        new_context_hash=new.context_hash,
    )
    msg = _message("RE_ESCALATED", old)
    approval_otp.emit(
        db,
        kind="RE_ESCALATED",
        now=now,
        deal=deal,
        approval=new,
        parties=_parties(deal, new),
        tier=new.tier,
        actor="system",
        title=("Re-escalated: conditions changed", "পুনরায় উন্নীত: পরিস্থিতি বদলেছে"),
        detail=msg,
        audit_seq=seq,
    )
    db.commit()
    return ApproveResult(
        outcome="RE_ESCALATED",
        approval=to_out(db, old, deal, role, now),
        new_approval=to_out(db, new, deal, role, now, with_evidence=True),
        message_en=msg[0],
        message_bn=msg[1],
        context_changed=old_hash != new.context_hash,
    )


def reject(
    db: Session,
    user: CurrentUser,
    approval_id: uuid.UUID,
    reason: str | None = None,
    *,
    now: datetime | None = None,
) -> ApprovalOut:
    now = now or utcnow()
    appr, deal, role = _load(db, user, approval_id, decide=True, lock=True)
    if appr.status == ApprovalStatus.REJECTED:
        return to_out(db, appr, deal, role, now)
    if appr.status not in OPEN:
        raise Refusal(
            f"this request is {appr.status.value.lower()}", f"APPROVAL_{appr.status.value}"
        )
    _end(db, appr, deal, user, ApprovalStatus.REJECTED, now, reason)
    return to_out(db, appr, deal, role, now)


def cancel(
    db: Session, user: CurrentUser, approval_id: uuid.UUID, *, now: datetime | None = None
) -> ApprovalOut:
    """Withdraw a Tier 3 request (the buyer's way out during the cooling-off)."""
    now = now or utcnow()
    appr, deal, role = _load(db, user, approval_id, decide=True, lock=True)
    if appr.status == ApprovalStatus.CANCELLED:
        return to_out(db, appr, deal, role, now)
    if appr.status not in OPEN or appr.tier != 3:
        raise Refusal("only an open Tier 3 request can be cancelled", "CANNOT_CANCEL")
    _end(db, appr, deal, user, ApprovalStatus.CANCELLED, now, "Cancelled by the buyer")
    return to_out(db, appr, deal, role, now)


def resend_otp(
    db: Session, user: CurrentUser, approval_id: uuid.UUID, *, now: datetime | None = None
) -> tuple[ApprovalOut, bool]:
    now = now or utcnow()
    appr, deal, role = _load(db, user, approval_id, decide=True, lock=True)
    if appr.tier != 3 or appr.status != ApprovalStatus.PENDING:
        raise Refusal("a code can only be sent for an open Tier 3 request", "OTP_NOT_APPLICABLE")
    if _requested_via(appr) == "email":
        raise Refusal("this request cannot be approved; reject it", "BENEFICIARY_VIA_EMAIL")
    sent = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalEvent)
            .where(ApprovalEvent.approval_id == appr.id, ApprovalEvent.kind == "OTP_SENT")
        )
        or 0
    )
    if sent >= MAX_RESENDS:
        raise Refusal("too many codes were requested", "OTP_RESEND_LIMIT")
    try:
        approval_otp.issue_otp(db, appr, deal, now)
    except ServiceUnavailable:
        db.rollback()  # the old code stays valid; the person can try "resend" again
        raise
    seq = _audit(db, deal, "APPROVAL_OTP_SENT", appr, user, "SENT", now)
    approval_otp.emit(
        db,
        kind="OTP_SENT",
        now=now,
        deal=deal,
        approval=appr,
        parties=[None],
        tier=appr.tier,
        actor="user",
        title=(
            ("New code sent by email", "ইমেইলে নতুন কোড পাঠানো হয়েছে")
            if get_settings().auth_mode == "neon"
            else ("New code sent to the demo phone", "ডেমো ফোনে নতুন কোড পাঠানো হয়েছে")
        ),
        audit_seq=seq,
    )
    db.commit()
    return to_out(db, appr, deal, role, now), get_settings().demo_mode


# --- demo phone, notifications, timeline --------------------------------------------------------


def demo_phone(db: Session, user: CurrentUser) -> list[DemoPhoneMessage]:
    """The simulated SMS inbox. Only when DEMO_MODE is on, and only the buyer (or an admin who may
    decide in the demo). Everyone else, and every deployment with DEMO_MODE=false, gets 404."""
    if not get_settings().demo_mode or get_settings().app_env == "prod":
        raise NotFound("not found")
    if user.role == Role.BUYER and user.party_id is not None:
        party_filter = DemoPhoneMessage.party_id == user.party_id
    elif user.role == Role.ADMIN:
        party_filter = DemoPhoneMessage.party_id.is_not(None)
    else:
        raise NotFound("not found")
    return list(
        db.scalars(
            select(DemoPhoneMessage)
            .where(party_filter)
            .order_by(DemoPhoneMessage.created_at.desc())
            .limit(20)
        ).all()
    )


def _event_out(db: Session, e: ApprovalEvent) -> EventOut:
    deal = db.get(Deal, e.deal_id) if e.deal_id else None
    return EventOut(
        id=e.id,
        ts=e.ts,
        kind=e.kind,
        tier=e.tier,
        actor=e.actor,
        title_en=e.title_en,
        title_bn=e.title_bn,
        detail_en=e.detail_en,
        detail_bn=e.detail_bn,
        approval_id=e.approval_id,
        deal_id=e.deal_id,
        deal_reference=deal.reference if deal else None,
        audit_seq=e.audit_seq,
        unread=e.read_at is None,
    )


def _feed(user: CurrentUser) -> Any:
    if user.role in (Role.ADMIN, Role.JUDGE):
        return ApprovalEvent.party_id.is_not(None)
    if user.party_id is None:
        raise Forbidden("no notifications for this user")
    return ApprovalEvent.party_id == user.party_id


def notifications(db: Session, user: CurrentUser, limit: int = 20) -> NotificationsOut:
    expire_due(db)
    where = [_feed(user), ApprovalEvent.kind.in_(FEED_KINDS)]
    rows = db.scalars(
        select(ApprovalEvent).where(*where).order_by(ApprovalEvent.ts.desc()).limit(limit)
    ).all()
    unread = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalEvent)
            .where(*where, ApprovalEvent.read_at.is_(None))
        )
        or 0
    )
    return NotificationsOut(unread=unread, items=[_event_out(db, e) for e in rows])


def mark_read(db: Session, user: CurrentUser, now: datetime | None = None) -> int:
    if user.role == Role.JUDGE:
        return 0  # read-only demo user
    now = now or utcnow()
    rows = db.scalars(
        select(ApprovalEvent).where(_feed(user), ApprovalEvent.read_at.is_(None))
    ).all()
    if user.role == Role.ADMIN:
        return 0
    for e in rows:
        e.read_at = now
    db.commit()
    return len(rows)


def timeline(
    db: Session,
    user: CurrentUser,
    deal: Deal,
    approval_id: uuid.UUID | None = None,
    *,
    now: datetime | None = None,
) -> TimelineOut:
    """Agent proposed -> risk engine decided Tier N -> human approved -> executed, each linked to
    its signed audit row. Chooses the given request, else the latest one of the deal."""
    now = now or utcnow()
    role = escrow_service.require_view(user, deal)
    if role == "SUPPLIER":
        raise Forbidden("approvals are private to the buyer")
    stmt = select(ApprovalRequest).where(ApprovalRequest.deal_id == deal.id)
    appr = (
        db.scalars(stmt.where(ApprovalRequest.id == approval_id)).first()
        if approval_id
        else db.scalars(stmt.order_by(ApprovalRequest.created_at.desc())).first()
    )
    if approval_id and appr is None:
        raise NotFound("approval not found")
    events = list(
        db.scalars(
            select(ApprovalEvent)
            .where(ApprovalEvent.deal_id == deal.id)
            .order_by(ApprovalEvent.ts.desc())
            .limit(100)
        ).all()
    )
    steps: list[TimelineStep] = []
    if appr is not None:
        mine = [e for e in events if e.approval_id == appr.id]

        def seq_of(kind: str) -> int | None:
            return next((e.audit_seq for e in reversed(mine) if e.kind == kind), None)

        by_agent = appr.requested_by.value == "llm"
        status = appr.status
        decided = status in (ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED)
        steps.append(
            TimelineStep(
                key="PROPOSED",
                ts=appr.created_at,
                state="DONE",
                label_en="Agent proposed" if by_agent else "Action requested",
                label_bn="এজেন্ট প্রস্তাব দিয়েছে" if by_agent else "কাজের অনুরোধ",
                detail_en=ACTION_LABELS[appr.action][0],
                detail_bn=ACTION_LABELS[appr.action][1],
                audit_seq=None,
            )
        )
        steps.append(
            TimelineStep(
                key="RISK",
                ts=appr.created_at,
                state="DONE",
                label_en=f"Risk engine decided Tier {appr.tier}",
                label_bn=f"ঝুঁকি ইঞ্জিন টিয়ার {appr.tier} নির্ধারণ করেছে",
                detail_en=", ".join(str(r.get("code")) for r in appr.reasons),
                detail_bn=", ".join(str(r.get("code")) for r in appr.reasons),
                audit_seq=seq_of("CREATED"),
            )
        )
        human_state = (
            "DONE"
            if decided
            else "FAILED"
            if status
            in (
                ApprovalStatus.REJECTED,
                ApprovalStatus.LOCKED,
                ApprovalStatus.CANCELLED,
                ApprovalStatus.EXPIRED,
            )
            else "CURRENT"
        )
        via = "with OTP" if appr.tier == 3 else "with one tap"
        via_bn = "ওটিপি দিয়ে" if appr.tier == 3 else "এক ট্যাপে"
        outcome_en = {
            ApprovalStatus.REJECTED: "Rejected by the buyer",
            ApprovalStatus.LOCKED: "Locked after 3 wrong codes",
            ApprovalStatus.CANCELLED: "Cancelled",
            ApprovalStatus.EXPIRED: "Expired",
        }.get(status)
        outcome_bn = {
            ApprovalStatus.REJECTED: "ক্রেতা প্রত্যাখ্যান করেছেন",
            ApprovalStatus.LOCKED: "৩ বার ভুল কোডে লক",
            ApprovalStatus.CANCELLED: "বাতিল",
            ApprovalStatus.EXPIRED: "মেয়াদ শেষ",
        }.get(status)
        steps.append(
            TimelineStep(
                key="HUMAN",
                ts=appr.decided_at,
                state=human_state,
                label_en=f"Human approved {via}"
                if decided
                else (outcome_en or "Waiting for a human"),
                label_bn=f"মানুষ {via_bn} অনুমোদন দিয়েছেন"
                if decided
                else (outcome_bn or "মানুষের অপেক্ষায়"),
                detail_en="",
                detail_bn="",
                audit_seq=seq_of("APPROVED")
                or seq_of(
                    {
                        "REJECTED": "REJECTED",
                        "LOCKED": "LOCKED",
                        "CANCELLED": "CANCELLED",
                        "EXPIRED": "EXPIRED",
                    }.get(status.value, "")
                ),
            )
        )
        done = status == ApprovalStatus.EXECUTED
        verb_en = (
            "Funds released" if appr.action == ApprovalAction.RELEASE_MILESTONE else "Executed"
        )
        verb_bn = (
            "অর্থ ছাড় হয়েছে" if appr.action == ApprovalAction.RELEASE_MILESTONE else "কার্যকর হয়েছে"
        )
        steps.append(
            TimelineStep(
                key="EXECUTED",
                ts=appr.decided_at if done else None,
                state="DONE"
                if done
                else ("UPCOMING" if human_state in ("CURRENT", "DONE") else "FAILED"),
                label_en=verb_en,
                label_bn=verb_bn,
                detail_en="Simulated" if done else "",
                detail_bn="সিমুলেটেড" if done else "",
                audit_seq=seq_of("EXECUTED"),
            )
        )
    return TimelineOut(
        approval_id=appr.id if appr else None,
        deal_id=deal.id,
        steps=steps,
        events=[_event_out(db, e) for e in events],
    )


def expiry_for_tests(minutes: int) -> timedelta:  # pragma: no cover - convenience
    return timedelta(minutes=minutes)
