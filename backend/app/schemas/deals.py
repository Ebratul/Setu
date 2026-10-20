"""FR-5 deals, milestones and simulated escrow API models. Money is a decimal string; the UI formats
but never computes. Everything here is simulated."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.analysis import CurrencyCode, DecStr, InDec

DealStatusOut = Literal[
    "DRAFT",
    "PROPOSED",
    "CONFIRMED",
    "FUNDED",
    "IN_PRODUCTION",
    "SHIPPED",
    "ARRIVED",
    "COMPLETED",
    "DISPUTED",
    "CANCELLED",
]
MilestoneStatusOut = Literal[
    "PROPOSED",
    "PENDING",
    "READY",
    "PENDING_APPROVAL",
    "RELEASED",
    "FROZEN",
    "REFUNDED",
    "CANCELLED",
]
EvidenceStatusOut = Literal["PENDING", "VERIFIED", "FLAGGED", "REJECTED"]
EvidenceItemStatus = Literal["MISSING", "PENDING", "VERIFIED", "FLAGGED", "REJECTED"]
TriggerOut = Literal["PRODUCTION_START", "SHIPMENT", "ARRIVAL"]
PartyRoleOut = Literal["BUYER", "SUPPLIER"]
ViewerRole = Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"]
CostKindOut = Literal["FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER"]
IdempotencyKey = Annotated[
    str, Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$", examples=["rel-m1-0001"])
]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionIn(BaseModel):
    """Body of a money action. Unknown fields are DROPPED, not rejected: a client-supplied `tier`
    or `approved` is ignored because the tier is decided in code from the database (SR-1), never
    read from a request."""

    model_config = ConfigDict(extra="ignore")


# --- requests ---------------------------------------------------------------------------------


class CostIn(In):
    kind: CostKindOut
    amount: InDec
    currency: CurrencyCode = "USD"
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=200)


class CreateDealRequest(In):
    buyer_id: uuid.UUID | None = Field(
        default=None, description="Admin only; a buyer always creates deals for its own business."
    )
    supplier_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200, description="The goods")
    hs_code: str = Field(default="0000.00", pattern=r"^[0-9.]{4,12}$")
    quantity: InDec
    unit: str = Field(min_length=1, max_length=8)
    unit_price: InDec
    currency: Literal["USD", "CNY"] = "USD"
    incoterm: str = Field(default="FOB", pattern=r"^[A-Z]{3}$")
    port_of_loading: str = Field(min_length=1, max_length=80)
    port_of_discharge: str = Field(min_length=1, max_length=80)
    expected_sale_value: InDec | None = None
    costs: list[CostIn] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _unique_costs(self) -> "CreateDealRequest":
        kinds = [c.kind for c in self.costs]
        if len(set(kinds)) != len(kinds):
            raise ValueError("each cost kind may appear once")
        return self


class ProposeRequest(ActionIn):
    template: Literal["30/60/10", "custom"] = "30/60/10"
    percents: list[Annotated[str, Field(pattern=r"^\d{1,3}(\.\d{1,2})?$")]] | None = Field(
        default=None, max_length=5, description='Percentages, e.g. ["40", "40", "20"]; custom only.'
    )

    @model_validator(mode="after")
    def _percents_match_template(self) -> "ProposeRequest":
        if self.template == "custom" and not self.percents:
            raise ValueError("custom schedules need percents")
        if self.template != "custom" and self.percents is not None:
            raise ValueError("percents are only for the custom template")
        return self


class ConfirmRequest(ActionIn):
    party_role: PartyRoleOut | None = Field(
        default=None, description="Derived from the signed-in user; admins must say which side."
    )


class FundRequest(ActionIn):
    amount: InDec | None = Field(
        default=None,
        description="Deposit in the deal currency. Omit for the next uncovered tranche.",
    )


class ReleaseRequest(ActionIn):
    idempotency_key: IdempotencyKey


class RefundRequest(In):
    reason: str = Field(min_length=3, max_length=300)


class EvidenceRequest(In):
    status: EvidenceStatusOut


# --- responses --------------------------------------------------------------------------------


class ActionFlag(Out):
    allowed: bool
    reason: str | None = Field(default=None, description="Why not, when allowed is false")


class DealActions(Out):
    can_propose: ActionFlag
    can_confirm: ActionFlag
    can_fund: ActionFlag
    can_release: ActionFlag
    can_refund: ActionFlag


class MilestoneActions(Out):
    can_release: ActionFlag
    can_refund: ActionFlag


class EvidenceItem(Out):
    doc_type: str
    status: EvidenceItemStatus
    documents: int = Field(description="Uploaded documents of this type for the milestone")


class SettlementOut(Out):
    currency: CurrencyCode
    fx_rate: DecStr | None
    counter_amount: DecStr | None


class ApprovalRef(Out):
    id: uuid.UUID
    key: str
    tier: int
    status: str
    reasons: list[str]
    otp_required: bool
    cooling_off_until: datetime | None


class MilestoneOut(Out):
    id: uuid.UUID
    seq: int
    trigger: TriggerOut
    percent: DecStr = Field(description="Fraction, 0.300000 = 30 %")
    percent_label: str
    amount: DecStr
    currency: CurrencyCode
    condition_text: str
    required_evidence: list[EvidenceItem]
    evidence_status: EvidenceStatusOut
    status: MilestoneStatusOut
    due_on: date
    released_at: datetime | None
    funded: bool = Field(description="Covered by the money deposited in escrow so far")
    settlement: SettlementOut | None
    approval: ApprovalRef | None
    can: MilestoneActions


class EscrowCard(Out):
    simulated: Literal[True] = True
    deal_id: uuid.UUID
    exists: bool
    currency: CurrencyCode
    partner: str
    status: str
    funded: DecStr
    released: DecStr
    refunded: DecStr
    balance: DecStr
    remaining_to_fund: DecStr
    advance_over_20k: bool
    invariant_ok: bool


class ConfirmationOut(Out):
    party_role: PartyRoleOut
    confirmed: bool
    confirmed_at: datetime | None
    confirmed_by: str | None


class KybSummary(Out):
    status: str
    score: int | None
    run_id: uuid.UUID | None
    checked_at: datetime | None
    reason_codes: list[str]
    supplier_route: str


class NextMilestone(Out):
    id: uuid.UUID
    seq: int
    amount: DecStr
    currency: CurrencyCode
    status: MilestoneStatusOut
    due_on: date
    trigger: TriggerOut


class CostOut(Out):
    kind: CostKindOut
    amount: DecStr
    currency: CurrencyCode
    due_on: date | None
    note: str | None


class DealListItem(Out):
    simulated: Literal[True] = True
    id: uuid.UUID
    reference: str
    title: str
    status: DealStatusOut
    buyer_id: uuid.UUID
    buyer_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    goods_value: DecStr
    currency: CurrencyCode
    opened_on: date
    funded: DecStr
    released: DecStr
    balance: DecStr
    milestones_total: int
    milestones_released: int
    next_milestone: NextMilestone | None
    supplier_kyb_status: str


class DealList(Out):
    simulated: Literal[True] = True
    viewer_role: ViewerRole
    deals: list[DealListItem]


class DealDetail(Out):
    simulated: Literal[True] = True
    viewer_role: ViewerRole
    id: uuid.UUID
    reference: str
    title: str
    status: DealStatusOut
    buyer_id: uuid.UUID
    buyer_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    beneficiary_account_id: uuid.UUID | None
    beneficiary_masked: str | None
    settlement_currency: CurrencyCode | None
    hs_code: str
    quantity: DecStr
    unit: str
    unit_price: DecStr
    currency: CurrencyCode
    goods_value: DecStr
    incoterm: str
    port_of_loading: str
    port_of_discharge: str
    expected_sale_value: DecStr | None
    opened_on: date
    funded_on: date | None
    completed_on: date | None
    dispute_count: int
    dispute_reason: str | None
    costs: list[CostOut]
    kyb: KybSummary
    milestones: list[MilestoneOut]
    confirmations: list[ConfirmationOut]
    escrow: EscrowCard
    next_milestone: NextMilestone | None
    can: DealActions


class LedgerRow(Out):
    id: uuid.UUID
    txn_ref: str
    kind: Literal["FUND", "RELEASE", "REFUND"]
    account: str
    direction: Literal["DEBIT", "CREDIT"]
    amount: DecStr
    currency: CurrencyCode
    memo: str
    posted_at: datetime
    milestone_id: uuid.UUID | None
    milestone_seq: int | None
    fx_rate: DecStr | None
    counter_amount: DecStr | None
    counter_currency: CurrencyCode | None
    simulated: bool


class LedgerOut(Out):
    simulated: Literal[True] = True
    deal_id: uuid.UUID
    reference: str
    rows: list[LedgerRow]
    balanced: bool
    escrow: EscrowCard


class ActivityRow(Out):
    seq: int
    ts: datetime
    actor: Literal["user", "llm", "system"]
    action: str
    tier: int
    result: str
    text_en: str
    text_bn: str
    payload_hash: str
    entry_hash: str
    key_id: str


class ActivityOut(Out):
    simulated: Literal[True] = True
    deal_id: uuid.UUID
    rows: list[ActivityRow]


class TraceItemOut(Out):
    code: str
    kind: Literal["BLOCK", "TIER3", "TIER2"]
    fired: bool
    deciding: bool
    label_en: str
    label_bn: str
    value_en: str
    value_bn: str


class HintOut(Out):
    code: str
    to_tier: int | None
    text_en: str
    text_bn: str


class RiskOut(Out):
    """The engine's answer plus its rule trace. Decided by code, never by a model."""

    decision: Literal["ALLOW", "REQUIRE_APPROVAL", "BLOCK"]
    tier: int
    reasons: list[str]
    explanation_en: str = ""
    explanation_bn: str = ""
    context_hash: str = ""
    decided_by: list[str] = Field(default_factory=list)
    trace: list[TraceItemOut] = Field(default_factory=list)
    hints: list[HintOut] = Field(default_factory=list)


