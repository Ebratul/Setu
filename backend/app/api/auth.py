"""Auth endpoints. `router` is always mounted: /auth/config, /auth/session (neon), /auth/me and
/auth/logout. `demo_router` (demo "login as", no passwords; see app/auth/demo.py) is mounted only
when AUTH_MODE=demo."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.demo import COOKIE_NAME, MAX_AGE_SECONDS, make_token
from app.auth.deps import (
    CurrentUser,
    audit_once,
    current_user,
    local_user,
    record_login,
    require_active,
    to_current,
    verified_identity,
)
from app.config import get_settings
from app.db.models import Party, User
from app.db.session import get_db
from app.errors import DomainError, Forbidden, NotFound
from app.services import stepup

router = APIRouter(prefix="/auth", tags=["auth"])
demo_router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[Session, Depends(get_db)]
RoleOut = Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"]
LanguageOut = Literal["en", "bn", "zh"]


class DemoUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str
    display_name: str
    role: RoleOut
    language: LanguageOut
    party_id: uuid.UUID | None
    party_name: str | None


class DemoUsers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demo: Literal[True] = True
    users: list[DemoUserOut]


class DemoLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str


def _out(db: Session, u: CurrentUser) -> DemoUserOut:
    party = db.get(Party, u.party_id) if u.party_id else None
    return DemoUserOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,  # type: ignore[arg-type]
        language=u.language,  # type: ignore[arg-type]
        party_id=u.party_id,
        party_name=party.legal_name if party else None,
    )


@demo_router.get("/demo-users", response_model=DemoUsers)
def demo_users(db: Db) -> DemoUsers:
    """Seeded demo users for the "Login as" screen."""
    users = db.scalars(select(User).where(User.is_demo.is_(True)).order_by(User.email)).all()
    return DemoUsers(users=[_out(db, to_current(u)) for u in users])


@demo_router.post("/demo-login", response_model=DemoUserOut)
def demo_login(body: DemoLoginIn, response: Response, db: Db) -> DemoUserOut:
    user = db.scalar(select(User).where(User.email == body.email, User.is_demo.is_(True)))
    if user is None:
        raise NotFound("unknown demo user")
    response.set_cookie(
        COOKIE_NAME,
        make_token(user.id),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=get_settings().demo_cookie_secure,
        path="/",
    )
    return _out(db, to_current(user))


@router.get("/me", response_model=DemoUserOut)
def me(db: Db, user: Annotated[CurrentUser, Depends(current_user)]) -> DemoUserOut:
    return _out(db, user)


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["demo", "neon"]


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Which sign-in the web app should show. Public; reveals no secrets."""
    return AuthConfig(mode=get_settings().auth_mode)


@router.post("/session", response_model=DemoUserOut)
def start_session(request: Request, db: Db) -> DemoUserOut:
    """Called once after a Neon sign-in: checks the bearer token, the account and its status,
    stamps `last_login_at` and writes the audit entry. Garbage tokens are rejected without an
    audit row (otherwise anyone could grow the chain)."""
    if get_settings().auth_mode != "neon":
        raise NotFound("not available in demo mode")
    identity = verified_identity(request)
    user = local_user(db, identity)
    try:
        user = require_active(user)
    except Forbidden as exc:
        if user is not None:  # no local actor yet (not onboarded) means nothing to attribute
            audit_once(db, user, "auth.login", "denied", {"reason": exc.code or ""})
            db.commit()
        raise
    record_login(db, user)
    audit_once(db, user, "auth.login", "ok", {}, within_s=60)
    db.commit()
    return _out(db, to_current(user))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Db) -> Response:
    """Demo: drop the cookie. Neon: the browser ends the Neon session; this only records it."""
    if get_settings().auth_mode == "neon":
        try:
            user = current_user(request, db)
        except DomainError:
            pass
        else:
            row = db.get(User, user.id)
            if row is not None:
                audit_once(db, row, "auth.logout", "ok", {}, within_s=60)
                db.commit()
    else:
        response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response


class StepupStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sent: Literal[True] = True
    expires_in_seconds: int
    starts_left: int


class StepupVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


class StepupToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    expires_in_seconds: int
    header: Literal["X-Stepup"] = "X-Stepup"


def _neon_only() -> None:
    if get_settings().auth_mode != "neon":
        raise NotFound("not available in demo mode")


@router.post("/stepup/start", response_model=StepupStarted)
def stepup_start(db: Db, user: Annotated[CurrentUser, Depends(current_user)]) -> StepupStarted:
    """Email a 6-digit confirmation code to the signed-in user's verified address. The code is in
    no response. 429 STEPUP_RATE_LIMIT after 3 codes in 15 minutes; 503 if the mail did not go."""
    _neon_only()
    ttl, left = stepup.start(db, user)
    return StepupStarted(expires_in_seconds=ttl, starts_left=left)


@router.post("/stepup/verify", response_model=StepupToken)
def stepup_verify(
    body: StepupVerifyIn, db: Db, user: Annotated[CurrentUser, Depends(current_user)]
) -> StepupToken:
    """Exchange the emailed code for a 10-minute `X-Stepup` token bound to this user."""
    _neon_only()
    token, ttl = stepup.verify(db, user, body.code)
    return StepupToken(token=token, expires_in_seconds=ttl)
