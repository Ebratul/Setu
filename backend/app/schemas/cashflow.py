"""FR-2 cash-flow, alert and dashboard API models. Money is a decimal string in the buyer's cash
currency (`currency`); dashboard KPIs also carry USD/BDT/CNY `Amounts`."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import Amounts, CurrencyCode, DecStr, InDec, MonthStr, Out

AlertTypeOut = Literal["SHORTFALL", "DEADLINE", "FX_OPPORTUNITY", "KYB_WARNING", "FRAUD", "INFO"]
SeverityOut = Literal["INFO", "WARNING", "CRITICAL"]
AlertStatusOut = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class FlowOut(Out):
    ref: str
    on: date
    direction: Literal["IN", "OUT"]
    amount: DecStr
    kind: str
    label: str
    deal_ref: str | None
    milestone_seq: int | None


class DayOut(Out):
    on: date
    opening: DecStr
    inflow: DecStr
    outflow: DecStr
    net: DecStr
    closing: DecStr
    below_buffer: bool
    items: list[FlowOut]


class WeekOut(Out):
    start: date
    end: date
    inflow: DecStr
    outflow: DecStr
    closing: DecStr
    lowest: DecStr


class ShortfallOut(Out):
    on: date
    amount: DecStr


class ForecastOut(Out):
    simulated: Literal[True] = True
    scenario: bool
    party_id: uuid.UUID
    party_name: str
    currency: CurrencyCode
    start: date
    end: date
    opening_balance: DecStr
    min_buffer: DecStr
    lowest_balance: DecStr
    lowest_on: date
    cover_amount: DecStr
    first_shortfall: ShortfallOut | None
    total_inflow: DecStr
    total_outflow: DecStr
    daily: list[DayOut]
    weekly: list[WeekOut]
    facts: list[str]


class AlertAction(Out):
    code: str
    label_en: str
    label_bn: str
    route: str
    query: dict[str, str]


class AlertPreview(Out):
    key: str
    type: AlertTypeOut
    severity: SeverityOut
    title_en: str
    title_bn: str
    message_en: str
    message_bn: str
    amount: DecStr | None
    currency: str | None
    due_on: date | None
    deal_ref: str | None
    milestone_seq: int | None
    action: AlertAction | None
    facts: dict[str, Any]


class AlertOut(AlertPreview):
    id: uuid.UUID
    status: AlertStatusOut
    created_at: datetime


class AlertList(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    alerts: list[AlertOut]


class RecomputeOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    created: int
    updated: int
    reopened: int
    resolved: int
    open: int


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: Annotated[str, Field(max_length=120)]
    on: date


class LoanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: InDec
    on: date
    repay_on: date | None = None
    repay_amount: InDec | None = None


class ScenarioRequest(BaseModel):
    """What-if overrides. Nothing is saved."""

    model_config = ConfigDict(extra="forbid")

    party_id: uuid.UUID | None = None
    days: Annotated[int, Field(ge=7, le=180)] = 90
    min_buffer: InDec | None = None
    moves: Annotated[list[MoveIn], Field(max_length=20)] = []
    removes: Annotated[list[Annotated[str, Field(max_length=120)]], Field(max_length=50)] = []
    loans: Annotated[list[LoanIn], Field(max_length=5)] = []


class ScenarioOut(Out):
    simulated: Literal[True] = True
    forecast: ForecastOut
    alerts: list[AlertPreview]


class NextMilestone(Out):
    seq: int
    trigger: str
    amount: Amounts
    due_on: date
    status: str


class DashboardDeal(Out):
    reference: str
    title: str
    status: str
    supplier_name: str
    goods_value: Amounts
    next_milestone: NextMilestone | None


class DashboardMonth(Out):
    month: MonthStr
    deals_count: int
    total_purchases: Amounts
    total_landed_cost: Amounts
    average_margin_pct: DecStr | None


class DashboardOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    party_name: str
    currency: CurrencyCode
    today: date
    cash_balance: Amounts
    in_escrow: Amounts
    due_next_30_days: Amounts
    open_alerts_count: int
    alerts: list[AlertOut]
    pending_approvals: int
    deals_by_status: dict[str, int]
    active_deals: list[DashboardDeal]
    lowest_balance: DecStr
    lowest_on: date
    first_shortfall: ShortfallOut | None
    month: DashboardMonth
