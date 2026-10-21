"""Who is calling and what they may read. The swap point between demo and real auth: routers and
services depend only on `CurrentUser`, `current_user` and the helpers here. AUTH_MODE=neon maps a
Neon Auth bearer JWT to a local user; AUTH_MODE=demo maps the signed demo cookie (judge
deployment)."""

import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit.writer import current_actor_id, write_audit
from app.auth import neon
from app.auth.demo import COOKIE_NAME, parse_token
from app.config import get_settings
from app.db.enums import KybStatus, MemberRole, Role, UserStatus
from app.db.models import AuditLog, Party, PartyMember, User
from app.db.session import get_db
from app.errors import DomainError, Forbidden, ServiceUnavailable, Unauthorized

log = structlog.get_logger("setu.auth")

READ_ALL_ROLES = frozenset({Role.ADMIN, Role.JUDGE})


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    language: str
    party_id: uuid.UUID | None
    member_role: MemberRole = MemberRole.OWNER
    account_status: UserStatus = UserStatus.ACTIVE
    mfa_enabled: bool = False  # TOTP really on: flag set AND a secret stored
    is_demo: bool = False
    party_blocked: bool = False  # the business was rejected or suspended

    @property
    def verified(self) -> bool:
        return self.account_status == UserStatus.ACTIVE and not self.party_blocked

    @property
    def privileged(self) -> bool:
        """May use admin powers: ACTIVE with TOTP on. Only the seeded demo admins of the demo
        deployment (AUTH_MODE=demo) are exempt; never with AUTH_MODE=neon."""
        if self.role != Role.ADMIN:
            return True
        if self.account_status == UserStatus.ACTIVE and self.mfa_enabled:
            return True
        s = get_settings()
        return self.is_demo and s.auth_mode == "demo" and s.demo_mode and s.app_env != "prod"

    @property
    def reads_all(self) -> bool:
        return self.role in READ_ALL_ROLES and self.privileged


def has_mfa(user: User) -> bool:
    """TOTP counts only with a stored secret. A pre-P30 row whose flag was set by the old email
    step-up has no secret and does not count."""
    return bool(user.mfa_enabled and user.mfa_secret_encrypted)


def to_current(
    user: User, member_role: MemberRole = MemberRole.OWNER, party_blocked: bool = False
) -> CurrentUser:
    return CurrentUser(
        user.id,
        user.email,
        user.display_name,
        user.role,
        user.language,
        user.party_id,
        member_role,
        user.status,
        has_mfa(user),
        user.is_demo,
        party_blocked,
    )


def ensure_verified(user: CurrentUser) -> CurrentUser:
    """Money actions need a verified (ACTIVE) account: 403 ACCOUNT_NOT_VERIFIED. Called by the
    `Verified` router dependencies and again at the top of the service functions, so a service
    reached through another path (approval execution, tools) is guarded too."""
    if user.account_status != UserStatus.ACTIVE:
        raise Forbidden(
            "your account is not verified yet; money actions unlock after verification",
            code="ACCOUNT_NOT_VERIFIED",
        )
    if user.party_blocked:
        raise Forbidden("this business is suspended or was not approved", code="ACCOUNT_SUSPENDED")
    return user


def member_role_of(db: Session, user: User) -> MemberRole:
    """Party-level role from `party_members`; a user with a party and no row (seeded demo users)
    is the OWNER, so nothing existing changes."""
    if user.party_id is None:
        return MemberRole.OWNER
    role = db.scalar(
        select(PartyMember.member_role).where(
            PartyMember.party_id == user.party_id, PartyMember.user_id == user.id
        )
    )
    return role or MemberRole.OWNER


