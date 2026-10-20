"""onboarding_members: party tax id, party members, onboarding reviews

Revision ID: f1b8d2c4a6e3
Revises: e7a3c1d9b5f4
Create Date: 2026-10-22 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f1b8d2c4a6e3"
down_revision: str | Sequence[str] | None = "e7a3c1d9b5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parties", sa.Column("tax_id", sa.String(length=32), nullable=True))
    op.add_column("parties", sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "party_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "member_role",
            sa.Enum(
                "OWNER",
                "FINANCE",
                "VIEWER",
                name="member_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], name=op.f("fk_party_members_party_id_parties")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_party_members_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_party_members")),
        sa.UniqueConstraint("party_id", "user_id", name=op.f("uq_party_members_party_id_user_id")),
    )
    op.create_index(op.f("ix_party_members_party_id"), "party_members", ["party_id"])
    op.create_index(op.f("ix_party_members_user_id"), "party_members", ["user_id"])
    op.create_table(
        "onboarding_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "APPROVED",
                "REJECTED",
                name="onboarding_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], name=op.f("fk_onboarding_reviews_decided_by_users")),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], name=op.f("fk_onboarding_reviews_party_id_parties")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_onboarding_reviews_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_reviews")),
    )
    op.create_index(op.f("ix_onboarding_reviews_user_id"), "onboarding_reviews", ["user_id"])
    op.create_index(op.f("ix_onboarding_reviews_party_id"), "onboarding_reviews", ["party_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_onboarding_reviews_party_id"), table_name="onboarding_reviews")
    op.drop_index(op.f("ix_onboarding_reviews_user_id"), table_name="onboarding_reviews")
    op.drop_table("onboarding_reviews")
    op.drop_index(op.f("ix_party_members_user_id"), table_name="party_members")
    op.drop_index(op.f("ix_party_members_party_id"), table_name="party_members")
    op.drop_table("party_members")
    op.drop_column("parties", "onboarded_at")
    op.drop_column("parties", "tax_id")
