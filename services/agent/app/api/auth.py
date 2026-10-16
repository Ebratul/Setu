"""Demo "login as" endpoints (stub; see app/auth/demo.py). Demo users only, no passwords."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.demo import COOKIE_NAME, MAX_AGE_SECONDS, make_token
from app.auth.deps import CurrentUser, current_user, to_current
from app.config import get_settings
from app.db.models import Party, User
from app.db.session import get_db
from app.errors import NotFound

router = APIRouter(prefix="/auth", tags=["auth"])

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


@router.get("/demo-users", response_model=DemoUsers)
def demo_users(db: Db) -> DemoUsers:
    """Seeded demo users for the "Login as" screen."""
    users = db.scalars(select(User).where(User.is_demo.is_(True)).order_by(User.email)).all()
    return DemoUsers(users=[_out(db, to_current(u)) for u in users])


@router.post("/demo-login", response_model=DemoUserOut)
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


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = 204
    return response
