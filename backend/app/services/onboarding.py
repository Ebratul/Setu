"""Self-service onboarding: a verified Neon identity submits a business and a bank account, code
checks it (app/domain/onboarding_kyb.py), and an admin (or, when enabled, the system for a clean
submission) activates it. Nothing here is reachable from the LLM tool layer."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth import neon
from app.auth.deps import CurrentUser, local_user
from app.config import get_settings
from app.db import tenancy
from app.db.enums import (
    AccountStatus,
    AccountType,
    KybStatus,
    Language,
    MemberRole,
    OnboardingStatus,
    PartyKind,
    Role,
    UserStatus,
)
from app.db.models import BankAccount, OnboardingReview, Party, PartyMember, User
from app.domain import onboarding_kyb as engine
from app.errors import Conflict, Forbidden, NotFound
from app.schemas.onboarding import (
    AdminBank,
    AdminCheck,
    AdminParty,
    OnboardingIn,
    OnboardingStatusOut,
    PublicCheck,
    ReviewList,
    ReviewOut,
)
from app.services import kyb as kyb_service

LICENSE_LOCK_KEY = 0x5E7A0B01


def _now() -> datetime:
    return datetime.now(UTC)


def _stored(checks: tuple[engine.OnboardingCheck, ...]) -> list[dict[str, str]]:
    return [{"code": c.code, "status": c.status, "detail": c.detail} for c in checks]


def _loaded(rows: list[dict[str, Any]]) -> list[engine.OnboardingCheck]:
    return [engine.OnboardingCheck(r["code"], r["status"], r["detail"]) for r in rows]


def submit(db: Session, identity: neon.NeonIdentity, body: OnboardingIn) -> OnboardingStatusOut:
    settings = get_settings()
    if local_user(db, identity) is not None:
        raise Conflict("this sign-in already has an account", code="ONBOARDING_EXISTS")
    taken = db.scalar(select(User.id).where(func.lower(User.email) == identity.email))
    if taken is not None:
        raise Conflict("this email address is already used by another account", code="EMAIL_IN_USE")
    allowed = settings.onboarding_country_list
    if body.country not in allowed:
        raise Conflict("Setu is not available for this country yet", code="COUNTRY_NOT_SUPPORTED")
    kind = PartyKind(body.account_type)
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": tenancy.lock_key(LICENSE_LOCK_KEY)})
    duplicate = db.scalar(
        select(Party.id).where(
            Party.kind == kind, func.upper(Party.license_no) == body.license_no.upper()
        )
    )
    if duplicate is not None:
        raise Conflict(
            "a business with this licence number is already registered", "LICENSE_EXISTS"
        )

    bank = body.bank_account
    assessment = engine.assess(
        engine.OnboardingFacts(
            legal_name=body.legal_name,
            license_name=body.license_name,
            tax_id=body.tax_id,
            country=body.country,
            holder_name=bank.holder_name,
            account_type=bank.account_type.value,
            bank_country=bank.bank_country,
        ),
        kyb_service.load_sanctions(),
        allowed,
        kyb_service.thresholds(),
    )
    now, today = _now(), date.today()
    party = Party(
        id=uuid.uuid4(),
        code=f"P-{uuid.uuid4().hex[:12].upper()}",
        kind=kind,
        legal_name=body.legal_name,
        license_name=body.license_name,
        license_no=body.license_no,
        tax_id=body.tax_id,
        city=body.city,
        country=body.country,
        first_seen_on=today,
        kyb_status=KybStatus.PENDING,
    )
    user = User(
        id=uuid.uuid4(),
        email=identity.email,
        display_name=body.display_name,
        role=Role(body.account_type),
        language=Language(body.language),
        party_id=party.id,
        is_demo=False,
        auth_subject=identity.subject,
        status=UserStatus.PENDING,
    )
    review = OnboardingReview(
        id=uuid.uuid4(),
        user_id=user.id,
        party_id=party.id,
        status=OnboardingStatus.PENDING,
        checks=_stored(assessment.checks),
        score=assessment.score,
        submitted_at=now,
    )
    try:
        db.add(party)
        db.flush()
        db.add(user)
        db.flush()
        db.add_all(
            [
                PartyMember(
                    id=uuid.uuid4(),
                    party_id=party.id,
                    user_id=user.id,
                    member_role=MemberRole.OWNER,
                ),
                BankAccount(
                    id=uuid.uuid4(),
                    party_id=party.id,
                    bank_name=bank.bank_name,
                    bank_country=bank.bank_country,
                    account_number=bank.account_number,
                    holder_name=bank.holder_name,
                    account_type=AccountType(bank.account_type),
                    currency=bank.currency,
                    status=AccountStatus.PENDING_CHANGE,
                    opened_on=today,
                    first_seen_on=today,
                    verified=False,
                    change_requested_via="ONBOARDING",
                    change_requested_at=now,
                ),
                review,
            ]
        )
        db.flush()
        write_audit(
            db,
            actor="user",
            action="onboarding.submitted",
            tier=0,
            params={
                "review_id": str(review.id),
                "party_id": str(party.id),
                "user_id": str(user.id),
                "kind": kind.value,
                "recommendation": assessment.recommendation,
                "score": assessment.score,
            },
            result="pending",
            actor_id=str(user.id),
        )
        if assessment.recommendation == "BLOCK":
            write_audit(
                db,
                actor="system",
                action="onboarding.blocked",
                tier=3,
                params={
                    "review_id": str(review.id),
                    "party_id": str(party.id),
                    "reason_code": "SANCTIONS_SCREEN",
                },
                result="blocked",
            )
        elif settings.onboarding_auto_approve and assessment.recommendation == "AUTO_CLEAR":
            _apply(db, review, None, approve=True, reason=None)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(
            "this sign-in or email already has an account", code="ONBOARDING_EXISTS"
        ) from exc
    return status_for(db, user)


def _apply(
    db: Session,
    review: OnboardingReview,
    admin: CurrentUser | None,
    *,
    approve: bool,
    reason: str | None,
) -> None:
    """The one decision path (admin click or system auto-approval). Caller commits."""
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    now = _now()
    review.status = OnboardingStatus.APPROVED if approve else OnboardingStatus.REJECTED
    review.decided_at = now
    review.decided_by = admin.id if admin else None
    review.reason = reason
    accounts = db.scalars(select(BankAccount).where(BankAccount.party_id == party.id)).all()
    if approve:
        user.status = UserStatus.ACTIVE
        party.kyb_status = KybStatus.VERIFIED
        party.onboarded_at = now
        for a in accounts:
            if a.status == AccountStatus.PENDING_CHANGE:
                a.status, a.verified = AccountStatus.ACTIVE, True
    else:
        user.status = UserStatus.SUSPENDED
        party.kyb_status = KybStatus.FAILED
        for a in accounts:
            a.status = AccountStatus.RETIRED
    write_audit(
        db,
        actor="user" if admin else "system",
        action="onboarding.approved" if approve else "onboarding.rejected",
        tier=2,
        params={
            "review_id": str(review.id),
            "party_id": str(party.id),
            "user_id": str(user.id),
            "auto": admin is None,
        },
        result="approved" if approve else "rejected",
        actor_id=str(admin.id) if admin else None,
    )


def decide(
    db: Session, admin: CurrentUser, review_id: uuid.UUID, *, approve: bool, reason: str | None
) -> ReviewOut:
    review = db.scalar(
        select(OnboardingReview).where(OnboardingReview.id == review_id).with_for_update()
    )
    if review is None:
        raise NotFound("onboarding review not found")
    if review.user_id == admin.id:
        raise Forbidden("you cannot decide your own onboarding", code="SELF_DECISION")
    if review.status != OnboardingStatus.PENDING:
        raise Conflict("this review was already decided", code="ONBOARDING_DECIDED")
    _apply(db, review, admin, approve=approve, reason=reason)
    db.commit()
    return review_out(db, review)


def status_for(db: Session, user: User) -> OnboardingStatusOut:
    review = db.scalar(
        select(OnboardingReview)
        .where(OnboardingReview.user_id == user.id)
        .order_by(OnboardingReview.submitted_at.desc())
        .limit(1)
    )
    party = db.get(Party, user.party_id) if user.party_id else None
    if review is not None:
        status = review.status.value
    else:  # admin or invited member: no own submission
        status = {"ACTIVE": "APPROVED", "SUSPENDED": "REJECTED"}.get(user.status.value, "PENDING")
    public = [
        PublicCheck.model_validate(c)
        for c in (review.checks if review else [])
        if c["code"] != "SANCTIONS_SCREEN"  # never reveal a screening hit to the applicant
    ]
    return OnboardingStatusOut(
        status=status,  # type: ignore[arg-type]
        account_status=user.status.value,  # type: ignore[arg-type]
        role=user.role.value,  # type: ignore[arg-type]
        party_name=party.legal_name if party else None,
        checks=public,
        submitted_at=review.submitted_at if review else None,
        decided_at=review.decided_at if review else None,
        reason=review.reason if review else None,
    )


def identity_status(db: Session, identity: neon.NeonIdentity) -> OnboardingStatusOut:
    user = local_user(db, identity)
    if user is None:
        raise NotFound("this sign-in has not been onboarded", code="NOT_ONBOARDED")
    return status_for(db, user)


def review_out(db: Session, review: OnboardingReview) -> ReviewOut:
    user = db.get(User, review.user_id)
    party = db.get(Party, review.party_id)
    assert user is not None and party is not None
    account = db.scalar(
        select(BankAccount)
        .where(BankAccount.party_id == party.id)
        .order_by(BankAccount.created_at)
        .limit(1)
    )
    checks = _loaded(review.checks)
    return ReviewOut(
        id=review.id,
        status=review.status.value,  # type: ignore[arg-type]
        recommendation=engine.recommend(checks),
        score=review.score,
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
        checks=[AdminCheck(code=c.code, status=c.status, detail=c.detail) for c in checks],
        submitted_at=review.submitted_at,
        decided_at=review.decided_at,
        decided_by=review.decided_by,
        reason=review.reason,
    )


def list_reviews(db: Session, status: OnboardingStatus | None) -> ReviewList:
    q = select(OnboardingReview).order_by(OnboardingReview.submitted_at.desc()).limit(200)
    if status is not None:
        q = q.where(OnboardingReview.status == status)
    return ReviewList(items=[review_out(db, r) for r in db.scalars(q)])


def get_review(db: Session, review_id: uuid.UUID) -> ReviewOut:
    review = db.get(OnboardingReview, review_id)
    if review is None:
        raise NotFound("onboarding review not found")
    return review_out(db, review)
