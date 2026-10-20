"""Admin onboarding review queue. ADMIN only (judges are read-only even in demo). These are the
human decisions: they are never exposed as agent tools."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.guards import require_admin_stepup
from app.auth.deps import CurrentUser, require_admin
from app.db.enums import OnboardingStatus
from app.db.session import get_db
from app.schemas.onboarding import RejectIn, ReviewList, ReviewOut
from app.services import onboarding

router = APIRouter(prefix="/admin/onboarding", tags=["admin"])

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[CurrentUser, Depends(require_admin)]
AdminStepup = Annotated[CurrentUser, Depends(require_admin_stepup)]


@router.get("", response_model=ReviewList)
def list_reviews(db: Db, _: Admin, status: OnboardingStatus | None = None) -> ReviewList:
    return onboarding.list_reviews(db, status)


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: uuid.UUID, db: Db, _: Admin) -> ReviewOut:
    return onboarding.get_review(db, review_id)


@router.post("/{review_id}/approve", response_model=ReviewOut)
def approve(review_id: uuid.UUID, db: Db, admin: AdminStepup) -> ReviewOut:
    return onboarding.decide(db, admin, review_id, approve=True, reason=None)


@router.post("/{review_id}/reject", response_model=ReviewOut)
def reject(review_id: uuid.UUID, body: RejectIn, db: Db, admin: AdminStepup) -> ReviewOut:
    return onboarding.decide(db, admin, review_id, approve=False, reason=body.reason)
