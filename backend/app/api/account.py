"""The caller's own account: profile, language, data export and deletion request."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, lenient_user
from app.db.models import User
from app.db.session import get_db
from app.errors import NotFound
from app.schemas.onboarding import AccountOut, AccountPatch, DeleteRequested
from app.services import account

router = APIRouter(prefix="/account", tags=["account"])

Db = Annotated[Session, Depends(get_db)]
Me = Annotated[CurrentUser, Depends(lenient_user)]


def _row(db: Session, me: CurrentUser) -> User:
    row = db.get(User, me.id)
    if row is None:
        raise NotFound("account not found")
    return row


@router.get("", response_model=AccountOut)
def get_account(db: Db, me: Me) -> AccountOut:
    return account.account_out(db, _row(db, me))


def _real_row(db: Session, me: CurrentUser) -> User:
    """Seeded demo accounts are shared by every judge: they cannot be edited or deleted."""
    row = _row(db, me)
    if row.is_demo:
        raise NotFound("not available for demo accounts")
    return row


@router.patch("", response_model=AccountOut)
def patch_account(body: AccountPatch, db: Db, me: Me) -> AccountOut:
    return account.patch(db, _real_row(db, me), body)


@router.get("/export")
def export_account(db: Db, me: Me) -> dict[str, Any]:
    """A JSON copy of the caller's own data. Sensitive numbers stay masked."""
    return account.export(db, _row(db, me))


@router.post("/delete-request", response_model=DeleteRequested)
def delete_request(db: Db, me: Me) -> DeleteRequested:
    """Soft delete: the account is suspended and marked for erasure."""
    return account.delete_request(db, _real_row(db, me))
