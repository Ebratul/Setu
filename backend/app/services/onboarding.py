"""Multi-step self-service onboarding (P30). The caller has a verified Neon sign-in; the server
chooses role and status. Steps: role -> contact (+ phone code) -> business -> documents ->
consent (+ TOTP for admins) -> submit. Submit runs the automated checks (app/domain/onboarding_kyb)
and moves the account to PENDING_VERIFICATION; a human then approves it
(app/services/onboarding_review.py). Nothing here is reachable from the LLM tool layer.

Data layout: `OnboardingProfile.data` holds non-sensitive and *masked* values only; the full phone,
licence/IRC/TIN/USCC and bank account numbers live in `OnboardingProfile.secure` (Fernet JSON)."""

import hashlib
import hmac
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.ratelimit import check_limit, over_limit, record_hit
from app.audit.writer import write_audit
from app.auth import neon
from app.auth.deps import has_mfa, local_user, require_active
from app.config import get_settings
from app.db.enums import (
    AccountStatus,
    AccountType,
    KybStatus,
    Language,
    MemberRole,
    OnboardingDecision,
    OnboardingStatus,
    PartyKind,
    Role,
    UserStatus,
)
from app.db.models import (
    AuditLog,
    BankAccount,
    OnboardingProfile,
    OnboardingReview,
    Party,
    PartyMember,
    PhoneVerification,
    User,
    VerificationDocument,
)
from app.domain import onboarding_kyb as engine
from app.domain import onboarding_validation as rules
from app.errors import Conflict, Forbidden, TooManyRequests, Unprocessable
from app.schemas.onboarding import (
    BuyerBusinessIn,
    ChangeRequestOut,
    ConsentIn,
    ConsentOut,
    ContactIn,
    ContactOut,
    MfaOut,
    OnboardingState,
    PublicCheck,
    RoleIn,
    StepOut,
    SupplierBusinessIn,
    VerificationDocumentOut,
)
from app.security import crypto
from app.services import kyb as kyb_service

STEP_KEYS = ("role", "contact", "business", "documents", "security", "review")
HIDDEN_FROM_APPLICANT = {"SANCTIONS_SCREEN"}
GENERIC_DETAIL = {
    "DUPLICATE_COMPANY": "needs manual review",
    "DOC_HASH_REUSE": "needs manual review",
}
BANK_ACCOUNT_TYPES = {"CORPORATE": AccountType.CORPORATE, "PERSONAL": AccountType.PERSONAL}


def _now() -> datetime:
    return datetime.now(UTC)


def audit(
    db: Session,
    user: User,
    action: str,
    params: dict[str, Any],
    *,
    result: str = "ok",
    tier: int = 0,
) -> None:
    """One signed audit row about `user`; params carry ids and field names, never PII values."""
    write_audit(
        db,
        actor="user",
        action=action,
        tier=tier,
        params=params,
        result=result,
        actor_id=str(user.id),
    )


def profile_of(db: Session, user: User) -> OnboardingProfile | None:
    return db.scalar(select(OnboardingProfile).where(OnboardingProfile.user_id == user.id))


def secure_of(profile: OnboardingProfile) -> dict[str, Any]:
    return crypto.decrypt_json(profile.secure)


def save_secure(profile: OnboardingProfile, secure: dict[str, Any]) -> None:
    profile.secure = crypto.encrypt_json(secure)


def _touch(profile: OnboardingProfile, **sections: Any) -> None:
    """Replace whole sections of the JSONB `data` (reassigning so the change is tracked)."""
    profile.data = {**(profile.data or {}), **sections}


def account_user(db: Session, identity: neon.NeonIdentity) -> User:
    """The caller's local account (any status except suspended/rejected/deleted)."""
    user = require_active(local_user(db, identity))
    return user


def editable_profile(db: Session, user: User) -> OnboardingProfile:
    """The profile, only while the applicant may still change it (PENDING_PROFILE)."""
    profile = profile_of(db, user)
    if profile is None:
        raise Conflict("choose your account type first", code="ROLE_REQUIRED")
    if user.status != UserStatus.PENDING_PROFILE:
        raise Conflict(
            "your details are with the review team and cannot be changed now",
            code="PROFILE_LOCKED",
        )
    return profile


