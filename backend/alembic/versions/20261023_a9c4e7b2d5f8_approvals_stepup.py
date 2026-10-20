"""approvals_stepup: approval_requests.requested_by_user_id (four-eyes), stepup_challenges

Revision ID: a9c4e7b2d5f8
Revises: f1b8d2c4a6e3
Create Date: 2026-10-23 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9c4e7b2d5f8"
down_revision: str | Sequence[str] | None = "f1b8d2c4a6e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("requested_by_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_approval_requests_requested_by_user_id_users"),
        "approval_requests",
        "users",
        ["requested_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "stepup_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_stepup_challenges_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stepup_challenges")),
    )
    op.create_index(op.f("ix_stepup_challenges_user_id"), "stepup_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_stepup_challenges_user_id"), table_name="stepup_challenges")
    op.drop_table("stepup_challenges")
    op.drop_constraint(
        op.f("fk_approval_requests_requested_by_user_id_users"), "approval_requests", type_="foreignkey"
    )
    op.drop_column("approval_requests", "requested_by_user_id")
