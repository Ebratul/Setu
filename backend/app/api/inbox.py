"""E-mail check (buyer) and the supplier's in-app payout account change (Phase 17, SR-6)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user, require_verified
from app.db.session import get_db
from app.schemas.approvals import (
    AccountChangeIn,
    AccountChangeList,
    AccountChangeRequestOut,
    EmailCheckIn,
    EmailCheckOut,
)
from app.services import inbox, supplier_accounts

router = APIRouter(tags=["inbox"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
Verified = Annotated[CurrentUser, Depends(require_verified)]


class DemoEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


@router.post("/inbox/email-check", response_model=EmailCheckOut)
def email_check(body: EmailCheckIn, db: Db, user: User) -> EmailCheckOut:
    """Read a pasted e-mail as data. A request to pay another account is BLOCKED, never applied."""
    return inbox.check_email(db, user, body.text, body.deal_reference)


@router.get("/inbox/demo-email", response_model=DemoEmail)
def demo_email(user: User) -> DemoEmail:
    """The fictional redirection e-mail of the demo (404 unless DEMO_MODE is on)."""
    return DemoEmail(text=inbox.demo_email_text())


@router.post(
    "/supplier/accounts/change-request", response_model=AccountChangeRequestOut, status_code=202
)
def request_change(body: AccountChangeIn, db: Db, user: Verified) -> AccountChangeRequestOut:
    """Supplier portal only. Parks the account as PENDING_CHANGE, re-runs KYB and opens a Tier 3
    request for the buyer. Nothing is paid to it until the buyer approves."""
    return supplier_accounts.request_change(db, user, body)


@router.get("/supplier/accounts/change-requests", response_model=AccountChangeList)
def change_requests(db: Db, user: User) -> AccountChangeList:
    return supplier_accounts.list_requests(db, user)