# --- state -----------------------------------------------------------------------------------


def phone_verified(db: Session, user: User, profile: OnboardingProfile) -> bool:
    mobile = secure_of(profile).get("mobile")
    if not mobile:
        return False
    return (
        db.scalar(
            select(func.count())
            .select_from(PhoneVerification)
            .where(
                PhoneVerification.user_id == user.id,
                PhoneVerification.verified_at.is_not(None),
                PhoneVerification.phone_hash == crypto.blind_index("phone", mobile),
            )
        )
        or 0
    ) > 0


def required_doc_types(role: Role) -> frozenset[str]:
    return engine.REQUIRED_DOCS.get(role.value, frozenset())


def doc_out(d: VerificationDocument) -> VerificationDocumentOut:
    return VerificationDocumentOut(
        id=d.id,
        type=d.type.value,  # type: ignore[arg-type]
        original_name=d.original_name,
        mime=d.mime,
        size=d.size,
        status=d.status.value,  # type: ignore[arg-type]
        reviewer_notes=d.reviewer_notes,
        created_at=d.created_at,
    )


def documents_of(db: Session, user: User) -> list[VerificationDocument]:
    return list(
        db.scalars(
            select(VerificationDocument)
            .where(VerificationDocument.user_id == user.id)
            .order_by(VerificationDocument.created_at, VerificationDocument.id)
        )
    )


def contact_out(db: Session, user: User, profile: OnboardingProfile) -> ContactOut | None:
    c = (profile.data or {}).get("contact")
    if not c:
        return None
    return ContactOut(
        full_name=c["full_name"],
        designation=c["designation"],
        mobile_masked=c["mobile_masked"],
        phone_verified=phone_verified(db, user, profile),
        language=c["language"],
    )


def public_checks(rows: list[dict[str, Any]]) -> list[PublicCheck]:
    out: list[PublicCheck] = []
    for c in rows:
        if c["code"] in HIDDEN_FROM_APPLICANT:
            continue
        detail = (
            GENERIC_DETAIL.get(c["code"], c["detail"]) if c["status"] != "PASS" else c["detail"]
        )
        out.append(PublicCheck(code=c["code"], status=c["status"], detail=detail))
    return out


def latest_review(db: Session, user: User) -> OnboardingReview | None:
    return db.scalar(
        select(OnboardingReview)
        .where(OnboardingReview.user_id == user.id)
        .order_by(OnboardingReview.submitted_at.desc())
        .limit(1)
    )


def _steps(db: Session, user: User, profile: OnboardingProfile | None) -> list[StepOut]:
    judge = user.role == Role.JUDGE
    if profile is None:
        done = {k: judge or user.status == UserStatus.ACTIVE for k in STEP_KEYS}
        return [StepOut(key=k, done=done[k]) for k in STEP_KEYS]  # type: ignore[arg-type]
    data = profile.data or {}
    business_role = user.role in (Role.BUYER, Role.SUPPLIER)
    docs = {d.type.value for d in documents_of(db, user)}
    contact_done = user.role == Role.ADMIN or (
        bool(data.get("contact")) and phone_verified(db, user, profile)
    )
    security_done = bool(data.get("consent")) and (user.role != Role.ADMIN or has_mfa(user))
    done = {
        "role": True,
        "contact": contact_done,
        "business": bool(data.get("business")) if business_role else True,
        "documents": required_doc_types(user.role) <= docs if business_role else True,
        "security": security_done,
        "review": user.status != UserStatus.PENDING_PROFILE,
    }
    return [StepOut(key=k, done=done[k]) for k in STEP_KEYS]  # type: ignore[arg-type]


