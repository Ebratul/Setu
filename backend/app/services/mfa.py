"""TOTP second factor (RFC 6238, app/security/totp.py). The secret is Fernet-encrypted at rest and
only shown once, at setup. `mfa_enabled` turns true after the first valid code. Recovery codes
(10, shown once) are stored as HMAC hashes and each works once. Admins cannot turn it off. The
email step-up (`/auth/stepup/verify`) also accepts a TOTP or recovery code once it is enabled."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.ratelimit import check_limit
from app.audit.writer import write_audit
from app.auth.deps import has_mfa
from app.config import get_settings
from app.db.enums import Role
from app.db.models import AuditLog, User
from app.errors import Conflict, DomainError, Forbidden, TooManyRequests
from app.schemas.onboarding import RecoveryCodesOut, TotpSetupOut
from app.security import crypto, totp


def _limit(user_id: uuid.UUID) -> None:
    check_limit("mfa", str(user_id), get_settings().rate_limit_mfa_per_10min, 600)


def budget(db: Session, row: User) -> None:
    """Wrong-code budget kept in the signed audit log (so it holds across instances, unlike the
    in-process limiter): 429 once `rate_limit_mfa_per_10min` failures happened in 10 minutes."""
    since = datetime.now(UTC) - timedelta(seconds=600)
    failed = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "auth.mfa_failed",
                AuditLog.actor_id == str(row.id),
                AuditLog.ts >= since,
            )
        )
        or 0
    )
    if failed >= get_settings().rate_limit_mfa_per_10min:
        raise TooManyRequests("too many wrong codes; wait a few minutes", code="RATE_LIMITED")


def record_failure(db: Session, row: User) -> None:
    write_audit(
        db,
        actor="user",
        action="auth.mfa_failed",
        tier=0,
        params={},
        result="failed",
        actor_id=str(row.id),
    )
    db.commit()


def attempt(db: Session, row: User, code: str) -> bool:
    """`check_second_factor` with the DB-backed budget and an audit row for each failure."""
    budget(db, row)
    if check_second_factor(row, code):
        return True
    record_failure(db, row)
    return False


def _recovery_hash(user_id: uuid.UUID, code: str) -> str:
    return crypto.blind_index(f"recovery:{user_id}", totp.normalise_recovery(code))


def check_second_factor(row: User, code: str, *, now: float | None = None) -> bool:
    """True when `code` is a valid current TOTP (never twice) or an unused recovery code. Updates
    the replay guard / spends the recovery code on the row; the caller commits."""
    if not row.mfa_enabled or not row.mfa_secret_encrypted:
        return False
    secret = crypto.decrypt_text(row.mfa_secret_encrypted)
    step = totp.verify(secret, code, last_step=row.mfa_last_step, now=now)
    if step is not None:
        row.mfa_last_step = step
        return True
    digest = _recovery_hash(row.id, code)
    hashes = list(row.mfa_recovery_hashes or [])
    if digest in hashes:
        hashes.remove(digest)
        row.mfa_recovery_hashes = hashes
        return True
    return False


def _audit(db: Session, row: User, action: str) -> None:
    write_audit(
        db, actor="user", action=action, tier=2, params={}, result="ok", actor_id=str(row.id)
    )


def _lock(db: Session, row: User) -> None:
    """Serialise TOTP work on one user: two requests with the same code cannot both pass."""
    db.refresh(row, with_for_update=True)


def setup(db: Session, row: User) -> TotpSetupOut:
    _limit(row.id)
    _lock(db, row)
    if has_mfa(row):
        raise Conflict("two-factor authentication is already on", code="MFA_ALREADY_ENABLED")
    row.mfa_enabled = False  # a legacy flag without a secret was never a second factor
    secret = totp.new_secret()
    row.mfa_secret_encrypted = crypto.encrypt_text(secret)
    db.commit()
    return TotpSetupOut(otpauth_uri=totp.otpauth_uri(secret, row.email), secret=secret)


def _new_codes(row: User) -> list[str]:
    codes = totp.new_recovery_codes()
    row.mfa_recovery_hashes = [_recovery_hash(row.id, c) for c in codes]
    return codes


def enable(db: Session, row: User, code: str, *, now: float | None = None) -> RecoveryCodesOut:
    _limit(row.id)
    _lock(db, row)
    if has_mfa(row):
        raise Conflict("two-factor authentication is already on", code="MFA_ALREADY_ENABLED")
    if not row.mfa_secret_encrypted:
        raise DomainError("start the setup first", "MFA_NOT_STARTED")
    budget(db, row)
    step = totp.verify(crypto.decrypt_text(row.mfa_secret_encrypted), code, now=now)
    if step is None:
        record_failure(db, row)
        raise DomainError("that code is not right; check your authenticator", "MFA_INVALID_CODE")
    row.mfa_enabled = True
    row.mfa_last_step = step
    codes = _new_codes(row)
    _audit(db, row, "auth.mfa_enabled")
    if row.role == Role.ADMIN:
        from app.services import onboarding

        onboarding.activate_admin_if_ready(db, row)
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


def disable(db: Session, row: User, code: str) -> None:
    _limit(row.id)
    _lock(db, row)
    if row.role == Role.ADMIN:
        raise Forbidden("administrators cannot turn off two-factor authentication", "MFA_REQUIRED")
    if not attempt(db, row, code):
        raise DomainError("that code is not right", "MFA_INVALID_CODE")
    row.mfa_enabled = False
    row.mfa_secret_encrypted = None
    row.mfa_recovery_hashes = None
    row.mfa_last_step = None
    _audit(db, row, "auth.mfa_disabled")
    db.commit()


def regenerate(db: Session, row: User, code: str) -> RecoveryCodesOut:
    _limit(row.id)
    _lock(db, row)
    if not attempt(db, row, code):
        raise DomainError("that code is not right", "MFA_INVALID_CODE")
    codes = _new_codes(row)
    _audit(db, row, "auth.mfa_recovery_regenerated")
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)
