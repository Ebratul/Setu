"""Approval inbox, supplier account-change tracker, e-mail check and notification API models.
The request bodies take no tier, no status and no payload: an approval executes exactly what was
stored when the engine escalated it."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.deals import TraceItemOut


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


ApprovalStatusOut = Literal[
    "PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED", "EXPIRED", "LOCKED"
]


class ApproveIn(In):
    otp: str | None = Field(default=None, pattern=r"^\d{6}$", description="Tier 3 only")


class RejectIn(In):
    reason: str | None = Field(default=None, max_length=300)


class ReasonOut(Out):
    code: str
    message: str
    message_bn: str


class SupplierEvidence(Out):
    id: uuid.UUID
    name: str
    kyb_status: str
    kyb_score: int | None
    account_label: str | None = Field(description="Bank, masked number and currency")
    account_status: str | None
    account_age_days: int | None


class DocumentEvidence(Out):
    id: uuid.UUID
    doc_type: str
    file_name: str
    status: str
    check_status: str
    issues: list[str] = Field(description="Codes of checks that did not pass")
    registry: Literal["NEW", "REGISTERED", "DUPLICATE", "UNKNOWN"]
    sha_short: str | None


class FxEvidence(Out):
    pair: str
    rate: str | None
    amount: str | None
    locked: bool
    lock_expires_at: datetime | None


class EvidenceSnapshot(Out):
    """Everything an approver needs on one card (read-only, built from the database)."""

    supplier: SupplierEvidence | None
    documents: list[DocumentEvidence]
    registry_status: Literal["CLEAR", "DUPLICATE_FOUND", "NOT_APPLICABLE"]
    fx: FxEvidence | None
    trace: list[TraceItemOut]
    risk_event_id: uuid.UUID | None
    audit_seq: int | None


class ApprovalOut(Out):
    id: uuid.UUID
    action: str
    action_label_en: str
    action_label_bn: str
    what_happens_en: str
    what_happens_bn: str
    tier: int
    status: ApprovalStatusOut
    deal_id: uuid.UUID | None
    deal_reference: str | None
    supplier_name: str | None
    milestone_seq: int | None
    amount: str | None
    currency: str | None
    reasons: list[ReasonOut]
    requested_by: str
    requested_via: str | None
    otp_required: bool
    created_at: datetime
    expires_at: datetime | None
    cooling_off_until: datetime | None
    seconds_to_cooling_off_end: int | None
    cooling_off_total_seconds: int | None
    otp_attempts_left: int | None
    otp_sent: bool
    decided_at: datetime | None
    decision_note: str | None
    can_approve: bool
    can_reject: bool
    can_cancel: bool
    blocked_reason: str | None = Field(description="Why approve is unavailable, if it is")
    why_pause_en: str | None
    why_pause_bn: str | None
    evidence: EvidenceSnapshot | None = None
    simulated: Literal[True] = True


class ApprovalList(Out):
    items: list[ApprovalOut]
    pending_count: int


class ApproveResult(Out):
    outcome: Literal["EXECUTED", "RE_ESCALATED", "APPROVED_NOT_EXECUTED"]
    idempotent_replay: bool = False
    approval: ApprovalOut
    new_approval: ApprovalOut | None = None
    message_en: str
    message_bn: str
    context_changed: bool = False
    simulated: Literal[True] = True


class RejectResult(Out):
    approval: ApprovalOut


class ResendResult(Out):
    approval: ApprovalOut
    delivered_to_demo_phone: bool


class PhoneMessage(Out):
    id: uuid.UUID
    approval_id: uuid.UUID | None
    body: str
    code: str
    created_at: datetime


class DemoPhoneOut(Out):
    simulated: Literal[True] = True
    messages: list[PhoneMessage]


class EventOut(Out):
    id: uuid.UUID
    ts: datetime
    kind: str
    tier: int
    actor: str
    title_en: str
    title_bn: str
    detail_en: str
    detail_bn: str
    approval_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    deal_reference: str | None
    audit_seq: int | None
    unread: bool


class NotificationsOut(Out):
    unread: int
    items: list[EventOut]


class TimelineStep(Out):
    key: str
    ts: datetime | None
    state: Literal["DONE", "CURRENT", "UPCOMING", "FAILED"]
    label_en: str
    label_bn: str
    detail_en: str
    detail_bn: str
    audit_seq: int | None


class TimelineOut(Out):
    approval_id: uuid.UUID | None
    deal_id: uuid.UUID
    steps: list[TimelineStep]
    events: list[EventOut]


# --- supplier account change, e-mail check ------------------------------------------------------


class AccountChangeIn(In):
    deal_id: uuid.UUID
    bank_name: str = Field(min_length=2, max_length=120)
    bank_country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    account_number: str = Field(min_length=6, max_length=34, pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]+$")
    holder_name: str = Field(min_length=2, max_length=200)
    account_type: Literal["CORPORATE", "PERSONAL"] = "CORPORATE"
    currency: Literal["USD", "CNY", "BDT"] = "USD"


class ChangeStep(Out):
    key: Literal["SUBMITTED", "KYB", "BUYER", "DONE"]
    state: Literal["DONE", "CURRENT", "UPCOMING", "FAILED"]


class AccountChangeRequestOut(Out):
    account_id: uuid.UUID
    deal_id: uuid.UUID
    deal_reference: str
    buyer_name: str
    account_label: str
    account_status: Literal["PENDING_CHANGE", "ACTIVE", "RETIRED"]
    stage: Literal["WAITING_BUYER", "APPROVED", "REJECTED", "EXPIRED", "LOCKED", "CANCELLED"]
    tier: int
    requested_at: datetime | None
    decided_at: datetime | None
    steps: list[ChangeStep]
    simulated: Literal[True] = True


class AccountChangeList(Out):
    items: list[AccountChangeRequestOut]


class EmailCheckIn(In):
    text: str = Field(min_length=1, max_length=20_000)
    deal_reference: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class SignalOut(Out):
    code: str
    label_en: str
    label_bn: str


class EmailCheckOut(Out):
    verdict: Literal["BLOCKED", "SUSPICIOUS", "NO_PAYMENT_CHANGE_FOUND"]
    blocked: bool
    account_changed: Literal[False] = False
    title_en: str
    title_bn: str
    message_en: str
    message_bn: str
    next_steps_en: list[str]
    next_steps_bn: list[str]
    signals: list[SignalOut]
    deal_reference: str | None
    alert_id: uuid.UUID | None
    audit_seq: int | None
    related_approval_id: uuid.UUID | None
    text_sha256: str
    simulated: Literal[True] = True


SimScenario = Literal["redirect-email", "supplier-account-change", "large-advance"]


class SimulateOut(Out):
    scenario: SimScenario
    title_en: str
    title_bn: str
    what_we_did_en: str
    what_we_did_bn: str
    how_setu_responded_en: str
    how_setu_responded_bn: str
    outcome: str
    tier: int | None
    reasons: list[str]
    approval_id: uuid.UUID | None
    email: EmailCheckOut | None = None
    simulated: Literal[True] = True