def state_for(db: Session, user: User | None) -> OnboardingState:
    settings = get_settings()
    if user is None:
        return OnboardingState(
            account_status=None,
            role=None,
            step=0,
            steps=[StepOut(key=k, done=False) for k in STEP_KEYS],  # type: ignore[arg-type]
            contact=None,
            business=None,
            documents=[],
            consent=None,
            mfa=MfaOut(enabled=False, required=False),
            checks=[],
            submitted_at=None,
            decision=None,
            change_requests=[],
            terms_version=settings.terms_version,
            demo_mode=settings.demo_enabled,
        )
    profile = profile_of(db, user)
    steps = _steps(db, user, profile)
    step = next((i for i, s in enumerate(steps) if not s.done), len(steps))
    review = latest_review(db, user)
    data = (profile.data if profile else None) or {}
    consent = data.get("consent")
    return OnboardingState(
        account_status=user.status.value,  # type: ignore[arg-type]
        role=user.role.value,  # type: ignore[arg-type]
        step=step,
        steps=steps,
        contact=contact_out(db, user, profile) if profile else None,
        business=data.get("business"),
        documents=[doc_out(d) for d in documents_of(db, user)],
        consent=ConsentOut(
            terms_version=consent["terms_version"],
            accepted_at=datetime.fromisoformat(consent["accepted_at"]),
        )
        if consent
        else None,
        mfa=MfaOut(enabled=has_mfa(user), required=user.role == Role.ADMIN),
        checks=public_checks(review.checks) if review else [],
        submitted_at=profile.submitted_at if profile else None,
        decision=profile.decision.value if profile and profile.decision else None,  # type: ignore[arg-type]
        change_requests=[
            ChangeRequestOut(target=c["target"], note=c["note"])
            for c in (profile.change_requests if profile else [])
        ],
        terms_version=settings.terms_version,
        demo_mode=settings.demo_enabled,
    )


# --- role ------------------------------------------------------------------------------------


def _invite_ok(code: str | None) -> bool:
    """Constant-time comparison against every configured code (no early exit)."""
    given = (code or "").encode()
    ok = False
    for candidate in get_settings().judge_codes:
        ok |= hmac.compare_digest(given, candidate.encode())
    return ok


def choose_role(db: Session, identity: neon.NeonIdentity, body: RoleIn, ip: str) -> OnboardingState:
    settings = get_settings()
    existing = local_user(db, identity)
    if existing is not None:
        require_active(existing)
    allowlisted = identity.email.lower() in settings.admin_allowlist
    requested = Role(body.role)
    subject = "sub:" + hashlib.sha256(identity.subject.encode()).hexdigest()[:16]
    if requested in (Role.JUDGE, Role.ADMIN) and not allowlisted:
        # guessing budget for invite codes / forbidden roles, per address and per identity (the
        # identity one is counted in the signed audit log, so it holds across instances);
        # ordinary sign-ups are not counted, so a shared office address is never locked out
        over_limit("onboarding-role", ip, settings.rate_limit_role_per_10min, 600)
        _subject_budget(db, subject)
    if allowlisted:
        role = Role.ADMIN  # forced: an allowlisted address cannot sign up as anything else
    elif requested == Role.ADMIN:
        _deny(db, subject, "role_not_allowed", ip)
        raise Forbidden("this address cannot register as an administrator", code="ROLE_NOT_ALLOWED")
    else:
        role = requested
    if role == Role.JUDGE and not _invite_ok(body.invite_code):
        _deny(db, subject, "invalid_invite_code", ip)
        raise Forbidden("that invite code is not valid", code="INVALID_INVITE_CODE")

    if existing is not None:
        profile = profile_of(db, existing)
        if existing.role == role:
            return state_for(db, existing)
        locked = (
            existing.status != UserStatus.PENDING_PROFILE
            or profile is None
            or (profile.data or {}).get("contact")
            or (profile.data or {}).get("business")
        )
        if locked:
            raise Conflict("your account type is already set", code="ROLE_LOCKED")
        existing.role = role
        profile.role = role  # type: ignore[union-attr]
        if role == Role.JUDGE:  # judges have no steps to finish: same result as a fresh sign-up
            existing.status = UserStatus.ACTIVE
        audit(db, existing, "onboarding.role_selected", {"role": role.value, "changed": True})
        db.commit()
        return state_for(db, existing)

    taken = db.scalar(select(User.id).where(func.lower(User.email) == identity.email))
    if taken is not None:
        raise Conflict("this email address is already used by another account", code="EMAIL_IN_USE")
    now = _now()
    user = User(
        id=uuid.uuid4(),
        email=identity.email,
        display_name=(identity.name or identity.email.split("@")[0])[:120].ljust(2, "_"),
        role=role,
        language=Language.EN,
        party_id=None,
        is_demo=False,
        auth_subject=identity.subject,
        auth_provider="neon",
        email_verified_at=now,
        status=UserStatus.ACTIVE if role == Role.JUDGE else UserStatus.PENDING_PROFILE,
        last_login_at=now,
    )
    try:
        db.add(user)
        db.flush()
        if role != Role.JUDGE:
            db.add(
                OnboardingProfile(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    role=role,
                    step=1,
                    data={},
                    change_requests=[],
                    revision=0,
                )
            )
        audit(db, user, "onboarding.role_selected", {"role": role.value, "changed": False})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("this sign-in already has an account", code="ONBOARDING_EXISTS") from exc
    return state_for(db, user)


