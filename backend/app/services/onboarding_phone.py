"""Mobile-number confirmation by a 6-digit code. The code is stored only as an HMAC, lives 5
minutes, is single use, may be requested 3 times per 10 minutes and guessed 5 times. `demo_code`
is returned only when DEMO_MODE=true (the console SMS provider sends nothing anywhere)."""

import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import PhoneVerification, User
from app.errors import Conflict, DomainError, Gone, Locked, ServiceUnavailable, TooManyRequests
from app.schemas.onboarding import OnboardingState, PhoneSent
from app.security import crypto
from app.services import onboarding, sms


def _now() -> datetime:
    return datetime.now(UTC)


def _code_hash(user_id: uuid.UUID, pv_id: uuid.UUID, code: str) -> str:
    return crypto.blind_index(f"phone-otp:{user_id}:{pv_id}", code)


def send(db: Session, user: User, *, now: datetime | None = None) -> PhoneSent:
    settings = get_settings()
    now = now or _now()
    profile = onboarding.editable_profile(db, user)
    mobile = onboarding.secure_of(profile).get("mobile")
    if not mobile:
        raise Conflict("save your mobile number first", code="MOBILE_REQUIRED")
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    recent = (
        db.scalar(
            select(func.count())
            .select_from(PhoneVerification)
            .where(
                PhoneVerification.user_id == user.id,
                PhoneVerification.created_at
                >= now - timedelta(seconds=settings.phone_otp_send_window_seconds),
            )
        )
        or 0
    )
    if recent >= settings.phone_otp_max_sends:
        raise TooManyRequests(
            "too many codes requested; try again in a few minutes", code="OTP_RATE_LIMIT"
        )
    code = f"{secrets.randbelow(10**6):06d}"
    pv_id = uuid.uuid4()
    ttl = settings.phone_otp_ttl_seconds
    try:
        sms.get_provider().send(
            sms.Sms(to=mobile, text=f"Setu verification code: {code}. Valid {ttl // 60} minutes.")
        )
    except sms.SmsError as exc:
        raise ServiceUnavailable("could not send the code", "SMS_UNAVAILABLE") from exc
    db.add(
        PhoneVerification(
            id=pv_id,
            user_id=user.id,
            phone_masked=crypto.mask_phone(mobile),
            phone_hash=crypto.blind_index("phone", mobile),
            code_hash=_code_hash(user.id, pv_id, code),
            expires_at=now + timedelta(seconds=ttl),
            attempts=0,
            created_at=now,
        )
    )
    onboarding.audit(db, user, "onboarding.phone_sent", {})
    db.commit()
    return PhoneSent(
        expires_in_seconds=ttl,
        sends_left=settings.phone_otp_max_sends - recent - 1,
        demo_code=code if settings.demo_enabled and settings.demo_mode else None,
    )


def verify(db: Session, user: User, code: str, *, now: datetime | None = None) -> OnboardingState:
    settings = get_settings()
    now = now or _now()
    profile = onboarding.editable_profile(db, user)
    mobile = onboarding.secure_of(profile).get("mobile")
    row = None
    if mobile:
        row = db.scalar(
            select(PhoneVerification)
            .where(
                PhoneVerification.user_id == user.id,
                PhoneVerification.verified_at.is_(None),
                PhoneVerification.phone_hash == crypto.blind_index("phone", mobile),
            )
            .order_by(PhoneVerification.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    if row is None:
        raise DomainError("ask for a new code", "OTP_NOT_SENT")
    if row.attempts >= settings.phone_otp_max_attempts:
        raise Locked("too many wrong codes; ask for a new one", code="OTP_LOCKED")
    if row.expires_at < now:
        raise Gone("this code has expired; ask for a new one", code="OTP_EXPIRED")
    if not hmac.compare_digest(_code_hash(user.id, row.id, code), row.code_hash.strip()):
        row.attempts += 1
        left = settings.phone_otp_max_attempts - row.attempts
        onboarding.audit(
            db, user, "onboarding.phone_failed", {"attempts": row.attempts}, result="failed"
        )
        db.commit()
        if left <= 0:
            raise Locked("too many wrong codes; ask for a new one", code="OTP_LOCKED")
        raise DomainError(f"wrong code, {left} tries left", "OTP_INVALID")
    row.verified_at = now
    row.attempts += 1
    # a code is single use: any older open code for this user is dead too
    for other in db.scalars(
        select(PhoneVerification).where(
            PhoneVerification.user_id == user.id, PhoneVerification.verified_at.is_(None)
        )
    ):
        other.expires_at = now - timedelta(seconds=1)
    onboarding.audit(db, user, "onboarding.phone_verified", {})
    profile.step = max(profile.step, 2)
    db.commit()
    return onboarding.state_for(db, user)
