import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Amount, Base, Created, CurrencyCode, Fraction, Rate, UUIDPk, str_enum
from app.db.enums import (
    AlertStatus,
    AlertType,
    CashflowKind,
    FinancingKind,
    FlowDirection,
    FxKind,
    FxLockStatus,
    Severity,
)


class CashflowItem(Base):
    """Dated cash movement for a buyer. `key` is a stable seed key (relative to DEMO_TODAY)."""

    __tablename__ = "cashflow_items"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[UUIDPk]
    key: Mapped[str] = mapped_column(String(80), unique=True)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[CashflowKind] = mapped_column(str_enum(CashflowKind, "cashflow_kind"))
    direction: Mapped[FlowDirection] = mapped_column(str_enum(FlowDirection, "flow_direction"))
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    description: Mapped[str] = mapped_column(String(200))
    is_projected: Mapped[bool] = mapped_column(Boolean)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE")
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="CASCADE")
    )
    deal_cost_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deal_costs.id", ondelete="CASCADE")
    )


class FxRate(Base):
    """Mock daily FX rate: 1 `base` = `rate` `quote`. FORECAST rows are mock projections."""

    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base", "quote", "as_of", "kind"),
        CheckConstraint("rate > 0", name="rate_positive"),
    )

    id: Mapped[UUIDPk]
    base: Mapped[CurrencyCode]
    quote: Mapped[CurrencyCode]
    rate: Mapped[Rate]
    as_of: Mapped[date] = mapped_column(Date)
    kind: Mapped[FxKind] = mapped_column(str_enum(FxKind, "fx_kind"))
    source: Mapped[str] = mapped_column(String(32))


class FxLock(Base):
    """Mock rate lock (FR-7, Tier 2)."""

    __tablename__ = "fx_locks"

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE")
    )
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    base: Mapped[CurrencyCode]
    quote: Mapped[CurrencyCode]
    rate: Mapped[Rate]
    amount: Mapped[Amount]
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[FxLockStatus] = mapped_column(str_enum(FxLockStatus, "fx_lock_status"))


class FinancingOption(Base):
    """Mock financing catalogue entry. `eligibility` is a rule tree the matcher evaluates:
    {"all": [{"fact": "<name>", "op": "gte|lte|eq|in", "value": ...}, ...]}."""

    __tablename__ = "financing_options"

    id: Mapped[UUIDPk]
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[FinancingKind] = mapped_column(str_enum(FinancingKind, "financing_kind"))
    provider_party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("parties.id"))
    currency: Mapped[CurrencyCode]
    annual_rate: Mapped[Fraction | None]
    flat_cost_rate: Mapped[Fraction | None]
    price_uplift_rate: Mapped[Fraction | None]
    fee_rate: Mapped[Fraction | None]
    fee_fixed: Mapped[Amount | None]
    tenor_days_min: Mapped[int | None] = mapped_column(Integer)
    tenor_days_max: Mapped[int | None] = mapped_column(Integer)
    tenor_rule: Mapped[str | None] = mapped_column(String(32))
    min_amount: Mapped[Amount | None]
    max_amount: Mapped[Amount | None]
    collateral: Mapped[str] = mapped_column(String(200))
    conditions: Mapped[str] = mapped_column(Text)
    eligibility: Mapped[dict[str, Any]] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[UUIDPk]
    key: Mapped[str] = mapped_column(String(80), unique=True)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE")
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="CASCADE")
    )
    type: Mapped[AlertType] = mapped_column(str_enum(AlertType, "alert_type"))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "alert_severity"))
    status: Mapped[AlertStatus] = mapped_column(str_enum(AlertStatus, "alert_status"))
    title_en: Mapped[str] = mapped_column(String(200))
    title_bn: Mapped[str] = mapped_column(String(200))
    message_en: Mapped[str] = mapped_column(Text)
    message_bn: Mapped[str] = mapped_column(Text)
    amount: Mapped[Amount | None]
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    due_on: Mapped[date | None] = mapped_column(Date)
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[Created]