def _subject_budget(db: Session, subject: str) -> None:
    since = _now() - timedelta(seconds=600)
    denied = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "auth.login_denied",
                AuditLog.actor_id == subject,
                AuditLog.ts >= since,
            )
        )
        or 0
    )
    if denied >= get_settings().rate_limit_role_per_10min:
        raise TooManyRequests("too many wrong attempts; wait a few minutes", code="RATE_LIMITED")


def _deny(db: Session, subject: str, reason: str, ip: str) -> None:
    """Audit a refused role/invite attempt under the hashed Neon subject (works before an account
    exists, and never records the code that was tried)."""
    write_audit(
        db,
        actor="user",
        action="auth.login_denied",
        tier=0,
        params={"reason": reason},
        result="denied",
        actor_id=subject,
    )
    db.commit()
    record_hit("onboarding-role", ip, get_settings().rate_limit_role_per_10min, 600)


# --- contact / business / consent ------------------------------------------------------------


def save_contact(db: Session, user: User, body: ContactIn) -> OnboardingState:
    profile = editable_profile(db, user)
    if user.role == Role.BUYER and rules.normalise_bd_mobile(body.mobile) is None:
        raise Unprocessable("enter a Bangladesh mobile number", code="INVALID_BD_MOBILE")
    secure = secure_of(profile)
    secure["mobile"] = body.mobile
    save_secure(profile, secure)
    _touch(
        profile,
        contact={
            "full_name": body.full_name,
            "designation": body.designation,
            "mobile_masked": crypto.mask_phone(body.mobile),
            "language": body.language,
        },
    )
    user.display_name = body.full_name
    user.language = Language(body.language)
    profile.step = max(profile.step, 2)
    audit(db, user, "onboarding.profile_saved", {"section": "contact"})
    db.commit()
    return state_for(db, user)


def _split_buyer(b: BuyerBusinessIn) -> tuple[dict[str, Any], dict[str, Any], str]:
    shown = {
        "legal_name": b.legal_name,
        "trade_name": b.trade_name,
        "trade_license_no_masked": crypto.mask_tail(b.trade_license_no),
        "license_authority": b.license_authority,
        "license_expiry": b.license_expiry.isoformat(),
        "irc_no_masked": crypto.mask_tail(b.irc_no),
        "tin_masked": crypto.mask_tail(b.tin),
        "address": b.address.model_dump(),
        "business_type": b.business_type,
        "main_import_goods": b.main_import_goods,
        "monthly_import_volume": b.monthly_import_volume,
    }
    secret = {"trade_license_no": b.trade_license_no, "irc_no": b.irc_no, "tin": b.tin}
    dedupe = crypto.blind_index("dedupe:BUYER", crypto.normalise_id(b.trade_license_no))
    return shown, secret, dedupe


