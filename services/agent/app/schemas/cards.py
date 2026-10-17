"""Chat result cards: what agent tools return and the chat UI renders.

Envelope: {card_type, data, explanation_codes, explanation_en, explanation_bn, simulated}. Amounts
are decimal strings in `data.currency` (the deal or buyer home currency). Routes are internal
`/app/...` paths only. The explanation is the one-line plain-language "why" for the card.
"""

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import DecStr

APP_ROUTE_PATTERN = r"^/app(/[A-Za-z0-9_\-]+)*/?(\?[A-Za-z0-9_\-=&.%]*)?$"
AppRoute = Annotated[str, Field(pattern=APP_ROUTE_PATTERN)]
CardType = Literal[
    "citations",
    "landed_cost",
    "cashflow",
    "alerts",
    "financing_comparison",
    "fx_compare",
    "monthly_summary",
    "scorecard",
    "kyb",
]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Bilingual(_M):
    code: str
    en: str
    bn: str


class _Card(_M):
    explanation_codes: list[str]
    explanation_en: str
    explanation_bn: str
    simulated: Literal[True] = True


# --- landed_cost ----------------------------------------------------------------------------


class CostLine(_M):
    kind: str
    label: str | None
    amount: DecStr
    share_pct: DecStr


class LandedCostData(_M):
    deal_ref: str | None
    title: str | None
    defaulted_deal: bool = False
    currency: str
    quantity: DecStr
    unit: str
    lines: list[CostLine]
    goods_value: DecStr
    extra_costs: DecStr
    landed_cost: DecStr
    landed_cost_bdt: DecStr
    cost_per_unit: DecStr
    selling_price_per_unit: DecStr | None
    expected_revenue: DecStr | None
    gross_margin: DecStr | None
    gross_margin_pct: DecStr | None
    margin_band: str | None
    break_even_price_per_unit: DecStr
    analysis_route: AppRoute | None


class LandedCostCard(_Card):
    card_type: Literal["landed_cost"] = "landed_cost"
    data: LandedCostData


# --- cashflow -------------------------------------------------------------------------------


class Point(_M):
    on: date
    closing: DecStr


class Shortfall(_M):
    on: date
    amount: DecStr


class Payment(_M):
    on: date
    label: str
    kind: str
    amount: DecStr
    deal_ref: str | None


class CashflowSide(_M):
    series: list[Point]
    first_shortfall: Shortfall | None
    lowest_balance: DecStr
    lowest_on: date


class CashflowData(_M):
    currency: str
    start: date
    end: date
    opening_balance: DecStr
    min_buffer: DecStr
    before: CashflowSide
    after: CashflowSide | None = None
    scenario_label: str | None = None
    upcoming: list[Payment]
    cashflow_route: AppRoute = "/app/cashflow"


class CashflowCard(_Card):
    card_type: Literal["cashflow"] = "cashflow"
    data: CashflowData


# --- alerts ---------------------------------------------------------------------------------


class AlertItem(_M):
    id: uuid.UUID
    type: str
    severity: str
    title_en: str
    title_bn: str
    amount: DecStr | None
    currency: str | None
    due_on: date | None
    deal_ref: str | None
    route: AppRoute | None


class AlertsData(_M):
    status: str
    count: int
    alerts: list[AlertItem]


class AlertsCard(_Card):
    card_type: Literal["alerts"] = "alerts"
    data: AlertsData


# --- financing_comparison -------------------------------------------------------------------


class FinancingOptionItem(_M):
    option_id: uuid.UUID
    code: str
    name: str
    kind: str
    rank: int
    recommended: bool
    eligible: bool
    tenor_days: int
    total_cost: DecStr
    effective_annual_rate_pct: DecStr
    collateral: str
    conditions: str
    why_not: list[Bilingual]


class Recommendation(_M):
    code: str
    name: str
    total_cost: DecStr
    saving_vs_next: DecStr | None
    why_codes: list[str]
    reasons: list[Bilingual]


class FinancingComparisonData(_M):
    mode: Literal["shortfall", "order"]
    deal_ref: str
    defaulted_deal: bool = False
    currency: str
    amount: DecStr
    needed_by: date
    needed_for_days: int
    no_financing_needed: bool
    options: list[FinancingOptionItem]
    recommended: Recommendation | None
    apply_route: AppRoute


