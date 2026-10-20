"""Admin side of onboarding: queue, masked detail, reveal-with-reason, and the decisions
(approve / request changes / reject / suspend, plus the DEMO_MODE auto-approve). Every decision is
a signed audit entry, an in-app notification for the applicant and (best effort) an email.
Humans only: nothing here is exposed as an agent tool. Nobody decides their own account."""

import uuid
from datetime import UTC, datetime
from html import escape
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.ratelimit import check_limit
from app.audit.writer import write_audit
from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import (
    AccountStatus,
    KybStatus,
    OnboardingDecision,
    OnboardingStatus,
    Role,
    UserStatus,
    VerificationDocStatus,
)
from app.db.models import (
    ApprovalEvent,
    BankAccount,
    OnboardingProfile,
    OnboardingReview,
    Party,
    User,
)
from app.domain import onboarding_kyb as engine
from app.errors import Conflict, DomainError, Forbidden, NotFound
from app.schemas.onboarding import (
    AdminBank,
    AdminCheck,
    AdminParty,
    ChangeRequestOut,
    RequestChangesIn,
    RevealOut,
    ReviewList,
    ReviewOut,
)
from app.services import kyb as kyb_service
from app.services import mail, onboarding

log = structlog.get_logger("setu.onboarding_review")
REVEAL_PATHS = {
    "mobile": ("mobile",),
    "trade_license_no": ("business", "trade_license_no"),
    "irc_no": ("business", "irc_no"),
    "tin": ("business", "tin"),
    "uscc": ("business", "uscc"),
    "bank_account_no": ("business", "bank_account_no"),
}
DOC_TYPES = {"TRADE_LICENSE", "IRC", "TIN_CERT", "BUSINESS_LICENSE", "BANK_PROOF", "OTHER"}


def _now() -> datetime:
    return datetime.now(UTC)


def _loaded(rows: list[dict[str, Any]]) -> list[engine.OnboardingCheck]:
    return [engine.OnboardingCheck(r["code"], r["status"], r["detail"]) for r in rows]


# --- read ------------------------------------------------------------------------------------


def review_out(db: Session, review: OnboardingReview) -> ReviewOut:
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    profile = onboarding.profile_of(db, user)
    account = db.scalar(
        select(BankAccount)
        .where(BankAccount.party_id == party.id)
        .order_by(BankAccount.created_at)
        .limit(1)
    )
    checks = _loaded(review.checks)
    data = (profile.data if profile else None) or {}
    return ReviewOut(
        id=review.id,
        status=review.status.value,  # type: ignore[arg-type]
        recommendation=engine.recommend(checks),
        risk_summary=engine.risk_summary(checks),
        score=review.score,
        role=user.role.value,  # type: ignore[arg-type]
        account_status=user.status.value,  # type: ignore[arg-type]
        decision=profile.decision.value if profile and profile.decision else None,  # type: ignore[arg-type]
        revision=profile.revision if profile else 0,
        user_id=user.id,
        user_email=user.email,
        user_display_name=user.display_name,
        party=AdminParty(
            id=party.id,
            kind=party.kind.value,  # type: ignore[arg-type]
            legal_name=party.legal_name,
            license_name=party.license_name,
            license_no=party.license_no,
            tax_id=party.tax_id,
            city=party.city,
            country=party.country,
            kyb_status=party.kyb_status.value,  # type: ignore[arg-type]
        ),
        bank_account=None
        if account is None
        else AdminBank(
            bank_name=account.bank_name,
            bank_country=account.bank_country,
            account_masked=kyb_service.mask_account(account.account_number),
            holder_name=account.holder_name,
            account_type=account.account_type.value,  # type: ignore[arg-type]
            currency=account.currency,
            status=account.status.value,  # type: ignore[arg-type]
        ),
        contact=onboarding.contact_out(db, user, profile) if profile else None,
        business=data.get("business"),
        documents=[onboarding.doc_out(d) for d in onboarding.documents_of(db, user)],
        change_requests=[
            ChangeRequestOut(target=c["target"], note=c["note"])
            for c in (profile.change_requests if profile else [])
        ],
        checks=[AdminCheck(code=c.code, status=c.status, detail=c.detail) for c in checks],
        submitted_at=review.submitted_at,
        decided_at=review.decided_at,
        decided_by=review.decided_by,
        reason=review.reason,
    )


