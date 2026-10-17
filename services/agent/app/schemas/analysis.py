"""FR-3 analysis API models. Money is a decimal string; every amount is given in USD, BDT and CNY
(converted server-side with the rates listed in `fx`) so the UI only formats, never computes."""

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DecStr = Annotated[str, Field(pattern=r"^-?\d+(\.\d+)?$", examples=["11200.00"])]
InDec = Annotated[str, Field(pattern=r"^\d{1,14}(\.\d{1,4})?$", examples=["9600.00"])]
CurrencyCode = Literal["USD", "BDT", "CNY"]
ExtraKind = Literal["FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER"]
LineKind = Literal["GOODS", "FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER"]
MarginBandOut = Literal["healthy", "thin", "low"]
MonthStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-10"])]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Amounts(Out):
    USD: DecStr
    BDT: DecStr
    CNY: DecStr


class FxRateOut(Out):
    base: CurrencyCode
    quote: CurrencyCode
    rate: DecStr
    as_of: date
    source: str


class Explanation(Out):
    code: str
    en: str
    bn: str


class DealSummary(Out):
    id: uuid.UUID
    reference: str
    title: str
    status: str
    buyer_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    supplier_kyb_status: str
    hs_code: str
    incoterm: str
    quantity: DecStr
    unit: str
    unit_price: DecStr
    currency: CurrencyCode
    goods_value: DecStr
    opened_on: date


class OrderList(Out):
    simulated: Literal[True] = True
    orders: list[DealSummary]


class CostLineOut(Out):
    kind: LineKind
    label: str | None
    amount: Amounts
    share_pct: DecStr


class TargetPrice(Out):
    margin_pct: DecStr
    price_per_unit: Amounts
    revenue: Amounts


class OrderAnalysis(Out):
    simulated: Literal[True] = True
    deal: DealSummary | None
    currency: CurrencyCode
    quantity: DecStr
    unit: str
    breakdown: list[CostLineOut]
    goods_value: Amounts
    extra_costs: Amounts
    landed_cost: Amounts
    cost_per_unit: Amounts
    expected_revenue: Amounts | None
    selling_price_per_unit: Amounts | None
    gross_margin: Amounts | None
    gross_margin_pct: DecStr | None
    markup_pct: DecStr | None
    margin_band: MarginBandOut | None
    break_even_price_per_unit: Amounts
    target: TargetPrice | None
    fx: list[FxRateOut]
    explanations: list[Explanation]
    facts: list[str]


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - pattern already guards
        raise ValueError("not a decimal") from exc


class CostLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExtraKind
    amount: InDec
    label: Annotated[str | None, Field(max_length=60)] = None


class LandedCostRequest(BaseModel):
    """What-if calculator input. Nothing is saved."""

    model_config = ConfigDict(extra="forbid")

    currency: CurrencyCode = "USD"
    goods_value: InDec
    quantity: InDec
    unit: Annotated[str, Field(min_length=1, max_length=8)] = "pcs"
    cost_lines: Annotated[list[CostLineIn], Field(max_length=20)] = []
    selling_price_per_unit: InDec | None = None
    target_margin_pct: InDec | None = None

    @field_validator("quantity")
    @classmethod
    def _positive(cls, v: str) -> str:
        if _decimal(v) <= 0:
            raise ValueError("quantity must be greater than 0")
        return v

    @field_validator("target_margin_pct")
    @classmethod
    def _below_100(cls, v: str | None) -> str | None:
        if v is not None and _decimal(v) >= 100:
            raise ValueError("target margin must be below 100%")
        return v


class MonthTotalsOut(Out):
    month: MonthStr
    deals_count: int
    total_purchases: Amounts
    total_landed_cost: Amounts
    expected_revenue: Amounts
    average_margin_pct: DecStr | None


class CostDriverOut(Out):
    kind: ExtraKind
    amount: Amounts
    share_pct: DecStr


class MonthlyChange(Out):
    purchases_delta: Amounts
    purchases_pct: DecStr | None
    deals_delta: int
    margin_delta_pts: DecStr | None


class MonthlyDeal(Out):
    reference: str
    title: str
    supplier_name: str
    status: str
    landed_cost: Amounts
    gross_margin_pct: DecStr | None


class MonthlySummaryOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    party_name: str
    month: MonthStr
    currency: CurrencyCode
    deals_count: int
    total_purchases: Amounts
    total_landed_cost: Amounts
    expected_revenue: Amounts
    average_margin_pct: DecStr | None
    top_cost_driver: CostDriverOut | None
    previous: MonthTotalsOut
    change: MonthlyChange
    history: list[MonthTotalsOut]
    deals: list[MonthlyDeal]
    insights: list[Explanation]
    fx: list[FxRateOut]
    facts: list[str]


class ScorePoint(Out):
    month: MonthStr
    score: DecStr


class SupplierScoreOut(Out):
    supplier_id: uuid.UUID
    code: str
    name: str
    city: str
    country: str
    kyb_status: str
    score: DecStr | None
    score_trend: list[ScorePoint]
    on_time_rate_pct: DecStr | None
    dispute_rate_pct: DecStr | None
    defect_rate_pct: DecStr | None
    doc_mismatch_count: int
    deals_count: int
    completed_deals_count: int
    your_deals_count: int
    price_index: DecStr | None
    flags: list[str]
    weak: bool
    notes: list[Explanation]


class SupplierScorecardOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID | None
    window_months: int
    suppliers: list[SupplierScoreOut]
    facts: list[str]