class ReleaseResult(Out):
    simulated: Literal[True] = True
    outcome: Literal["RELEASED", "PENDING_APPROVAL"]
    idempotent_replay: bool
    milestone: MilestoneOut
    ledger: list[LedgerRow]
    approval: ApprovalRef | None
    risk: RiskOut | None = Field(description="Absent on an idempotent replay")
    notice: str | None = Field(description="Tier 1 releases carry a notice for the buyer")
    deal: DealDetail


class RefundResult(Out):
    simulated: Literal[True] = True
    refunded_amount: DecStr
    currency: CurrencyCode
    ledger: list[LedgerRow]
    deal: DealDetail


class EvidenceResult(Out):
    simulated: Literal[True] = True
    milestone: MilestoneOut


class FxLockRequest(ActionIn):
    amount: InDec | None = Field(
        default=None, description="Amount in the deal currency. Omit for what is not yet released."
    )


class FxLockResult(Out):
    simulated: Literal[True] = True
    outcome: Literal["LOCKED", "PENDING_APPROVAL"]
    base: CurrencyCode | None
    quote: CurrencyCode | None
    rate: DecStr | None
    amount: DecStr | None
    expires_at: datetime | None
    approval: ApprovalRef | None
    risk: RiskOut


class ChangeBeneficiaryRequest(ActionIn):
    bank_account_id: uuid.UUID


class ChangeBeneficiaryResult(Out):
    simulated: Literal[True] = True
    outcome: Literal["CHANGED", "PENDING_APPROVAL"]
    approval: ApprovalRef | None
    risk: RiskOut
    deal: DealDetail
