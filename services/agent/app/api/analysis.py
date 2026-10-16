import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_analysis_reader
from app.db.session import get_db
from app.schemas.analysis import (
    LandedCostRequest,
    MonthlySummaryOut,
    OrderAnalysis,
    OrderList,
    SupplierScorecardOut,
)
from app.services import analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require_analysis_reader)]


@router.get("/orders", response_model=OrderList)
def list_orders(db: Db, user: Reader) -> OrderList:
    """Deals the caller may analyse (own deals for buyers; all for admin/judge)."""
    return analysis.list_orders(db, user)


@router.get("/orders/{deal_id}", response_model=OrderAnalysis)
def order_analysis(
    deal_id: str,
    db: Db,
    user: Reader,
    target_margin_pct: Annotated[
        Decimal | None, Query(ge=0, lt=100, description="Target gross margin in percent")
    ] = None,
) -> OrderAnalysis:
    """Landed cost breakdown, margin, break-even and explanations for one deal (reference or id)."""
    return analysis.order_analysis(db, user, deal_id, target_margin_pct)


@router.post("/landed-cost", response_model=OrderAnalysis)
def landed_cost_what_if(body: LandedCostRequest, db: Db, _: Reader) -> OrderAnalysis:
    """What-if landed cost calculator. Uses today's mock FX rates; saves nothing."""
    return analysis.what_if(db, body)


@router.get("/monthly", response_model=MonthlySummaryOut)
def monthly_summary(
    db: Db,
    user: Reader,
    party_id: uuid.UUID | None = None,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> MonthlySummaryOut:
    """Monthly purchase summary for a buyer with plain-language insights (EN + BN)."""
    return analysis.monthly(db, user, party_id, month)


@router.get("/suppliers", response_model=SupplierScorecardOut)
def supplier_scorecard(
    db: Db, user: Reader, party_id: uuid.UUID | None = None
) -> SupplierScorecardOut:
    """Supplier scorecard: on-time, disputes, price index, score 0-100 and KYB status."""
    return analysis.suppliers(db, user, party_id)