def list_reviews(
    db: Session, status: OnboardingStatus | None, role: Role | None = None
) -> ReviewList:
    q = select(OnboardingReview).order_by(OnboardingReview.submitted_at.desc()).limit(200)
    if status is not None:
        q = q.where(OnboardingReview.status == status)
    if role is not None:
        q = q.join(User, User.id == OnboardingReview.user_id).where(User.role == role)
    return ReviewList(items=[review_out(db, r) for r in db.scalars(q)])


def get_review(db: Session, review_id: uuid.UUID) -> ReviewOut:
    return review_out(db, _review(db, review_id))


def _review(db: Session, review_id: uuid.UUID, *, lock: bool = False) -> OnboardingReview:
    stmt = select(OnboardingReview).where(OnboardingReview.id == review_id)
    review = db.scalar(stmt.with_for_update() if lock else stmt)
    if review is None:
        raise NotFound("onboarding review not found")
    return review


def reveal(
    db: Session, admin: CurrentUser, review_id: uuid.UUID, field: str, reason: str
) -> RevealOut:
    check_limit("onboarding-reveal", str(admin.id), get_settings().rate_limit_reveal_per_hour, 3600)
    review = _review(db, review_id)
    if review.user_id == admin.id:
        raise Forbidden("you cannot reveal your own details here", code="SELF_DECISION")
    user = db.get(User, review.user_id)
    profile = onboarding.profile_of(db, user) if user else None
    if profile is None:
        raise NotFound("no details on file")
    node: Any = onboarding.secure_of(profile)
    for key in REVEAL_PATHS[field]:
        node = node.get(key) if isinstance(node, dict) else None
    if not isinstance(node, str) or not node:
        raise NotFound("that value is not on file")
    admin_row = db.get(User, admin.id)
    assert admin_row is not None
    onboarding.audit(
        db,
        admin_row,
        "onboarding.reveal",
        {"review_id": str(review.id), "field": field, "reason": reason},
        tier=2,
    )
    db.commit()
    return RevealOut(field=field, value=node)  # type: ignore[arg-type]


# --- decisions -------------------------------------------------------------------------------


def _notify(
    db: Session,
    user: User,
    party_id: uuid.UUID | None,
    title: tuple[str, str],
    detail: tuple[str, str],
    audit_seq: int | None,
) -> None:
    if party_id is not None:  # the in-app bell is per business; reviews always have one
        db.add(
            ApprovalEvent(
                id=uuid.uuid4(),
                ts=_now(),
                party_id=party_id,
                kind="ONBOARDING",
                tier=0,
                actor="user",
                title_en=title[0][:200],
                title_bn=title[1][:200],
                detail_en=detail[0][:600],
                detail_bn=detail[1][:900],
                audit_seq=audit_seq,
            )
        )
    text = f"{title[0]}\n{detail[0]}\n\n{title[1]}\n{detail[1]}\n"
    html = f"<p><b>{escape(title[0])}</b><br>{escape(detail[0])}</p><p>{escape(title[1])}</p>"
    try:
        mail.deliver(
            mail.Mail(to=user.email, subject=f"{title[0]} / {title[1]}", text=text, html=html)
        )
    except DomainError:
        log.warning("onboarding_mail_failed", user_id=str(user.id))


def _record(
    db: Session,
    admin: CurrentUser | None,
    review: OnboardingReview,
    decision: str,
    extra: dict[str, Any],
) -> int:
    return write_audit(
        db,
        actor="user" if admin else "system",
        action="onboarding.decision",
        tier=2,
        params={
            "review_id": str(review.id),
            "user_id": str(review.user_id),
            "decision": decision,
            **extra,
        },
        result=decision.lower(),
        actor_id=str(admin.id) if admin else None,
    )