def _split_supplier(b: SupplierBusinessIn) -> tuple[dict[str, Any], dict[str, Any], str]:
    shown = {
        "legal_name_en": b.legal_name_en,
        "legal_name_zh": b.legal_name_zh,
        "uscc_masked": crypto.mask_tail(b.uscc),
        "address": b.address.model_dump(),
        "business_scope": b.business_scope,
        "export_experience_years": b.export_experience_years,
        "wechat_id": b.wechat_id,
        "contact_phone_masked": crypto.mask_tail(b.contact_phone) if b.contact_phone else None,
        "bank": {
            "bank_name": b.bank.bank_name,
            "holder_name": b.bank.holder_name,
            "account_masked": crypto.mask_tail(b.bank.account_no),
            "currency": b.bank.currency,
            "swift": b.bank.swift,
        },
    }
    secret = {
        "uscc": b.uscc,
        "bank_account_no": b.bank.account_no,
        "contact_phone": b.contact_phone,
    }
    dedupe = crypto.blind_index("dedupe:SUPPLIER", crypto.normalise_id(b.uscc))
    return shown, secret, dedupe


def save_business(
    db: Session, user: User, body: BuyerBusinessIn | SupplierBusinessIn
) -> OnboardingState:
    if user.role not in (Role.BUYER, Role.SUPPLIER):
        raise Conflict("this account type has no business details", code="NOT_APPLICABLE")
    wants = BuyerBusinessIn if user.role == Role.BUYER else SupplierBusinessIn
    if not isinstance(body, wants):
        raise Unprocessable(
            "these business details do not match your account type",
            "ROLE_MISMATCH",
            [{"field": "body", "code": "ROLE_MISMATCH", "message": "wrong form for your role"}],
        )
    profile = editable_profile(db, user)
    if isinstance(body, BuyerBusinessIn):
        shown, secret, dedupe = _split_buyer(body)
    else:
        shown, secret, dedupe = _split_supplier(body)
    secure = secure_of(profile)
    secure["business"] = secret
    save_secure(profile, secure)
    _touch(profile, business=shown, dedupe_key_hmac=dedupe)
    profile.step = max(profile.step, 3)
    audit(db, user, "onboarding.profile_saved", {"section": "business"})
    db.commit()
    return state_for(db, user)


def save_consent(db: Session, user: User, body: ConsentIn) -> OnboardingState:
    settings = get_settings()
    profile = editable_profile(db, user)
    if body.terms_version != settings.terms_version:
        raise Conflict(
            "the terms were updated; reload and read the current version",
            code="TERMS_VERSION_MISMATCH",
        )
    now = _now()
    user.terms_accepted_at = now
    user.privacy_accepted_at = now
    user.terms_version = body.terms_version
    _touch(
        profile,
        consent={
            "terms_version": body.terms_version,
            "accepted_at": now.isoformat(),
            "consent_verification": True,
        },
    )
    profile.step = max(profile.step, 5)
    audit(db, user, "onboarding.profile_saved", {"section": "consent"})
    activate_admin_if_ready(db, user)
    db.commit()
    return state_for(db, user)


def activate_admin_if_ready(db: Session, user: User) -> None:
    """An allowlisted admin becomes ACTIVE once TOTP is on and the terms are accepted (whichever
    comes last). Caller commits."""
    if user.role != Role.ADMIN or user.status != UserStatus.PENDING_PROFILE or not has_mfa(user):
        return
    profile = profile_of(db, user)
    if profile is None or not (profile.data or {}).get("consent"):
        return
    user.status = UserStatus.ACTIVE
    profile.submitted_at = _now()
    audit(db, user, "onboarding.submitted", {"role": "ADMIN"}, result="activated")


# --- submit ----------------------------------------------------------------------------------


def _missing(db: Session, user: User, profile: OnboardingProfile) -> list[str]:
    steps = {s.key: s.done for s in _steps(db, user, profile)}
    return [k for k in ("contact", "business", "documents", "security") if not steps[k]]


