"""Who is calling and what they may read. The swap point for real auth: routers and services
depend only on `CurrentUser`, `current_user` and the helpers here; `demo.py` only maps a cookie to a
user id."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.demo import COOKIE_NAME, parse_token
from app.db.enums import Role
from app.db.models import User
from app.db.session import get_db
from app.errors import Forbidden, Unauthorized

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


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    token = request.cookies.get(COOKIE_NAME)
    uid = parse_token(token) if token else None
    user = db.scalar(select(User).where(User.id == uid, User.is_demo.is_(True))) if uid else None
    if user is None:
        raise Unauthorized("sign in with a demo user first")
    return to_current(user)


def require_analysis_reader(user: Annotated[CurrentUser, Depends(current_user)]) -> CurrentUser:
    """Buyers (own data only) and admin/judge (all data) may read financial analysis."""
    if user.role == Role.BUYER and user.party_id is not None:
        return user
    if user.reads_all:
        return user
    raise Forbidden("financial analysis is available to buyers, admins and judges")


def can_read_party(user: CurrentUser, party_id: uuid.UUID) -> bool:
    return user.reads_all or user.party_id == party_id