def _stamp(
    profile: OnboardingProfile | None,
    review: OnboardingReview,
    admin: CurrentUser | None,
    decision: OnboardingDecision,
    notes: str | None,
) -> None:
    now = _now()
    review.decided_at = now
    review.decided_by = admin.id if admin else None
    review.reason = notes
    if profile is not None:
        profile.decision = decision
        profile.reviewed_by = admin.id if admin else None
        profile.reviewed_at = now
        profile.review_notes = notes


def apply_approve(db: Session, review: OnboardingReview, admin: CurrentUser | None) -> None:
    """Activate the account (admin click, DEMO auto-approve or ONBOARDING_AUTO_APPROVE). Caller
    commits. A licence/USCC already held by an approved business raises 409 and changes nothing."""
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    profile = onboarding.profile_of(db, user)
    if engine.blocked(_loaded(review.checks)):
        raise Conflict("a screening hit blocks approval; reject instead", code="SANCTIONS_BLOCK")
    now = _now()
    review.status = OnboardingStatus.APPROVED
    user.status = UserStatus.ACTIVE
    party.kyb_status = KybStatus.VERIFIED
    party.onboarded_at = now
    if profile is not None:
        party.dedupe_key = (profile.data or {}).get("dedupe_key_hmac")
        profile.change_requests = []
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "another approved business already uses this licence or registration number",
            code="DUPLICATE_COMPANY_APPROVED",
        ) from exc
    for a in db.scalars(select(BankAccount).where(BankAccount.party_id == party.id)):
        if a.status == AccountStatus.PENDING_CHANGE:
            a.status, a.verified = AccountStatus.ACTIVE, True
    for d in onboarding.documents_of(db, user):
        d.status = VerificationDocStatus.VERIFIED
    _stamp(profile, review, admin, OnboardingDecision.APPROVED, None)
    seq = _record(db, admin, review, "APPROVED", {"auto": admin is None, "party_id": str(party.id)})
    _notify(
        db,
        user,
        party.id,
        ("Your Setu account is verified", "আপনার সেতু অ্যাকাউন্ট যাচাই হয়েছে"),
        (
            "You can now create orders and move money (simulated).",
            "এখন অর্ডার ও লেনদেন করতে পারবেন (সিমুলেটেড)।",
        ),
        seq,
    )


def _freeze_party(db: Session, party: Party, owner: User) -> None:
    """A rejected or suspended business is frozen as a whole: the party fails KYB (so deals refuse
    it) and every other member account is suspended with it."""
    party.kyb_status = KybStatus.FAILED
    for member in db.scalars(select(User).where(User.party_id == party.id, User.id != owner.id)):
        member.status = UserStatus.SUSPENDED


def _pending(db: Session, admin: CurrentUser, review_id: uuid.UUID) -> OnboardingReview:
    review = _review(db, review_id, lock=True)
    if review.user_id == admin.id:
        raise Forbidden("you cannot decide your own onboarding", code="SELF_DECISION")
    return review


def _not_frozen(db: Session, review: OnboardingReview) -> None:
    """Suspension is terminal: no approve / request-changes on a suspended owner or business."""
    owner = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    if (
        review.status == OnboardingStatus.SUSPENDED
        or (owner is not None and owner.status == UserStatus.SUSPENDED)
        or (party is not None and party.kyb_status == KybStatus.FAILED)
    ):
        raise Conflict("this account is suspended or closed", code="ACCOUNT_SUSPENDED")


def approve(db: Session, admin: CurrentUser, review_id: uuid.UUID) -> ReviewOut:
    review = _pending(db, admin, review_id)
    _not_frozen(db, review)
    if review.status != OnboardingStatus.PENDING:
        raise Conflict("this review was already decided", code="ONBOARDING_DECIDED")
    apply_approve(db, review, admin)
    db.commit()
    return review_out(db, review)


