"""Step-up verification: the practical second factor. Neon Auth has no TOTP plugin, so a sensitive
action needs a fresh email code on top of the sign-in. `start` mails a 6-digit code (HMAC at rest,
5 min, 3 wrong tries, 3 codes per 15 min); `verify` returns a signed `X-Stepup` token bound to the
user (HMAC over user id + expiry, 10 min). Endpoints that need it call `require`.

This proves control of the mailbox right now, not possession of a device: see docs/auth.md."""

import base64
import hashlib
import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.deps import CurrentUser, audit_once
from app.config import get_settings
from app.db.models import StepupChallenge, User
from app.errors import DomainError, Forbidden, TooManyRequests
from app.services import approval_otp, mail

MAX_ATTEMPTS = 3
MAX_STARTS = 3
START_WINDOW = timedelta(minutes=15)
HEADER = "X-Stepup"


def _now() -> datetime:
    return datetime.now(UTC)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _mac(label: str, payload: str) -> bytes:
    return hmac.new(
        approval_otp.secret_key(), f"{label}:{payload}".encode(), hashlib.sha256
    ).digest()


def _code_hash(user_id: uuid.UUID, challenge_id: uuid.UUID, code: str) -> str:
    return _mac("stepup-code", f"{user_id}:{challenge_id}:{code}").hex()


def make_token(user_id: uuid.UUID, *, now: int | None = None) -> tuple[str, int]:
    """`<user>.<expiry>.<mac>`; returns the token and its lifetime in seconds."""
    ttl = get_settings().stepup_token_ttl_seconds
    expires = (now if now is not None else int(time.time())) + ttl
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_b64(_mac('stepup-token', payload))}", ttl


def token_valid(token: str | None, user_id: uuid.UUID, *, now: int | None = None) -> bool:
    if not token or len(token) > 200:
        return False
    try:
        uid, expires, sig = token.split(".")
        expected = _b64(_mac("stepup-token", f"{uid}.{expires}"))
        if not hmac.compare_digest(sig.encode(), expected.encode()):
            return False
        if uuid.UUID(uid) != user_id:
            return False
        return int(expires) > (now if now is not None else int(time.time()))
    except (ValueError, TypeError, UnicodeError):
        return False


def _required() -> DomainError:
    return Forbidden("confirm with the code we email you first", code="STEPUP_REQUIRED")


def require(db: Session, user: CurrentUser, token: str | None) -> None:
    """Raise 403 STEPUP_REQUIRED unless step-up is off (demo mode / STEPUP_REQUIRED=false) or the
    token is a valid, unexpired one issued to this very user."""
    if not get_settings().stepup_enabled:
        return
    if token_valid(token, user.id):
        return
    if token:  # a presented-but-bad token is worth a (deduplicated) audit row; none at all is not
        row = db.get(User, user.id)
        if row is not None:
            audit_once(db, row, "auth.stepup", "failed", {"reason": "bad_token"})
            db.commit()
    raise _required()


def start(db: Session, user: CurrentUser, *, now: datetime | None = None) -> tuple[int, int]:
    """Mail a new code. Returns (code lifetime in seconds, codes still allowed in this window)."""
    now = now or _now()
    row = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if row is None:
        raise _required()
    recent = (
        db.scalar(
            select(func.count())
            .select_from(StepupChallenge)
            .where(
                StepupChallenge.user_id == user.id,
                StepupChallenge.created_at >= now - START_WINDOW,
            )
        )
        or 0
    )
    if recent >= MAX_STARTS:
        raise TooManyRequests(
            "too many codes requested; try again in a few minutes", code="STEPUP_RATE_LIMIT"
        )
    ttl = get_settings().stepup_code_ttl_seconds
    code = f"{secrets.randbelow(10**6):06d}"
    challenge_id = uuid.uuid4()
    message = mail.code_mail(
        row.email,
        code,
        subject=("Your Setu confirmation code", "আপনার সেতু নিশ্চিতকরণ কোড"),
        what=("Confirming a sensitive action in Setu", "সেতুতে একটি সংবেদনশীল কাজ নিশ্চিত করা"),
        reference=None,
        minutes=max(1, ttl // 60),
    )
    mail.deliver(message)  # raises ServiceUnavailable("could not send the code")
    db.add(
        StepupChallenge(
            id=challenge_id,
            user_id=user.id,
            code_hash=_code_hash(user.id, challenge_id, code),
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
    )
    db.commit()
    return ttl, MAX_STARTS - recent - 1


def verify(
    db: Session, user: CurrentUser, code: str, *, now: datetime | None = None
) -> tuple[str, int]:
    """Check the newest unused code. Returns (token, lifetime). A wrong code costs one of three
    tries on that code; the right one is single-use and sets `users.mfa_enabled`."""
    now = now or _now()
    row = db.scalar(select(User).where(User.id == user.id).with_for_update())
    challenge = db.scalar(
        select(StepupChallenge)
        .where(StepupChallenge.user_id == user.id, StepupChallenge.consumed_at.is_(None))
        .order_by(StepupChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None or challenge is None or challenge.expires_at < now:
        _failed(db, row, "no_active_code")
        raise DomainError("ask for a new code", "STEPUP_NO_CODE")
    if challenge.attempts >= MAX_ATTEMPTS:
        _failed(db, row, "locked")
        raise Forbidden("too many wrong codes; ask for a new one", code="STEPUP_LOCKED")
    if not hmac.compare_digest(
        _code_hash(user.id, challenge.id, code), challenge.code_hash.strip()
    ):
        challenge.attempts += 1
        left = MAX_ATTEMPTS - challenge.attempts
        _failed(db, row, "wrong_code")
        raise DomainError(f"wrong code, {left} tries left", "STEPUP_INVALID")
    challenge.consumed_at = now
    row.mfa_enabled = True
    token, ttl = make_token(user.id)
    write_audit(
        db,
        actor="user",
        action="auth.stepup",
        tier=0,
        params={},
        result="ok",
        actor_id=str(user.id),
    )
    db.commit()
    return token, ttl


def _failed(db: Session, row: User | None, reason: str) -> None:
    """Commit the attempt counter and (deduplicated) the audit row, then the caller raises."""
    if row is not None:
        audit_once(db, row, "auth.stepup", "failed", {"reason": reason})
    db.commit()