def _dup_party(db: Session, kind: PartyKind, dedupe: str, user: User) -> uuid.UUID | None:
    """Another business already using this licence / USCC: an approved party, or a different
    applicant's live submission. Flagged for the admins, never merged."""
    party = db.scalar(
        select(Party.id).where(
            Party.kind == kind, Party.dedupe_key == dedupe, Party.id != _own(user)
        )
    )
    if party is not None:
        return party
    other = db.scalar(
        select(OnboardingProfile.user_id).where(
            OnboardingProfile.user_id != user.id,
            OnboardingProfile.submitted_at.is_not(None),
            OnboardingProfile.data["dedupe_key_hmac"].astext == dedupe,
            OnboardingProfile.decision.is_distinct_from(OnboardingDecision.REJECTED),
        )
    )
    if other is None:
        return None
    return db.scalar(select(User.party_id).where(User.id == other))


def _own(user: User) -> uuid.UUID:
    return user.party_id or uuid.UUID(int=0)


def _hash_reused(db: Session, user: User) -> bool:
    mine = [d.sha256 for d in documents_of(db, user)]
    if not mine:
        return False
    return (
        db.scalar(
            select(func.count())
            .select_from(VerificationDocument)
            .where(VerificationDocument.sha256.in_(mine), VerificationDocument.user_id != user.id)
        )
        or 0
    ) > 0


def _facts(
    db: Session, user: User, profile: OnboardingProfile, dup: uuid.UUID | None
) -> engine.ProfileFacts:
    data = profile.data or {}
    b = data["business"]
    docs = frozenset(d.type.value for d in documents_of(db, user) if d.status.value != "REJECTED")
    base: dict[str, Any] = {
        "contact_name": data["contact"]["full_name"],
        "today": date.today(),
        "duplicate_of_other_company": dup is not None,
        "phone_verified": phone_verified(db, user, profile),
        "doc_types": docs,
        "reused_hash": _hash_reused(db, user),
    }
    if user.role == Role.BUYER:
        return engine.ProfileFacts(
            role="BUYER",
            legal_name=b["legal_name"],
            license_expiry=date.fromisoformat(b["license_expiry"]),
            **base,
        )
    return engine.ProfileFacts(
        role="SUPPLIER",
        legal_name=b["legal_name_en"],
        holder_name=b["bank"]["holder_name"],
        swift_country=b["bank"]["swift"][4:6],
        **base,
    )


def _upsert_party(db: Session, user: User, profile: OnboardingProfile) -> Party:
    data = profile.data or {}
    b = data["business"]
    buyer = user.role == Role.BUYER
    values: dict[str, Any] = {
        "kind": PartyKind.BUYER if buyer else PartyKind.SUPPLIER,
        "legal_name": b["legal_name"] if buyer else b["legal_name_en"],
        "license_no": b["trade_license_no_masked"] if buyer else b["uscc_masked"],
        "tax_id": b["tin_masked"] if buyer else None,
        "city": (b["address"]["district"] if buyer else b["address"]["city"])[:80],
        "country": "BD" if buyer else "CN",
    }
    party = db.get(Party, user.party_id) if user.party_id else None
    if party is None:
        party = Party(
            id=uuid.uuid4(),
            code=f"P-{uuid.uuid4().hex[:12].upper()}",
            first_seen_on=date.today(),
            kyb_status=KybStatus.PENDING,
            **values,
        )
        db.add(party)
        db.flush()
        user.party_id = party.id
        db.add(
            PartyMember(
                id=uuid.uuid4(), party_id=party.id, user_id=user.id, member_role=MemberRole.OWNER
            )
        )
    else:
        for k, v in values.items():
            setattr(party, k, v)
        party.kyb_status = KybStatus.PENDING
    return party


def _upsert_bank(db: Session, party: Party, profile: OnboardingProfile) -> None:
    b = (profile.data or {})["business"]["bank"]
    number = secure_of(profile)["business"]["bank_account_no"]
    now, today = _now(), date.today()
    corporate = bool(engine.COMPANY_MARKERS.search(b["holder_name"]))
    account = db.scalar(
        select(BankAccount).where(BankAccount.party_id == party.id).order_by(BankAccount.created_at)
    )
    values: dict[str, Any] = {
        "bank_name": b["bank_name"],
        "bank_country": b["swift"][4:6],
        "account_number": crypto.mask_tail(number),
        "account_number_encrypted": crypto.encrypt_text(number),
        "account_number_hmac": crypto.blind_index("bank", crypto.normalise_id(number)),
        "holder_name": b["holder_name"],
        "account_type": BANK_ACCOUNT_TYPES["CORPORATE" if corporate else "PERSONAL"],
        "currency": b["currency"],
        "status": AccountStatus.PENDING_CHANGE,
        "verified": False,
        "change_requested_via": "ONBOARDING",
        "change_requested_at": now,
    }
    if account is None:
        db.add(
            BankAccount(
                id=uuid.uuid4(),
                party_id=party.id,
                opened_on=today,
                first_seen_on=today,
                **values,
            )
        )
    else:
        for k, v in values.items():
            setattr(account, k, v)


