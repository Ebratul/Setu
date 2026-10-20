"""Endpoint guards that need the step-up token (`X-Stepup`). Kept apart from app/auth/deps.py
because the step-up service itself depends on the auth module."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user, require_admin
from app.db.session import get_db
from app.services import stepup

Db = Annotated[Session, Depends(get_db)]


def require_stepup(
    request: Request, db: Db, user: Annotated[CurrentUser, Depends(current_user)]
) -> CurrentUser:
    """Signed-in user who also presented a valid step-up token (403 STEPUP_REQUIRED otherwise)."""
    stepup.require(db, user, request.headers.get(stepup.HEADER))
    return user


def require_admin_stepup(
    request: Request, db: Db, admin: Annotated[CurrentUser, Depends(require_admin)]
) -> CurrentUser:
    """ADMIN (checked first, so a non-admin never sees the prompt) with a valid step-up token."""
    stepup.require(db, admin, request.headers.get(stepup.HEADER))
    return admin
