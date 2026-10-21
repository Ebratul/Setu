"""Admin onboarding review. ADMIN with TOTP enabled only (judges are read-only even in demo).
Decisions also need a fresh step-up token (`X-Stepup`: emailed code, or a TOTP / recovery code).
These are human decisions: never exposed as agent tools."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.guards import require_admin_mfa_stepup
from app.auth.deps import CurrentUser, require_admin_mfa
from app.db.enums import OnboardingStatus, Role
from app.db.session import get_db
from app.schemas.onboarding import (
    RejectIn,
    RequestChangesIn,
    RevealIn,
    RevealOut,
    ReviewList,
    ReviewOut,
)
from app.services import onboarding_review

router = APIRouter(prefix="/admin/onboarding", tags=["admin"])

Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[CurrentUser, Depends(require_admin_mfa)]
AdminStepup = Annotated[CurrentUser, Depends(require_admin_mfa_stepup)]


@router.get("", response_model=ReviewList)
def list_reviews(
    db: Db, _: Admin, status: OnboardingStatus | None = None, role: Role | None = None
) -> ReviewList:
    return onboarding_review.list_reviews(db, status, role)


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: uuid.UUID, db: Db, _: Admin) -> ReviewOut:
    return onboarding_review.get_review(db, review_id)


@router.post("/{review_id}/reveal", response_model=RevealOut)
def reveal(review_id: uuid.UUID, body: RevealIn, db: Db, admin: Admin) -> RevealOut:
    """One sensitive value, in clear, once. Needs a reason; the audit entry holds the field name
    and reason, never the value."""
    return onboarding_review.reveal(db, admin, review_id, body.field, body.reason)


@router.post("/{review_id}/approve", response_model=ReviewOut)
def approve(review_id: uuid.UUID, db: Db, admin: AdminStepup) -> ReviewOut:
    return onboarding_review.approve(db, admin, review_id)


@router.post("/{review_id}/request-changes", response_model=ReviewOut)
def request_changes(
    review_id: uuid.UUID, body: RequestChangesIn, db: Db, admin: AdminStepup
) -> ReviewOut:
    return onboarding_review.request_changes(db, admin, review_id, body)


@router.post("/{review_id}/reject", response_model=ReviewOut)
def reject(review_id: uuid.UUID, body: RejectIn, db: Db, admin: AdminStepup) -> ReviewOut:
    return onboarding_review.reject(db, admin, review_id, body.reason)


@router.post("/{review_id}/suspend", response_model=ReviewOut)
def suspend(review_id: uuid.UUID, body: RejectIn, db: Db, admin: AdminStepup) -> ReviewOut:
    return onboarding_review.suspend(db, admin, review_id, body.reason)


@router.post("/{review_id}/auto-approve", response_model=ReviewOut)
def auto_approve(review_id: uuid.UUID, db: Db, admin: AdminStepup) -> ReviewOut:
    """Demo only: 404 unless DEMO_MODE=true."""
    return onboarding_review.auto_approve(db, admin, review_id)
