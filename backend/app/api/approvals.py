"""Approval inbox and decisions (Phase 17). Humans only: nothing here is an agent tool. The body of
approve carries at most an OTP; the action and its parameters are the ones stored when the engine
escalated, and the service re-runs the risk engine before it executes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user, not_viewer
from app.config import get_settings
from app.db.session import get_db
from app.schemas.approvals import (
    ApprovalList,
    ApprovalOut,
    ApproveIn,
    ApproveResult,
    DemoPhoneOut,
    NotificationsOut,
    PhoneMessage,
    RejectIn,
    RejectResult,
    ResendResult,
    SimScenario,
    SimulateOut,
    TimelineOut,
)
from app.services import approvals, deals, simulator

router = APIRouter(tags=["approvals"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
Decider = Annotated[CurrentUser, Depends(not_viewer)]  # a party VIEWER may read, never decide


@router.get("/approvals", response_model=ApprovalList)
def list_approvals(
    db: Db,
    user: User,
    status: Annotated[str | None, Query(max_length=16, pattern=r"^[A-Za-z]+$")] = None,
) -> ApprovalList:
    """`status=pending` (open), `status=history` (decided/ended) or one exact status."""
    return approvals.list_approvals(db, user, status)


@router.get("/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: uuid.UUID, db: Db, user: User) -> ApprovalOut:
    """One request with its evidence snapshot (KYB, documents, registry, FX, rule trace)."""
    return approvals.get_approval(db, user, approval_id)


@router.post("/approvals/{approval_id}/approve", response_model=ApproveResult)
def approve(
    approval_id: uuid.UUID, body: ApproveIn, request: Request, db: Db, user: Decider
) -> ApproveResult:
    """Tier 2: one tap (plus a step-up token in neon mode: 403 STEPUP_REQUIRED). Tier 3: needs the
    6-digit code and the end of the cooling-off. Executes the stored action only; re-escalates
    instead if conditions got worse since the request was made. 403 FOUR_EYES when you requested
    it yourself and a colleague could approve instead."""
    return approvals.approve(
        db, user, approval_id, body.otp, stepup_token=request.headers.get("x-stepup")
    )


@router.post("/approvals/{approval_id}/reject", response_model=RejectResult)
def reject(approval_id: uuid.UUID, body: RejectIn, db: Db, user: Decider) -> RejectResult:
    return RejectResult(approval=approvals.reject(db, user, approval_id, body.reason))


@router.post("/approvals/{approval_id}/cancel", response_model=RejectResult)
def cancel(approval_id: uuid.UUID, db: Db, user: Decider) -> RejectResult:
    """Withdraw an open Tier 3 request (also during its cooling-off)."""
    return RejectResult(approval=approvals.cancel(db, user, approval_id))


@router.post("/approvals/{approval_id}/resend-otp", response_model=ResendResult)
def resend_otp(approval_id: uuid.UUID, db: Db, user: Decider) -> ResendResult:
    """New code: emailed to the buyer's OWNER/FINANCE members (neon) or the simulated phone (demo).
    The code is never in this response. 503 if the mail could not be sent; try again."""
    out, delivered = approvals.resend_otp(db, user, approval_id)
    return ResendResult(
        approval=out,
        delivered_to_demo_phone=delivered,
        delivered_by_email=get_settings().auth_mode == "neon",
    )


@router.get("/demo/phone", response_model=DemoPhoneOut)
def demo_phone(db: Db, user: User) -> DemoPhoneOut:
    """The simulated SMS inbox. 404 unless DEMO_MODE is on; buyer (or admin) only."""
    rows = approvals.demo_phone(db, user)
    return DemoPhoneOut(
        messages=[
            PhoneMessage(
                id=m.id,
                approval_id=m.approval_id,
                body=m.body,
                code=m.code,
                created_at=m.created_at,
            )
            for m in rows
        ]
    )


@router.post("/demo/simulate/{scenario}", response_model=SimulateOut)
def simulate(scenario: SimScenario, db: Db, user: User) -> SimulateOut:
    """Judge-mode scam simulator (demo only): runs the real flow and explains the response."""
    return simulator.run(db, user, scenario)


@router.get("/notifications", response_model=NotificationsOut)
def notifications(
    db: Db, user: User, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> NotificationsOut:
    return approvals.notifications(db, user, limit)


@router.post("/notifications/read")
def mark_read(db: Db, user: User) -> dict[str, int]:
    return {"marked": approvals.mark_read(db, user)}


@router.get("/deals/{deal_id}/timeline", response_model=TimelineOut)
def deal_timeline(
    deal_id: str, db: Db, user: User, approval_id: uuid.UUID | None = None
) -> TimelineOut:
    """Agent proposed -> risk engine decided -> human approved -> executed, with audit links."""
    return approvals.timeline(db, user, deals.find_deal(db, user, deal_id), approval_id)