def auto_approve(db: Session, admin: CurrentUser, review_id: uuid.UUID) -> ReviewOut:
    if not get_settings().demo_enabled:
        raise NotFound("not found")
    return approve(db, admin, review_id)


def request_changes(
    db: Session, admin: CurrentUser, review_id: uuid.UUID, body: RequestChangesIn
) -> ReviewOut:
    review = _pending(db, admin, review_id)
    _not_frozen(db, review)
    if review.status != OnboardingStatus.PENDING:
        raise Conflict("this review was already decided", code="ONBOARDING_DECIDED")
    user = db.get(User, review.user_id)
    assert user is not None
    profile = onboarding.profile_of(db, user)
    items = [{"target": i.target, "note": i.note} for i in body.items]
    for doc in onboarding.documents_of(db, user):
        notes = [i["note"] for i in items if i["target"] == doc.type.value]
        if notes:
            doc.status = VerificationDocStatus.REJECTED
            doc.reviewer_notes = notes[0]
    review.status = OnboardingStatus.CHANGES_REQUESTED
    user.status = UserStatus.PENDING_PROFILE
    _stamp(profile, review, admin, OnboardingDecision.CHANGES_REQUESTED, f"{len(items)} item(s)")
    if profile is not None:
        profile.change_requests = items
    seq = _record(db, admin, review, "CHANGES_REQUESTED", {"targets": [i["target"] for i in items]})
    _notify(
        db,
        user,
        review.party_id,
        ("Please update your verification details", "যাচাইয়ের তথ্য হালনাগাদ করুন"),
        ("Open your verification status to see what to fix.", "কী ঠিক করতে হবে তা স্ট্যাটাস পাতায় দেখুন।"),
        seq,
    )
    db.commit()
    return review_out(db, review)


def reject(db: Session, admin: CurrentUser, review_id: uuid.UUID, reason: str) -> ReviewOut:
    review = _pending(db, admin, review_id)
    if review.status != OnboardingStatus.PENDING:
        raise Conflict("this review was already decided", code="ONBOARDING_DECIDED")
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    review.status = OnboardingStatus.REJECTED
    user.status = UserStatus.REJECTED
    _freeze_party(db, party, user)
    for a in db.scalars(select(BankAccount).where(BankAccount.party_id == party.id)):
        a.status = AccountStatus.RETIRED
    _stamp(onboarding.profile_of(db, user), review, admin, OnboardingDecision.REJECTED, reason)
    seq = _record(db, admin, review, "REJECTED", {"reason": reason})
    _notify(
        db,
        user,
        party.id,
        ("Your verification was not approved", "আপনার যাচাই অনুমোদিত হয়নি"),
        (reason, reason),
        seq,
    )
    db.commit()
    return review_out(db, review)


def suspend(db: Session, admin: CurrentUser, review_id: uuid.UUID, reason: str) -> ReviewOut:
    review = _pending(db, admin, review_id)
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    if user.role not in (Role.BUYER, Role.SUPPLIER):
        raise Conflict("only business accounts are suspended here", code="ROLE_NOT_REVIEWABLE")
    if user.status == UserStatus.SUSPENDED or review.status in (
        OnboardingStatus.SUSPENDED,
        OnboardingStatus.REJECTED,
        OnboardingStatus.CHANGES_REQUESTED,
    ):
        raise Conflict("this account is already closed or suspended", code="ONBOARDING_DECIDED")
    review.status = OnboardingStatus.SUSPENDED  # leaves the PENDING queue for good
    user.status = UserStatus.SUSPENDED
    _freeze_party(db, party, user)
    _stamp(onboarding.profile_of(db, user), review, admin, OnboardingDecision.SUSPENDED, reason)
    seq = _record(db, admin, review, "SUSPENDED", {"reason": reason})
    _notify(
        db,
        user,
        party.id,
        ("Your Setu account is suspended", "আপনার সেতু অ্যাকাউন্ট স্থগিত করা হয়েছে"),
        (reason, reason),
        seq,
    )
    db.commit()
    return review_out(db, review)
