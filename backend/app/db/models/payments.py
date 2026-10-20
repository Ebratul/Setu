import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Amount, Base, Created, CurrencyCode, Rate, UUIDPk, str_enum
from app.db.enums import SandboxPaymentCoverage, SandboxPaymentStatus


class SandboxPayment(Base):
    """A PayPal Sandbox checkout for one deal. Separate from escrow and the ledger: a CAPTURED row
    moves nothing there. `amount`/`currency` are what the escrow would be funded with (deal
    currency, derived by the server); `charge_*` is what PayPal was asked to take."""

    __tablename__ = "sandbox_payments"
    __table_args__ = (
        CheckConstraint("simulated", name="always_simulated"),
        CheckConstraint("amount > 0 AND charge_amount > 0", name="amounts_positive"),
        UniqueConstraint("created_by_user_id", "idempotency_key"),
    )

    id: Mapped[UUIDPk]
    provider: Mapped[str] = mapped_column(String(24), default="PAYPAL_SANDBOX")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    coverage: Mapped[SandboxPaymentCoverage] = mapped_column(
        str_enum(SandboxPaymentCoverage, "sandbox_payment_coverage")
    )
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    charge_amount: Mapped[Amount]
    charge_currency: Mapped[CurrencyCode]
    fx_rate: Mapped[Rate | None]
    status: Mapped[SandboxPaymentStatus] = mapped_column(
        str_enum(SandboxPaymentStatus, "sandbox_payment_status"), index=True
    )
    provider_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    provider_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    provider_status: Mapped[str | None] = mapped_column(String(32))
    failure_code: Mapped[str | None] = mapped_column(String(48))
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(64))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escrow_funded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    funding_approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id", ondelete="SET NULL")
    )
    created_at: Mapped[Created]


class SandboxPaymentEvent(Base):
    """One verified provider webhook delivery. The unique `provider_event_id` is what makes a
    redelivery a no-op."""

    __tablename__ = "sandbox_payment_events"

    id: Mapped[UUIDPk]
    provider_event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sandbox_payments.id", ondelete="SET NULL"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(32))
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    received_at: Mapped[Created]
