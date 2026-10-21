"""user_auth_identity: link users to Neon Auth (auth_subject), account status, login bookkeeping

Revision ID: e7a3c1d9b5f4
Revises: d6b1f4a8c2e9
Create Date: 2026-10-21 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7a3c1d9b5f4"
down_revision: str | Sequence[str] | None = "d6b1f4a8c2e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_subject", sa.String(length=128), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_unique_constraint(op.f("uq_users_auth_subject"), "users", ["auth_subject"])
    op.create_check_constraint(
        op.f("ck_users_user_status"),
        "users",
        "status IN ('PENDING', 'ACTIVE', 'SUSPENDED')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_user_status"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_auth_subject"), "users", type_="unique")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "status")
    op.drop_column("users", "auth_subject")
