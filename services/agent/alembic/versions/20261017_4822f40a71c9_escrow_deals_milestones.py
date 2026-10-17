"""escrow deals milestones: states, confirmations, evidence status, ledger kind, FX counter amount

Revision ID: 4822f40a71c9
Revises: 26ef10614ad3
Create Date: 2026-10-17 11:37:37.950673

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4822f40a71c9"
down_revision: Union[str, Sequence[str], None] = "26ef10614ad3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _in(column: str, values: list[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


DEAL_OLD = ["DRAFT", "FUNDED", "IN_PRODUCTION", "SHIPPED", "COMPLETED", "DISPUTED", "CANCELLED"]
DEAL_NEW = [
    "DRAFT", "PROPOSED", "CONFIRMED", "FUNDED", "IN_PRODUCTION", "SHIPPED", "ARRIVED",
    "COMPLETED", "DISPUTED", "CANCELLED",
]  # fmt: skip
MS_OLD = ["PENDING", "READY", "RELEASED", "FROZEN", "REFUNDED", "CANCELLED"]
MS_NEW = [
    "PROPOSED", "PENDING", "READY", "PENDING_APPROVAL", "RELEASED", "FROZEN", "REFUNDED",
    "CANCELLED",
]  # fmt: skip


def upgrade() -> None:
    # Enum columns are VARCHAR + CHECK: replace the CHECK on the two status columns.
    for table, name, col, values in (
        ("deals", "ck_deals_deal_status", "status", DEAL_NEW),
        ("milestones", "ck_milestones_milestone_status", "status", MS_NEW),
    ):
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, _in(col, values))

    op.create_table(
        "milestone_confirmations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("party_role", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "party_role IN ('BUYER', 'SUPPLIER')",
            name=op.f("ck_milestone_confirmations_confirm_role"),
        ),
        sa.ForeignKeyConstraint(
            ["deal_id"],
            ["deals.id"],
            name=op.f("fk_milestone_confirmations_deal_id_deals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_milestone_confirmations_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone_confirmations")),
        sa.UniqueConstraint(
            "deal_id", "party_role", name=op.f("uq_milestone_confirmations_deal_id_party_role")
        ),
    )

    # Refusal results carry a stable code ("REFUSED:MILESTONE_ALREADY_RELEASED").
    op.alter_column(
        "audit_log",
        "result",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.add_column("audit_log", sa.Column("deal_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_audit_log_deal_id"), "audit_log", ["deal_id"], unique=False)

    op.add_column("deals", sa.Column("kyb_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_deals_kyb_run_id_kyb_runs"),
        "deals",
        "kyb_runs",
        ["kyb_run_id"],
        ["id"],
        use_alter=True,
    )

    op.add_column(
        "escrow_accounts",
        sa.Column(
            "refunded_total", sa.Numeric(precision=20, scale=4), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "escrow_accounts",
        sa.Column(
            "partner",
            sa.String(length=80),
            server_default="Simulated Escrow Partner",
            nullable=False,
        ),
    )
    op.add_column(
        "escrow_accounts",
        sa.Column("advance_over_20k", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_escrow_accounts_escrow_invariant"),
        "escrow_accounts",
        "funded_total = released_total + refunded_total + balance",
    )

    op.add_column("ledger_entries", sa.Column("kind", sa.String(length=32), nullable=True))
    op.add_column("ledger_entries", sa.Column("milestone_id", sa.Uuid(), nullable=True))
    op.add_column(
        "ledger_entries", sa.Column("fx_rate", sa.Numeric(precision=20, scale=8), nullable=True)
    )
    op.add_column(
        "ledger_entries",
        sa.Column("counter_amount", sa.Numeric(precision=20, scale=4), nullable=True),
    )
    op.add_column("ledger_entries", sa.Column("counter_currency", sa.CHAR(length=3), nullable=True))
    op.create_foreign_key(
        op.f("fk_ledger_entries_milestone_id_milestones"),
        "ledger_entries",
        "milestones",
        ["milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Backfill from the seed's txn_ref convention '<ref>:fund:m1' / '<ref>:release:m2'.
    op.execute(
        """
        UPDATE ledger_entries SET kind = CASE
            WHEN txn_ref LIKE '%:fund:%' THEN 'FUND'
            WHEN txn_ref LIKE '%:release:%' THEN 'RELEASE'
            ELSE 'REFUND' END
        """
    )
    op.execute(
        """
        UPDATE ledger_entries l SET milestone_id = m.id
        FROM milestones m
        WHERE m.deal_id = l.deal_id
          AND l.txn_ref ~ '[:](fund|release|refund)[:]m[0-9]+$'
          AND m.seq = substring(l.txn_ref from '[:]m([0-9]+)$')::int
        """
    )
    op.alter_column("ledger_entries", "kind", nullable=False)
    op.create_check_constraint(
        op.f("ck_ledger_entries_ledger_kind"),
        "ledger_entries",
        "kind IN ('FUND', 'RELEASE', 'REFUND')",
    )

    op.add_column("milestones", sa.Column("condition_text", sa.Text(), nullable=True))
    op.add_column(
        "milestones",
        sa.Column(
            "evidence_status", sa.String(length=32), server_default="PENDING", nullable=False
        ),
    )
    op.add_column(
        "milestones", sa.Column("release_idempotency_key", sa.String(length=80), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_milestones_evidence_status"),
        "milestones",
        "evidence_status IN ('PENDING', 'VERIFIED', 'FLAGGED', 'REJECTED')",
    )
    # Tranches already released had their evidence checked.
    op.execute("UPDATE milestones SET evidence_status = 'VERIFIED' WHERE status = 'RELEASED'")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_milestones_evidence_status"), "milestones", type_="check")
    op.drop_column("milestones", "release_idempotency_key")
    op.drop_column("milestones", "evidence_status")
    op.drop_column("milestones", "condition_text")
    op.drop_constraint(op.f("ck_ledger_entries_ledger_kind"), "ledger_entries", type_="check")
    op.drop_constraint(
        op.f("fk_ledger_entries_milestone_id_milestones"), "ledger_entries", type_="foreignkey"
    )
    for col in ("counter_currency", "counter_amount", "fx_rate", "milestone_id", "kind"):
        op.drop_column("ledger_entries", col)
    op.drop_constraint(
        op.f("ck_escrow_accounts_escrow_invariant"), "escrow_accounts", type_="check"
    )
    for col in ("advance_over_20k", "partner", "refunded_total"):
        op.drop_column("escrow_accounts", col)
    op.drop_constraint(op.f("fk_deals_kyb_run_id_kyb_runs"), "deals", type_="foreignkey")
    op.drop_column("deals", "kyb_run_id")
    op.drop_table("milestone_confirmations")
    op.drop_index(op.f("ix_audit_log_deal_id"), table_name="audit_log")
    op.drop_column("audit_log", "deal_id")
    # audit_log.result stays VARCHAR(64): shrinking it would have to rewrite signed rows.
    # Rows in the new states cannot satisfy the old CHECKs: map them back first.
    op.execute(
        "UPDATE deals SET status = CASE status WHEN 'PROPOSED' THEN 'DRAFT' "
        "WHEN 'CONFIRMED' THEN 'DRAFT' WHEN 'ARRIVED' THEN 'SHIPPED' ELSE status END"
    )
    op.execute(
        "UPDATE milestones SET status = CASE status WHEN 'PROPOSED' THEN 'PENDING' "
        "WHEN 'PENDING_APPROVAL' THEN 'READY' ELSE status END"
    )
    for table, name, col, values in (
        ("deals", "ck_deals_deal_status", "status", DEAL_OLD),
        ("milestones", "ck_milestones_milestone_status", "status", MS_OLD),
    ):
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, _in(col, values))
