"""kb_chunks for RAG: source ids, language, content hash, metadata, tsvector, HNSW + GIN indexes

Revision ID: c4d2e8f1a9b3
Revises: b7c1a9e4d2f0
Create Date: 2026-10-17 08:00:00

The table held no rows before this phase (the indexer is new), so it is rebuilt rather than
altered column by column.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4d2e8f1a9b3"
down_revision: str | Sequence[str] | None = "b7c1a9e4d2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV = (
    "to_tsvector('simple'::regconfig, "
    "coalesce(title, '') || ' ' || coalesce(heading_path, '') || ' ' || coalesce(content, ''))"
)


def upgrade() -> None:
    op.drop_table("kb_chunks")
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("heading_path", sa.String(length=300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=384), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(TSV, persisted=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_chunks")),
        sa.UniqueConstraint("source_id", "seq", name=op.f("uq_kb_chunks_source_id_seq")),
    )
    op.create_index(op.f("ix_kb_chunks_source_id"), "kb_chunks", ["source_id"])
    op.create_index(op.f("ix_kb_chunks_content_hash"), "kb_chunks", ["content_hash"])
    op.create_index(
        "ix_kb_chunks_embedding_hnsw",
        "kb_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_kb_chunks_tsv", "kb_chunks", ["tsv"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("kb_chunks")
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("heading_path", sa.String(length=300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=384), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kb_chunks")),
    )
    op.create_index(op.f("ix_kb_chunks_source"), "kb_chunks", ["source"])