def current_of(db: Session, user: User) -> CurrentUser:
    blocked = False
    if user.party_id is not None and not user.is_demo:
        status = db.scalar(select(Party.kyb_status).where(Party.id == user.party_id))
        blocked = status == KybStatus.FAILED
    return to_current(user, member_role_of(db, user), blocked)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def verified_identity(request: Request) -> neon.NeonIdentity:
    """The caller's Neon Auth identity from the bearer JWT (no local account needed yet)."""
    token = _bearer(request)
    if token is None:
        log.warning("auth.no_bearer", path=request.url.path)
        raise Unauthorized("sign in first", code="UNAUTHENTICATED")
    try:
        identity = neon.verify_token(token)
    except neon.TokenError as exc:
        log.warning("auth.token_rejected", reason=str(exc), path=request.url.path)
        raise Unauthorized("your session is invalid or has expired", code="TOKEN_INVALID") from exc
    except neon.AuthUnavailable as exc:
        raise ServiceUnavailable("sign-in is temporarily unavailable") from exc
    if not identity.email_verified:
        raise Forbidden("verify your email address first", code="EMAIL_NOT_VERIFIED")
    return identity


def local_user(db: Session, identity: neon.NeonIdentity) -> User | None:
    """The account for a Neon identity. A real account created ahead of time (admin invite) is
    linked on the first sign-in with the same *verified* email; demo accounts never link."""
    user = db.scalar(select(User).where(User.auth_subject == identity.subject))
    if user is not None:
        return user
    user = db.scalar(
        select(User).where(
            func.lower(User.email) == identity.email,
            User.auth_subject.is_(None),
            User.is_demo.is_(False),
        )
    )
    if user is None:
        return None
    user.auth_subject = identity.subject
    write_audit(
        db,
        actor="user",
        action="auth.link",
        tier=0,
        params={"subject_sha256": hashlib.sha256(identity.subject.encode()).hexdigest()[:16]},
        result="ok",
        actor_id=str(user.id),
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(User).where(User.auth_subject == identity.subject))
    return user


def require_active(user: User | None) -> User:
    """Admit a local account to the API. PENDING_PROFILE / PENDING_VERIFICATION users get in (they
    finish onboarding and read their own workspace); money actions need `ensure_verified`."""
    if user is None:
        raise Forbidden(
            "this sign-in has no Setu account yet; finish onboarding", code="ACCOUNT_NOT_ONBOARDED"
        )
    if user.deleted_at is not None or user.status == UserStatus.SUSPENDED:
        raise Forbidden("this account is suspended", code="ACCOUNT_SUSPENDED")
    if user.status == UserStatus.REJECTED:
        raise Forbidden("this account was not approved", code="ACCOUNT_REJECTED")
    return user


def audit_once(
    db: Session, user: User, action: str, decision: str, params: dict[str, str], within_s: int = 300
) -> None:
    """Write an auth audit entry unless the same one was written for this user moments ago, so a
    client looping on /auth/session or /auth/logout cannot grow the signed chain without bound."""
    since = datetime.now(UTC) - timedelta(seconds=within_s)
    recent = db.scalar(
        select(AuditLog.seq)
        .where(
            AuditLog.actor_id == str(user.id),
            AuditLog.action == action,
            AuditLog.decision == decision,
            AuditLog.ts >= since,
        )
        .limit(1)
    )
    if recent is None:
        write_audit(
            db,
            actor="user",
            action=action,
            tier=0,
            params=params,
            result=decision,
            actor_id=str(user.id),
        )


def record_login(db: Session, user: User) -> None:
    user.last_login_at = datetime.now(UTC)
    db.commit()


def _resolve(request: Request, db: Session) -> CurrentUser:
    """A bearer token (neon mode) always wins. The signed demo cookie is believed only when
    DEMO_MODE=true and no bearer is present; it can only name a seeded demo user."""
    settings = get_settings()
    if settings.auth_mode == "neon" and _bearer(request) is not None:
        return current_of(db, require_active(local_user(db, verified_identity(request))))
    token = request.cookies.get(COOKIE_NAME) if settings.demo_login_enabled else None
    if token is None:
        if settings.auth_mode == "neon":
            return current_of(db, require_active(local_user(db, verified_identity(request))))
        raise Unauthorized("sign in with a demo user first")
    uid = parse_token(token)
    user = db.scalar(select(User).where(User.id == uid, User.is_demo.is_(True))) if uid else None
    if user is None:
        raise Unauthorized("sign in with a demo user first")
    return current_of(db, user)


