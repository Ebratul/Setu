import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Amount, Base, Created, CurrencyCode, Fraction, UUIDPk, str_enum
from app.db.enums import (
    ConfirmRole,
    CostKind,
    DealStatus,
    EscrowStatus,
    EvidenceStatus,
    LedgerDirection,
    LedgerKind,
    MilestoneStatus,
    MilestoneTrigger,
)


class Deal(Base):
    """One import order between a buyer and a supplier (reference SETU-YYYY-NNNN)."""

    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("goods_value >= 0", name="goods_value_non_negative"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[UUIDPk]
    reference: Mapped[str] = mapped_column(String(32), unique=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    beneficiary_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id")
    )
    title: Mapped[str] = mapped_column(String(200))
    hs_code: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    unit: Mapped[str] = mapped_column(String(8))
    unit_price: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    goods_value: Mapped[Amount]
    incoterm: Mapped[str] = mapped_column(String(8))
    port_of_loading: Mapped[str] = mapped_column(String(80))
    port_of_discharge: Mapped[str] = mapped_column(String(80))
    expected_sale_value: Mapped[Amount | None]
    status: Mapped[DealStatus] = mapped_column(str_enum(DealStatus, "deal_status"), index=True)
    opened_on: Mapped[date] = mapped_column(Date)
    funded_on: Mapped[date | None] = mapped_column(Date)
    completed_on: Mapped[date | None] = mapped_column(Date)
    on_time: Mapped[bool | None] = mapped_column(Boolean)
    dispute_count: Mapped[int] = mapped_column(Integer, default=0)
    dispute_reason: Mapped[str | None] = mapped_column(Text)
    kyb_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("kyb_runs.id", use_alter=True, name="fk_deals_kyb_run_id_kyb_runs")
    )
    created_at: Mapped[Created]


class DealCost(Base):
    """Landed-cost line on top of goods value (paid by the buyer)."""

    __tablename__ = "deal_costs"
    __table_args__ = (
        UniqueConstraint("deal_id", "kind"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
    )

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"))
    kind: Mapped[CostKind] = mapped_column(str_enum(CostKind, "cost_kind"))
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    due_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(200))


class Milestone(Base):
    """Escrow tranche. `percent` is a fraction; tranches of a deal sum to exactly 1."""

    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("deal_id", "seq"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("percent > 0 AND percent <= 1", name="percent_range"),
    )

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(SmallInteger)
    trigger: Mapped[MilestoneTrigger] = mapped_column(
        str_enum(MilestoneTrigger, "milestone_trigger")
    )
    percent: Mapped[Fraction]
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[MilestoneStatus] = mapped_column(str_enum(MilestoneStatus, "milestone_status"))
    required_evidence: Mapped[list[str]] = mapped_column(JSONB, default=list)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    condition_text: Mapped[str | None] = mapped_column(Text)
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        str_enum(EvidenceStatus, "evidence_status"),
        default=EvidenceStatus.PENDING,
        server_default=EvidenceStatus.PENDING.value,
    )
    release_idempotency_key: Mapped[str | None] = mapped_column(String(80))


class MilestoneConfirmation(Base):
    """One row per party that confirmed the current milestone schedule (reset on re-propose)."""

    __tablename__ = "milestone_confirmations"
    __table_args__ = (UniqueConstraint("deal_id", "party_role"),)

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deals.id", ondelete="CASCADE"))
    party_role: Mapped[ConfirmRole] = mapped_column(str_enum(ConfirmRole, "confirm_role"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EscrowAccount(Base):
    """Simulated escrow wallet per deal. The buyer funds tranche by tranche before each due date."""

    __tablename__ = "escrow_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint(
            "funded_total = released_total + refunded_total + balance", name="escrow_invariant"
        ),
    )

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), unique=True
    )
    currency: Mapped[CurrencyCode]
    funded_total: Mapped[Amount]
    released_total: Mapped[Amount]
    balance: Mapped[Amount]
    status: Mapped[EscrowStatus] = mapped_column(str_enum(EscrowStatus, "escrow_status"))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    refunded_total: Mapped[Amount] = mapped_column(
        Numeric(20, 4), default=Decimal("0"), server_default="0"
    )
    partner: Mapped[str] = mapped_column(
        String(80), default="Simulated Escrow Partner", server_default="Simulated Escrow Partner"
    )
    advance_over_20k: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class LedgerEntry(Base):
    """Simulated double-entry posting; each txn_ref balances (debits == credits)."""

    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[UUIDPk]
    txn_ref: Mapped[str] = mapped_column(String(64), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    account: Mapped[str] = mapped_column(String(80))
    direction: Mapped[LedgerDirection] = mapped_column(str_enum(LedgerDirection, "ledger_dir"))
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    memo: Mapped[str] = mapped_column(String(200))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    kind: Mapped[LedgerKind] = mapped_column(str_enum(LedgerKind, "ledger_kind"))
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="SET NULL")
    )
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    counter_amount: Mapped[Amount | None]
    counter_currency: Mapped[str | None] = mapped_column(CHAR(3))


class SupplierScore(Base):
    """Monthly supplier scorecard snapshot (rates are fractions; score is 0-100)."""

    __tablename__ = "supplier_scores"
    __table_args__ = (UniqueConstraint("supplier_id", "month"),)

    id: Mapped[UUIDPk]
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    month: Mapped[date] = mapped_column(Date)
    deals_count: Mapped[int] = mapped_column(Integer)
    on_time_rate: Mapped[Fraction]
    defect_rate: Mapped[Fraction]
    doc_mismatch_count: Mapped[int] = mapped_column(Integer)
    dispute_count: Mapped[int] = mapped_column(Integer)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2))


class CreditRecord(Base):
    """Ed25519-signed completed-deal record (FR-8).
    `payload_hash` = sha256(canonical_json(payload))."""

    __tablename__ = "credit_records"

    id: Mapped[UUIDPk]
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), unique=True
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    amount: Mapped[Amount]
    currency: Mapped[CurrencyCode]
    on_time: Mapped[bool] = mapped_column(Boolean)
    dispute_count: Mapped[int] = mapped_column(Integer)
    completed_on: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(CHAR(64))
    signature: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(32))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
