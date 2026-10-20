"""p30_onboarding_verification: multi-step onboarding, verification gate, field encryption

Revision ID: c4e8a2f6b9d1
Revises: b7d3e9a1c4f6
Create Date: 2026-10-25 09:00:00.000000

Statuses are VARCHAR(32) + CHECK (not a native enum), so widening the set is: drop the check,
migrate the data, add the new check. Downgrade maps the new values back (any PENDING_* -> PENDING,
REJECTED -> SUSPENDED, CHANGES_REQUESTED -> PENDING).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4e8a2f6b9d1"
down_revision: str | Sequence[str] | None = "b7d3e9a1c4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_USER = "'PENDING_PROFILE', 'PENDING_VERIFICATION', 'ACTIVE', 'REJECTED', 'SUSPENDED'"
OLD_USER = "'PENDING', 'ACTIVE', 'SUSPENDED'"
NEW_REVIEW = "'PENDING', 'APPROVED', 'REJECTED', 'CHANGES_REQUESTED', 'SUSPENDED'"
OLD_REVIEW = "'PENDING', 'APPROVED', 'REJECTED'"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _recheck(table: str, name: str, column: str, allowed: str) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, f"{column} IN ({allowed})")


def upgrade() -> None:
    op.drop_constraint(op.f("ck_users_user_status"), "users", type_="check")
    op.execute("UPDATE users SET status = 'PENDING_VERIFICATION' WHERE status = 'PENDING'")
    op.create_check_constraint(op.f("ck_users_user_status"), "users", f"status IN ({NEW_USER})")
    _recheck("onboarding_reviews", "onboarding_status", "status", NEW_REVIEW)

    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.LargeBinary()))
    op.add_column("users", sa.Column("mfa_recovery_hashes", postgresql.JSONB()))
    # before P30 the email step-up set mfa_enabled; that was never TOTP, so no secret = not enabled
    op.execute("UPDATE users SET mfa_enabled = false WHERE mfa_secret_encrypted IS NULL")
    op.add_column("users", sa.Column("mfa_last_step", sa.BigInteger()))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("terms_version", sa.String(length=32)))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("auth_provider", sa.String(length=32)))

    op.add_column("parties", sa.Column("dedupe_key", sa.CHAR(length=64)))
    op.create_index(
        "uq_parties_kind_dedupe_key",
        "parties",
        ["kind", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.add_column("bank_accounts", sa.Column("account_number_encrypted", sa.LargeBinary()))
    op.add_column("bank_accounts", sa.Column("account_number_hmac", sa.CHAR(length=64)))
    op.create_index(
        op.f("ix_bank_accounts_account_number_hmac"), "bank_accounts", ["account_number_hmac"]
    )

    op.create_table(
        "onboarding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            _enum("onboarding_profile_role", "BUYER", "SUPPLIER", "ADMIN", "JUDGE"),
            nullable=False,
        ),
        sa.Column("step", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("secure", sa.LargeBinary()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text()),
        sa.Column(
            "decision",
            _enum(
                "onboarding_decision", "APPROVED", "CHANGES_REQUESTED", "REJECTED", "SUSPENDED"
            ),
        ),
        sa.Column("change_requests", postgresql.JSONB(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_onboarding_profiles_user_id_users")),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_onboarding_profiles_reviewed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_onboarding_profiles_user_id")),
    )
    op.create_table(
        "verification_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column(
            "type",
            _enum(
                "verification_doc_type",
                "TRADE_LICENSE",
                "IRC",
                "TIN_CERT",
                "BUSINESS_LICENSE",
                "BANK_PROOF",
                "OTHER",
            ),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("original_name", sa.String(length=160), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "status",
            _enum("verification_doc_status", "UPLOADED", "VERIFIED", "REJECTED"),
            nullable=False,
        ),
        sa.Column("reviewer_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_verification_documents_user_id_users")),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["onboarding_profiles.id"],
            name=op.f("fk_verification_documents_profile_id_onboarding_profiles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_documents")),
    )
    op.create_index(
        op.f("ix_verification_documents_user_id"), "verification_documents", ["user_id"]
    )
    op.create_index(
        op.f("ix_verification_documents_profile_id"), "verification_documents", ["profile_id"]
    )
    op.create_index(op.f("ix_verification_documents_sha256"), "verification_documents", ["sha256"])
    op.create_table(
        "phone_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone_masked", sa.String(length=32), nullable=False),
        sa.Column("phone_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("code_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_phone_verifications_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phone_verifications")),
    )
    op.create_index(op.f("ix_phone_verifications_user_id"), "phone_verifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("phone_verifications")
    op.drop_table("verification_documents")
    op.drop_table("onboarding_profiles")
    op.drop_index(op.f("ix_bank_accounts_account_number_hmac"), table_name="bank_accounts")
    op.drop_column("bank_accounts", "account_number_hmac")
    op.drop_column("bank_accounts", "account_number_encrypted")
    op.drop_index("uq_parties_kind_dedupe_key", table_name="parties")
    op.drop_column("parties", "dedupe_key")
    for col in (
        "auth_provider",
        "deleted_at",
        "terms_version",
        "privacy_accepted_at",
        "terms_accepted_at",
        "mfa_last_step",
        "mfa_recovery_hashes",
        "mfa_secret_encrypted",
        "email_verified_at",
    ):
        op.drop_column("users", col)

    op.execute("UPDATE onboarding_reviews SET status = 'PENDING' WHERE status = 'CHANGES_REQUESTED'")
    op.execute("UPDATE onboarding_reviews SET status = 'REJECTED' WHERE status = 'SUSPENDED'")
    _recheck("onboarding_reviews", "onboarding_status", "status", OLD_REVIEW)
    op.drop_constraint(op.f("ck_users_user_status"), "users", type_="check")
    op.execute(
        "UPDATE users SET status = CASE status "
        "WHEN 'PENDING_PROFILE' THEN 'PENDING' WHEN 'PENDING_VERIFICATION' THEN 'PENDING' "
        "WHEN 'REJECTED' THEN 'SUSPENDED' ELSE status END"
    )
    op.create_check_constraint(op.f("ck_users_user_status"), "users", f"status IN ({OLD_USER})")
