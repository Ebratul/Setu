import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_analysis_reader, require_writer
from app.db.enums import AlertStatus
from app.db.session import get_db
from app.schemas.analysis import InDec
from app.schemas.cashflow import (
    AlertList,
    AlertOut,
    AlertStatusOut,
    DashboardOut,
    ForecastOut,
    RecomputeOut,
    ScenarioOut,
    ScenarioRequest,
)
from app.services import alerts, cashflow, dashboard, scenario

router = APIRouter(tags=["cashflow"])

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require_analysis_reader)]
Writer = Annotated[CurrentUser, Depends(require_writer)]


@router.get("/cashflow/forecast", response_model=ForecastOut)
def forecast(
    db: Db,
    user: Reader,
    party_id: uuid.UUID | None = None,
    days: Annotated[int, Query(ge=7, le=180)] = 90,
    min_buffer: Annotated[InDec | None, Query()] = None,
) -> ForecastOut:
    """Day-by-day 90-day forecast (opening, flows, closing) with weekly buckets."""
    return cashflow.get_forecast(db, user, party_id, days, min_buffer)


@router.post("/cashflow/scenario", response_model=ScenarioOut)
def what_if(body: ScenarioRequest, db: Db, user: Reader) -> ScenarioOut:
    """What-if: move/remove items, add a loan; returns forecast + alerts. Saves nothing."""
    return scenario.run(db, user, body)


@router.get("/alerts", response_model=AlertList)
def list_alerts(
    db: Db, user: Reader, party_id: uuid.UUID | None = None, status: AlertStatusOut | None = None
) -> AlertList:
    """Alerts for a buyer, critical first, then by due date."""
    return alerts.list_alerts(db, user, party_id, status)


@router.post("/alerts/recompute", response_model=RecomputeOut)
def recompute(db: Db, user: Writer, party_id: uuid.UUID | None = None) -> RecomputeOut:
    """Run the alert engine for a buyer (idempotent upsert + auto-resolve)."""
    return alerts.recompute(db, user, party_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge(alert_id: uuid.UUID, db: Db, user: Writer) -> AlertOut:
    return alerts.set_status(db, user, alert_id, AlertStatus.ACKNOWLEDGED)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve(alert_id: uuid.UUID, db: Db, user: Writer) -> AlertOut:
    return alerts.set_status(db, user, alert_id, AlertStatus.RESOLVED)


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Db, user: Reader, party_id: uuid.UUID | None = None) -> DashboardOut:
    """Buyer home: cash, escrow, next-30-day outflows, top alerts, approvals, deals, month."""
    return dashboard.dashboard(db, user, party_id)
