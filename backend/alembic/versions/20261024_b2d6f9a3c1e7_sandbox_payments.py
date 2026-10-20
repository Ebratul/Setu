"""sandbox_payments: PayPal Sandbox checkouts and verified webhook deliveries (simulated)

Revision ID: b2d6f9a3c1e7
Revises: a9c4e7b2d5f8
Create Date: 2026-10-24 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b2d6f9a3c1e7"
down_revision: str | Sequence[str] | None = "a9c4e7b2d5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sandbox_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("simulated", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "coverage",
            sa.Enum(
                "NEXT_TRANCHE",
                "REMAINING",
                name="sandbox_payment_coverage",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("charge_amount", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("charge_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "CREATED",
                "CAPTURED",
                "FAILED",
                "CANCELLED",
                name="sandbox_payment_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("provider_order_id", sa.String(length=64), nullable=False),
        sa.Column("provider_capture_id", sa.String(length=64), nullable=True),
        sa.Column("provider_status", sa.String(length=32), nullable=True),
        sa.Column("failure_code", sa.String(length=48), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escrow_funded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("funding_approval_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("simulated", name=op.f("ck_sandbox_payments_always_simulated")),
        sa.CheckConstraint(
            "amount > 0 AND charge_amount > 0", name=op.f("ck_sandbox_payments_amounts_positive")
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], name=op.f("fk_sandbox_payments_deal_id_deals"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["buyer_id"], ["parties.id"], name=op.f("fk_sandbox_payments_buyer_id_parties")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name=op.f("fk_sandbox_payments_created_by_user_id_users")),
        sa.ForeignKeyConstraint(
            ["funding_approval_id"],
            ["approval_requests.id"],
            name=op.f("fk_sandbox_payments_funding_approval_id_approval_requests"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sandbox_payments")),
        sa.UniqueConstraint("created_by_user_id", "idempotency_key", name=op.f("uq_sandbox_payments_created_by_user_id_idempotency_key")),
        sa.UniqueConstraint("provider_order_id", name=op.f("uq_sandbox_payments_provider_order_id")),
        sa.UniqueConstraint("provider_capture_id", name=op.f("uq_sandbox_payments_provider_capture_id")),
    )
    op.create_index(op.f("ix_sandbox_payments_deal_id"), "sandbox_payments", ["deal_id"])
    op.create_index(op.f("ix_sandbox_payments_status"), "sandbox_payments", ["status"])
    op.create_table(
        "sandbox_payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["sandbox_payments.id"],
            name=op.f("fk_sandbox_payment_events_payment_id_sandbox_payments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sandbox_payment_events")),
        sa.UniqueConstraint("provider_event_id", name=op.f("uq_sandbox_payment_events_provider_event_id")),
    )
    op.create_index(op.f("ix_sandbox_payment_events_payment_id"), "sandbox_payment_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_sandbox_payment_events_payment_id"), table_name="sandbox_payment_events")
    op.drop_table("sandbox_payment_events")
    op.drop_index(op.f("ix_sandbox_payments_status"), table_name="sandbox_payments")
    op.drop_index(op.f("ix_sandbox_payments_deal_id"), table_name="sandbox_payments")
    op.drop_table("sandbox_payments")
