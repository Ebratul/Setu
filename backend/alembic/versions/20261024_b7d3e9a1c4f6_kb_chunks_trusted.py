"""kb_chunks.trusted: first-party user guide chunks skip the injection gate

Revision ID: b7d3e9a1c4f6
Revises: a9c4e7b2d5f8
Create Date: 2026-10-24 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d3e9a1c4f6"
down_revision: str | Sequence[str] | None = "a9c4e7b2d5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kb_chunks",
        sa.Column("trusted", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("kb_chunks", "trusted")
