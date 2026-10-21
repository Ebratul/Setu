"""demo_sandboxes: registry of isolated judge sandboxes (one Postgres schema each)

Revision ID: d6b1f4a8c2e9
Revises: c4f9e2a6d1b3
Create Date: 2026-10-20 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d6b1f4a8c2e9"
down_revision: str | Sequence[str] | None = "c4f9e2a6d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_sandboxes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schema_name", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("live_ai", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("llm_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resets", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "run_state",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_sandboxes")),
        sa.UniqueConstraint("schema_name", name=op.f("uq_demo_sandboxes_schema_name")),
    )
    op.create_index(op.f("ix_demo_sandboxes_expires_at"), "demo_sandboxes", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_demo_sandboxes_expires_at"), table_name="demo_sandboxes")
    op.drop_table("demo_sandboxes")
