"""FR-1 financing API models. Money is a decimal string; `Amounts` carries USD/BDT/CNY."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import Amounts, CurrencyCode, DecStr, Explanation, FxRateOut, InDec, Out
from app.schemas.cashflow import RecomputeOut, ShortfallOut
from app.schemas.registry import RegistryBlockOut

ModeOut = Literal["shortfall", "order"]
AppStatusOut = Literal["SUBMITTED", "APPROVED", "REJECTED", "CANCELLED"]
Ref = Annotated[str, Field(min_length=1, max_length=64)]


class DealRef(Out):
    reference: str
    title: str
    supplier_name: str


class GapOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    deal: DealRef | None
    mode: ModeOut
    currency: CurrencyCode
    no_financing_needed: bool
    amount: Amounts
    needed_by: date
    needed_for_days: int
    recover_on: date | None
    peak_amount: Amounts
    landed_cost: Amounts | None
    available_cash: Amounts | None
    explanations: list[Explanation]
    facts: list[str]


class CheckOut(Out):
    code: str
    ok: bool
    en: str
    bn: str
    params: dict[str, str]


class CostOut(Out):
    interest: Amounts
    fees: Amounts
    uplift: Amounts
    flat: Amounts
    total: Amounts
    per_30_days: Amounts
    effective_annual_rate_pct: DecStr


class OptionQuote(Out):
    option_id: uuid.UUID
    code: str
    name: str
    kind: str
    provider_name: str | None
    rank: int
    recommended: bool
    eligible: bool
    tenor_days: int
    start_on: date
    maturity_on: date
    principal: Amounts
    cost: CostOut
    collateral: str
    conditions: str
    condition_count: int
    checks: list[CheckOut]
    why_not: list[CheckOut]
    risk_notes: list[Explanation]
    facts: list[str]
    registry_block: RegistryBlockOut | None = None


class TopPick(Out):
    option_id: uuid.UUID
    code: str
    total_cost: Amounts
    saving_vs_next: Amounts | None
    key_conditions: list[str]
    why_codes: list[str]
    sentences: list[Explanation]


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_id: uuid.UUID | None = None
    deal_id: Ref | None = None
    mode: ModeOut = "shortfall"
    amount: InDec | None = None
    days: Annotated[int, Field(ge=1, le=365)] | None = None


class MatchOut(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    deal: DealRef
    mode: ModeOut
    currency: CurrencyCode
    no_financing_needed: bool
    amount: Amounts
    needed_by: date
    needed_for_days: int
    options: list[OptionQuote]
    top_pick: TopPick | None
    fx: list[FxRateOut]


class InstalmentOut(Out):
    due_on: date
    principal: Amounts
    cost: Amounts
    total: Amounts


class ScheduleOut(Out):
    simulated: Literal[True] = True
    option_id: uuid.UUID
    code: str
    amount: Amounts
    start_on: date
    tenor_days: int
    maturity_on: date
    cost: CostOut
    instalments: list[InstalmentOut]


class ImpactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_id: uuid.UUID | None = None
    deal_id: Ref | None = None
    option_id: Ref
    amount: InDec
    mode: ModeOut = "shortfall"


class ImpactSide(Out):
    first_shortfall: ShortfallOut | None
    lowest_balance: DecStr
    lowest_on: date


class ImpactPoint(Out):
    on: date
    before: DecStr
    after: DecStr


class DatedAmount(Out):
    on: date
    amount: DecStr


class ImpactOut(Out):
    simulated: Literal[True] = True
    currency: CurrencyCode
    option_code: str
    before: ImpactSide
    after: ImpactSide
    original_shortfall: ShortfallOut | None
    original_covered: bool
    new_shortfalls: list[ShortfallOut]
    inflow: DatedAmount
    repayment: DatedAmount
    repayment_in_window: bool
    series: list[ImpactPoint]
    explanations: list[Explanation]


class ApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_id: uuid.UUID | None = None
    deal_id: Ref
    option_id: Ref
    amount: InDec
    mode: ModeOut = "shortfall"


class ApplicationOut(Out):
    id: uuid.UUID
    reference: str
    deal_ref: str
    option_code: str
    option_name: str
    mode: ModeOut
    currency: CurrencyCode
    amount: Amounts
    tenor_days: int
    start_on: date
    maturity_on: date
    total_cost: Amounts
    schedule: list[InstalmentOut]
    status: AppStatusOut
    simulated: Literal[True] = True
    submitted_at: datetime
    decided_at: datetime | None


class ApplicationList(Out):
    simulated: Literal[True] = True
    party_id: uuid.UUID
    applications: list[ApplicationOut]


class ApprovalOut(Out):
    simulated: Literal[True] = True
    application: ApplicationOut
    alerts: RecomputeOut