def resolved_user(request: Request, db: Session) -> CurrentUser:
    """Who is calling, admitted (not rejected/suspended) but not yet checked for admin 2FA. Used
    by the routes an admin needs to *reach* 2FA: /auth/*, /account, onboarding documents."""
    cached = getattr(request.state, "auth_result", None)
    if cached is None:
        try:
            cached = _resolve(request, db)
        except DomainError as exc:
            cached = exc
        request.state.auth_result = cached
    if isinstance(cached, DomainError):
        raise cached
    return cached


def lenient_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    """Dependency form of `resolved_user` (no admin-2FA gate)."""
    return resolved_user(request, db)


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    """The caller for every other route. An ADMIN who is not ACTIVE with TOTP on is refused
    (403 MFA_REQUIRED) everywhere: admin rights are never granted before the second factor."""
    user = resolved_user(request, db)
    if not user.privileged:
        raise Forbidden("turn on two-factor authentication first", code="MFA_REQUIRED")
    return user


@contextmanager
def _own_session() -> Iterator[Session]:
    yield from get_db()


def _actor_of(request: Request) -> uuid.UUID | None:
    with _own_session() as db:
        try:
            return resolved_user(request, db).id
        except DomainError:
            return None


async def bind_actor(request: Request) -> None:
    """App-wide dependency: tell the audit writer who is acting. In neon mode the demo cookie is
    never believed unless DEMO_MODE=true and no bearer is sent (the audit middleware sets that
    actor). The database is only touched when a bearer token is present (so /health works)."""
    if get_settings().auth_mode != "neon":
        return
    if _bearer(request) is None:
        if not get_settings().demo_login_enabled:
            current_actor_id.set(None)
        return
    current_actor_id.set(None)
    try:
        uid = await run_in_threadpool(_actor_of, request)
    except DomainError:
        return
    if uid is not None:
        current_actor_id.set(str(uid))


def require_analysis_reader(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Buyers (own data only) and admin/judge (all data) may read financial analysis."""
    if user.role == Role.BUYER and user.party_id is not None:
        return user
    if user.reads_all:
        return user
    raise Forbidden("financial analysis is available to buyers, admins and judges")


def can_read_party(user: CurrentUser, party_id: uuid.UUID) -> bool:
    return user.reads_all or user.party_id == party_id


def require_writer(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Buyers (own data) and admins may change alert state; judges are read-only."""
    if user.member_role == MemberRole.VIEWER:
        raise Forbidden("viewers can read but not change anything", code="VIEWER_READ_ONLY")
    if user.role == Role.BUYER and user.party_id is not None:
        return user
    if user.role == Role.ADMIN:
        return user
    raise Forbidden("this demo user is read-only")


def not_viewer(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Any signed-in user except a party VIEWER (for mutating endpoints with their own role
    checks in the service layer)."""
    if user.member_role == MemberRole.VIEWER:
        raise Forbidden("viewers can read but not change anything", code="VIEWER_READ_ONLY")
    return user


def require_admin(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """ADMIN only (judges read everything but never decide anything)."""
    if user.role != Role.ADMIN:
        raise Forbidden("administrators only")
    return user


def require_admin_mfa(user: Annotated[CurrentUser, Depends(require_admin)]) -> CurrentUser:
    """ADMIN who is ACTIVE with TOTP on (403 MFA_REQUIRED). `current_user` already enforces it for
    every admin; this stays as the explicit name admin-only routes depend on."""
    if not user.privileged:
        raise Forbidden("turn on two-factor authentication first", code="MFA_REQUIRED")
    return user


def require_verified(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Signed in AND verified (ACTIVE): the base guard for read-write money endpoints."""
    return ensure_verified(user)


def verified_writer(user: Annotated[CurrentUser, Depends(not_viewer)]) -> CurrentUser:
    """Like `not_viewer` plus ACCOUNT_NOT_VERIFIED (viewer check first, as before)."""
    return ensure_verified(user)


def verified_party_writer(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Verified first (an applicant sees ACCOUNT_NOT_VERIFIED), then `require_writer`."""
    ensure_verified(user)
    return require_writer(user)
