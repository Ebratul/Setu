"""FR-4 supplier KYB API models. All text is deterministic (no LLM), in English and Bangla."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import DecStr, ScorePoint

CheckStatusOut = Literal["PASS", "WARN", "FAIL"]
KybOverall = Literal["VERIFIED", "WARNING", "BLOCKED"]
InvoiceNameSource = Literal["proforma", "legal_name", "override"]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KybCheckOut(Out):
    code: str
    status: CheckStatusOut
    weight: int
    detail_en: str
    detail_bn: str
    evidence: dict[str, Any]


class AccountSummary(Out):
    account_id: uuid.UUID
    bank_name: str
    masked_number: str
    holder_name: str
    account_type: Literal["CORPORATE", "PERSONAL"]
    status: Literal["ACTIVE", "PENDING_CHANGE", "RETIRED"]
    currency: str
    bank_country: str
    first_seen_on: date
    age_days: int
    verified: bool


class KybAssessmentOut(Out):
    status: KybOverall
    score: int = Field(ge=0, le=100)
    checks: list[KybCheckOut]
    reason_codes: list[str]
    explanation_en: str
    explanation_bn: str


class PendingAccountResult(KybAssessmentOut):
    account: AccountSummary


class KybThresholds(Out):
    match: float
    partial: float
    account_age_warn_days: int
    account_age_fail_days: int


class KybResult(KybAssessmentOut):
    """Supplier-level result: the active receiving account plus name, sanctions and history
    checks. A pending beneficiary change is evaluated on its own and never downgrades this."""

    simulated: Literal[True] = True
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    deal_ref: str | None
    invoice_name: str
    invoice_name_source: InvoiceNameSource
    account: AccountSummary | None
    pending_accounts: list[PendingAccountResult]
    has_pending_change: bool
    checked_at: datetime
    thresholds: KybThresholds
    persisted: bool
    route: str
    # Party and account facts only (no invoice name): what Party.kyb_status is based on.
    party_status: KybOverall
    party_score: int = Field(ge=0, le=100)
    invoice_flags: list[str] = Field(
        default_factory=list, description="Instruction-like text codes found in the seller name."
    )


class KybHistoryItem(Out):
    id: uuid.UUID
    checked_at: datetime
    status: KybOverall
    score: int
    reason_codes: list[str]
    deal_ref: str | None


class KybStatusOut(Out):
    """Latest stored result (or a live read-only evaluation if never verified) and history."""

    supplier_id: uuid.UUID
    source: Literal["stored", "live"]
    latest: KybResult
    history: list[KybHistoryItem]


class SupplierListItem(Out):
    supplier_id: uuid.UUID
    code: str
    name: str
    city: str
    country: str
    kyb_status: str
    kyb_badge: Literal["VERIFIED", "WARNING", "BLOCKED", "PENDING"]
    kyb_score: int | None
    has_pending_change: bool
    last_checked: datetime | None
    completed_deals: int
    your_deals_count: int
    on_time_rate_pct: DecStr | None
    scorecard_score: DecStr | None
    weak: bool


class SupplierList(Out):
    simulated: Literal[True] = True
    buyer_id: uuid.UUID | None
    suppliers: list[SupplierListItem]


class SupplierDealItem(Out):
    deal_id: uuid.UUID
    reference: str
    title: str
    status: str
    currency: str
    goods_value: DecStr
    opened_on: date
    on_time: bool | None
    dispute_count: int


class SupplierCompany(Out):
    legal_name: str
    license_name: str | None
    license_no: str | None
    city: str
    country: str
    first_seen_on: date


class SupplierProfile(Out):
    simulated: Literal[True] = True
    supplier_id: uuid.UUID
    code: str
    company: SupplierCompany
    kyb_status: str
    kyb: KybResult
    kyb_source: Literal["stored", "live"]
    last_checked: datetime | None
    accounts: list[AccountSummary]
    deals: list[SupplierDealItem]
    score: DecStr | None
    score_trend: list[ScorePoint]
    on_time_rate_pct: DecStr | None
    dispute_rate_pct: DecStr | None
    completed_deals: int
    history: list[KybHistoryItem]
