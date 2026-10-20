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

from fastapi import Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.audit.writer import current_actor_id, write_audit
from app.auth import neon
from app.auth.demo import COOKIE_NAME, parse_token
from app.config import get_settings
from app.db.enums import Role, UserStatus
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.errors import DomainError, Forbidden, ServiceUnavailable, Unauthorized

READ_ALL_ROLES = frozenset({Role.ADMIN, Role.JUDGE})


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    language: str
    party_id: uuid.UUID | None

    @property
    def reads_all(self) -> bool:
        return self.role in READ_ALL_ROLES


def to_current(user: User) -> CurrentUser:
    return CurrentUser(
        user.id, user.email, user.display_name, user.role, user.language, user.party_id
    )


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def verified_identity(request: Request) -> neon.NeonIdentity:
    """The caller's Neon Auth identity from the bearer JWT (no local account needed yet)."""
    token = _bearer(request)
    if token is None:
        raise Unauthorized("sign in first", code="UNAUTHENTICATED")
    try:
        identity = neon.verify_token(token)
    except neon.TokenError as exc:
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
    if user is None:
        raise Forbidden(
            "this sign-in has no Setu account yet; finish onboarding", code="ACCOUNT_NOT_ONBOARDED"
        )
    if user.status == UserStatus.SUSPENDED:
        raise Forbidden("this account is suspended", code="ACCOUNT_SUSPENDED")
    if user.status != UserStatus.ACTIVE:
        raise Forbidden("your account is awaiting verification", code="ACCOUNT_PENDING")
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
    if get_settings().auth_mode == "neon":
        return to_current(require_active(local_user(db, verified_identity(request))))
    token = request.cookies.get(COOKIE_NAME)
    uid = parse_token(token) if token else None
    user = db.scalar(select(User).where(User.id == uid, User.is_demo.is_(True))) if uid else None
    if user is None:
        raise Unauthorized("sign in with a demo user first")
    return to_current(user)


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
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


@contextmanager
def _own_session() -> Iterator[Session]:
    yield from get_db()


def _actor_of(request: Request) -> uuid.UUID | None:
    with _own_session() as db:
        try:
            return current_user(request, db).id
        except DomainError:
            return None


async def bind_actor(request: Request) -> None:
    """App-wide dependency: tell the audit writer who is acting. In neon mode the demo cookie is
    never believed (the actor starts empty), and a request without a valid bearer stays anonymous.
    The database is only touched when a bearer token is present (so /health works without one)."""
    if get_settings().auth_mode != "neon":
        return
    current_actor_id.set(None)
    if _bearer(request) is None:
        return
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
    if user.role == Role.BUYER and user.party_id is not None:
        return user
    if user.role == Role.ADMIN:
        return user
    raise Forbidden("this demo user is read-only")
