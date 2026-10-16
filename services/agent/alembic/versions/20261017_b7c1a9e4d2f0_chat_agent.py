"""chat agent: tool role, message meta, thread budget, LangGraph checkpoint tables

Revision ID: b7c1a9e4d2f0
Revises: 60340801e54e
Create Date: 2026-10-17 12:00:00

The LangGraph checkpoint tables are created here (not by `PostgresSaver.setup()`) so Alembic
stays the single schema owner. The DDL is the pinned langgraph-checkpoint-postgres 3.2.0
`MIGRATIONS` list, and `checkpoint_migrations` is filled the same way `setup()` does, so the
library sees an up-to-date schema and never migrates by itself.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7c1a9e4d2f0"
down_revision: str | Sequence[str] | None = "60340801e54e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKPOINT_DDL = [
    """CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
)""",
    """CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
)""",
    """CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
)""",
    """CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
)""",
    "CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
    "CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
]
# len(BasePostgresSaver.MIGRATIONS) for langgraph-checkpoint-postgres 3.2.0.
CHECKPOINT_MIGRATION_COUNT = 10


def upgrade() -> None:
    op.drop_constraint(op.f("ck_chat_messages_chat_role"), "chat_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_chat_messages_chat_role"), "chat_messages", "role IN ('user', 'assistant', 'tool')"
    )
    op.add_column("chat_messages", sa.Column("meta", postgresql.JSONB(), nullable=True))
    op.add_column("chat_threads", sa.Column("deal_id", sa.Uuid(), nullable=True))
    op.add_column(
        "chat_threads",
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "chat_threads", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_chat_threads_deal_id_deals"),
        "chat_threads",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for ddl in CHECKPOINT_DDL:
        op.execute(ddl)
    op.execute(
        "INSERT INTO checkpoint_migrations (v) SELECT generate_series(0, "
        f"{CHECKPOINT_MIGRATION_COUNT - 1}) ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints", "checkpoint_migrations"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.drop_constraint(op.f("fk_chat_threads_deal_id_deals"), "chat_threads", type_="foreignkey")
    op.drop_column("chat_threads", "updated_at")
    op.drop_column("chat_threads", "tokens_used")
    op.drop_column("chat_threads", "deal_id")
    op.drop_column("chat_messages", "meta")
    op.execute("DELETE FROM chat_messages WHERE role = 'tool'")
    op.drop_constraint(op.f("ck_chat_messages_chat_role"), "chat_messages", type_="check")
    op.create_check_constraint(
        op.f("ck_chat_messages_chat_role"), "chat_messages", "role IN ('user', 'assistant')"
    )
