"""Self-service onboarding. Identity-only: the caller has a verified Neon sign-in but may not have
a Setu account yet (so these routes do not use `current_user`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import neon
from app.auth.deps import verified_identity
from app.config import get_settings
from app.db.session import get_db
from app.errors import NotFound
from app.schemas.onboarding import OnboardingIn, OnboardingStatusOut
from app.services import onboarding

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

Db = Annotated[Session, Depends(get_db)]


def _identity(request: Request) -> neon.NeonIdentity:
    if get_settings().auth_mode != "neon":
        raise NotFound("not available in demo mode")
    return verified_identity(request)


Identity = Annotated[neon.NeonIdentity, Depends(_identity)]


@router.post("", response_model=OnboardingStatusOut, status_code=201)
def submit(body: OnboardingIn, db: Db, identity: Identity) -> OnboardingStatusOut:
    """Create the business, owner account (PENDING) and review; the server picks the role."""
    return onboarding.submit(db, identity, body)


@router.get("/status", response_model=OnboardingStatusOut)
def status(db: Db, identity: Identity) -> OnboardingStatusOut:
    """Where the caller's onboarding stands (works while the account is still PENDING)."""
    return onboarding.identity_status(db, identity)