class FinancingComparisonCard(_Card):
    card_type: Literal["financing_comparison"] = "financing_comparison"
    data: FinancingComparisonData


# --- fx_compare -----------------------------------------------------------------------------


class Route(_M):
    route: Literal["USD", "CNY"]
    sent: DecStr
    sent_currency: Literal["USD", "CNY"]
    rate_used: DecStr
    conversion: DecStr
    fees: DecStr
    total: DecStr


class FxCompareData(_M):
    basis: str
    invoice_amount: DecStr
    invoice_currency: Literal["USD", "CNY"]
    payer_currency: str
    supplier_receives_cny: DecStr
    usd_route: Route
    cny_route: Route
    cheaper: Literal["USD", "CNY"]
    saving: DecStr
    saving_pct: DecStr
    as_of: date
    assumptions: list[str]


class FxCompareCard(_Card):
    card_type: Literal["fx_compare"] = "fx_compare"
    data: FxCompareData


# --- monthly_summary ------------------------------------------------------------------------


class MonthPoint(_M):
    month: str
    total_landed_cost: DecStr


class MonthlySummaryData(_M):
    month: str
    currency: str
    deals_count: int
    total_purchases: DecStr
    total_landed_cost: DecStr
    expected_revenue: DecStr
    average_margin_pct: DecStr | None
    top_cost_driver: CostLine | None
    purchases_delta: DecStr
    purchases_pct: DecStr | None
    margin_delta_pts: DecStr | None
    history: list[MonthPoint]
    insights: list[Bilingual]


class MonthlySummaryCard(_Card):
    card_type: Literal["monthly_summary"] = "monthly_summary"
    data: MonthlySummaryData


# --- scorecard ------------------------------------------------------------------------------


class SupplierItem(_M):
    code: str
    name: str
    country: str
    kyb_status: str
    score: DecStr | None
    on_time_rate_pct: DecStr | None
    dispute_rate_pct: DecStr | None
    defect_rate_pct: DecStr | None
    doc_mismatch_count: int
    your_deals_count: int
    weak: bool
    flags: list[str]


class ScorecardData(_M):
    window_months: int
    suppliers: list[SupplierItem]


class ScorecardCard(_Card):
    card_type: Literal["scorecard"] = "scorecard"
    data: ScorecardData


# --- kyb ------------------------------------------------------------------------------------


class KybReason(_M):
    code: str
    status: Literal["WARN", "FAIL"]
    detail_en: str
    detail_bn: str


class KybData(_M):
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    status: Literal["VERIFIED", "WARNING", "BLOCKED"]
    score: int
    deal_ref: str | None
    reasons: list[KybReason] = Field(description="Top 3 non-passing checks, worst first.")
    checks_passed: int
    checks_total: int
    has_pending_change: bool
    pending_status: Literal["VERIFIED", "WARNING", "BLOCKED"] | None
    supplier_route: AppRoute


class KybCard(_Card):
    card_type: Literal["kyb"] = "kyb"
    data: KybData


# --- citations (RAG) ------------------------------------------------------------------------


class CitationSnippet(_M):
    cite_id: str = Field(pattern=r"^S\d{1,3}$")
    source_id: str
    title: str
    heading_path: str
    content: str
    language: str
    source_type: str
    original_reference: str
    last_reviewed: str
    disclaimer: str
    score: float


class Withheld(_M):
    source_id: str
    codes: list[str]


class CitationsData(_M):
    # The user's query is deliberately not echoed: it is not tool data and must not be scanned
    # as untrusted text (a normal "release the tranche?" question would flag the turn).
    snippets: list[CitationSnippet]
    withheld: list[Withheld] = []
    security_flags: list[str] = Field(
        default_factory=list, description="Injection codes of withheld passages (flags the turn)."
    )


class CitationsCard(_Card):
    card_type: Literal["citations"] = "citations"
    data: CitationsData


Card = Annotated[
    CitationsCard
    | LandedCostCard
    | CashflowCard
    | AlertsCard
    | FinancingComparisonCard
    | FxCompareCard
    | MonthlySummaryCard
    | ScorecardCard
    | KybCard,
    Field(discriminator="card_type"),
]
CARD_TYPES = frozenset(
    {
        "citations",
        "landed_cost",
        "cashflow",
        "alerts",
        "financing_comparison",
        "fx_compare",
        "monthly_summary",
        "scorecard",
        "kyb",
    }
)
