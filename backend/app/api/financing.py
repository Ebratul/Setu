import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_analysis_reader, verified_party_writer
from app.db.session import get_db
from app.schemas.analysis import InDec
from app.schemas.financing import (
    ApplicationList,
    ApplicationOut,
    ApplicationRequest,
    ApprovalOut,
    GapOut,
    ImpactOut,
    ImpactRequest,
    MatchOut,
    MatchRequest,
    ModeOut,
    ScheduleOut,
)
from app.services import financing

router = APIRouter(prefix="/financing", tags=["financing"])

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require_analysis_reader)]
Writer = Annotated[CurrentUser, Depends(verified_party_writer)]


@router.get("/gap", response_model=GapOut)
def gap(
    db: Db,
    user: Reader,
    party_id: uuid.UUID | None = None,
    deal_id: Annotated[str | None, Query(max_length=64)] = None,
    mode: ModeOut = "shortfall",
) -> GapOut:
    """Financing gap: the forecast shortfall, or the whole order (landed cost − available cash)."""
    return financing.get_gap(db, user, party_id, deal_id, mode)


@router.post("/match", response_model=MatchOut)
def match(body: MatchRequest, db: Db, user: Reader) -> MatchOut:
    """Compare every active option: eligibility with reasons, cost at its tenor, ranking."""
    return financing.match(db, user, body)


@router.get("/options/{option_id}/schedule", response_model=ScheduleOut)
def option_schedule(
    option_id: str,
    db: Db,
    user: Reader,
    amount: Annotated[InDec, Query()],
    start: date | None = None,
    party_id: uuid.UUID | None = None,
    deal_id: Annotated[str | None, Query(max_length=64)] = None,
) -> ScheduleOut:
    """Repayment schedule of one option (code or id) for an amount and start date."""
    return financing.get_schedule(db, user, option_id, amount, start, party_id, deal_id)


@router.post("/impact", response_model=ImpactOut)
def impact(body: ImpactRequest, db: Db, user: Reader) -> ImpactOut:
    """Before/after cash-flow forecast with the loan inflow and repayment. Saves nothing."""
    return financing.impact(db, user, body)


@router.post("/applications", response_model=ApplicationOut)
def apply(body: ApplicationRequest, db: Db, user: Writer) -> ApplicationOut:
    """Submit a simulated application (idempotent per deal + option + mode while active)."""
    return financing.apply(db, user, body)


@router.post("/applications/{application_id}/simulate-approval", response_model=ApprovalOut)
def simulate_approval(application_id: uuid.UUID, db: Db, user: Writer) -> ApprovalOut:
    """Demo only: the lender approves; adds the loan cash flows and recomputes alerts."""
    return financing.simulate_approval(db, user, application_id)


@router.get("/applications", response_model=ApplicationList)
def applications(db: Db, user: Reader, party_id: uuid.UUID | None = None) -> ApplicationList:
    return financing.list_applications(db, user, party_id)