def submit(db: Session, user: User) -> OnboardingState:
    settings = get_settings()
    check_limit("onboarding-submit", str(user.id), settings.rate_limit_submit_per_hour, 3600)
    if user.role == Role.JUDGE:
        raise Conflict("judge accounts have nothing to submit", code="NOT_APPLICABLE")
    if user.role == Role.ADMIN:
        return _submit_admin(db, user)
    profile = editable_profile(db, user)
    missing = _missing(db, user, profile)
    if missing:
        raise Unprocessable(
            "finish the earlier steps first",
            "STEP_INCOMPLETE",
            [{"field": k, "code": "INCOMPLETE", "message": "step not finished"} for k in missing],
        )
    data = profile.data or {}
    kind = PartyKind.BUYER if user.role == Role.BUYER else PartyKind.SUPPLIER
    dup = _dup_party(db, kind, data["dedupe_key_hmac"], user)
    facts = _facts(db, user, profile, dup)
    assessment = engine.assess_profile(
        facts,
        kyb_service.load_sanctions(),
        settings.onboarding_country_list,
        kyb_service.thresholds(),
    )
    stored = [{"code": c.code, "status": c.status, "detail": c.detail} for c in assessment.checks]
    if dup is not None:
        for c in stored:
            if c["code"] == "DUPLICATE_COMPANY":
                c["detail"] += f" (earlier party {dup})"
    now = _now()
    party = _upsert_party(db, user, profile)
    if user.role == Role.SUPPLIER:
        _upsert_bank(db, party, profile)
    review = OnboardingReview(
        id=uuid.uuid4(),
        user_id=user.id,
        party_id=party.id,
        status=OnboardingStatus.PENDING,
        checks=stored,
        score=assessment.score,
        submitted_at=now,
    )
    db.add(review)
    user.status = UserStatus.PENDING_VERIFICATION
    profile.submitted_at = now
    profile.decision = None
    profile.change_requests = []
    profile.revision += 1
    profile.step = 6
    db.flush()
    audit(
        db,
        user,
        "onboarding.submitted",
        {
            "review_id": str(review.id),
            "party_id": str(party.id),
            "role": user.role.value,
            "revision": profile.revision,
            "recommendation": assessment.recommendation,
            "risk_summary": engine.risk_summary(assessment.checks),
        },
        result="pending",
    )
    if assessment.recommendation == "BLOCK":
        write_audit(
            db,
            actor="system",
            action="onboarding.blocked",
            tier=3,
            params={"review_id": str(review.id), "reason_code": "SANCTIONS_SCREEN"},
            result="blocked",
        )
    elif settings.onboarding_auto_approve and assessment.recommendation == "AUTO_CLEAR":
        from app.services import onboarding_review

        onboarding_review.apply_approve(db, review, None)
    db.commit()
    return state_for(db, user)


def _submit_admin(db: Session, user: User) -> OnboardingState:
    profile = profile_of(db, user)
    if not has_mfa(user):
        raise Unprocessable(
            "turn on two-factor authentication to finish",
            "MFA_REQUIRED",
            [{"field": "security", "code": "MFA_REQUIRED", "message": "TOTP is required"}],
        )
    if profile is None or not (profile.data or {}).get("consent"):
        raise Unprocessable(
            "accept the terms first",
            "STEP_INCOMPLETE",
            [{"field": "security", "code": "INCOMPLETE", "message": "consent missing"}],
        )
    activate_admin_if_ready(db, user)
    db.commit()
    return state_for(db, user)
