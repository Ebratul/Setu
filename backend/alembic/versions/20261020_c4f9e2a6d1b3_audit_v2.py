"""audit_log v2: signed payload, actor id, decision; append-only trigger

The chain scheme changed (setu-audit-v2), so existing rows cannot be re-signed in place: the table
is emptied (TRUNCATE is not blocked) and the seed re-creates a verifying history. Rows elsewhere
that cite an `audit_seq` become dangling in a dev database; run `pnpm db:reset-demo`.

Revision ID: c4f9e2a6d1b3
Revises: b3e8d5a1c7f2
Create Date: 2026-10-20 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4f9e2a6d1b3"
down_revision: str | Sequence[str] | None = "b3e8d5a1c7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE audit_log")
    op.alter_column("audit_log", "result", new_column_name="decision")
    op.alter_column("audit_log", "params_hash", new_column_name="payload_hash")
    op.add_column("audit_log", sa.Column("actor_id", sa.String(length=64), nullable=False))
    op.add_column(
        "audit_log",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% rejected)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.execute("TRUNCATE TABLE audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_column("audit_log", "payload")
    op.drop_column("audit_log", "actor_id")
    op.alter_column("audit_log", "payload_hash", new_column_name="params_hash")
    op.alter_column("audit_log", "decision", new_column_name="result")
