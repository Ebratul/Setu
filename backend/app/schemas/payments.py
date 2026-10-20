"""PayPal Sandbox checkout API models. Requests carry ids and a coverage choice only: the amount,
currency, owner and status of a payment are always read from the server's own records. Everything
here is simulated."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.analysis import CurrencyCode, DecStr

CoverageOut = Literal["NEXT_TRANCHE", "REMAINING"]
PaymentStatusOut = Literal["CREATED", "CAPTURED", "FAILED", "CANCELLED"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateOrderRequest(In):
    deal_id: str
    coverage: CoverageOut = "NEXT_TRANCHE"


class PaypalConfigOut(Out):
    simulated: Literal[True] = True
    enabled: bool
    client_id: str | None
    charge_currency: CurrencyCode


class PaymentOut(Out):
    simulated: Literal[True] = True
    provider: Literal["PAYPAL_SANDBOX"] = "PAYPAL_SANDBOX"
    id: uuid.UUID
    deal_id: uuid.UUID
    deal_reference: str
    coverage: CoverageOut
    status: PaymentStatusOut
    amount: DecStr
    currency: CurrencyCode
    charge_amount: DecStr
    charge_currency: CurrencyCode
    fx_rate: str | None
    provider_order_id: str
    provider_capture_id: str | None
    provider_status: str | None
    failure_code: str | None
    created_at: datetime
    captured_at: datetime | None
    escrow_funded_at: datetime | None
    funding_approval_id: uuid.UUID | None
    can_capture: bool
    can_cancel: bool
    can_fund_escrow: bool


class PaymentListOut(Out):
    simulated: Literal[True] = True
    payments: list[PaymentOut]


class FundEscrowResult(Out):
    simulated: Literal[True] = True
    outcome: Literal["FUNDED", "PENDING_APPROVAL"]
    idempotent_replay: bool
    approval_id: uuid.UUID | None
    approval_tier: int | None
    notice: str
    payment: PaymentOut


class WebhookAck(Out):
    received: Literal[True] = True
    outcome: str
