import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Created, UUIDPk, str_enum
from app.db.enums import ChatRole, Language

EMBEDDING_DIM = 384
KB_TSV = (
    "to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || "
    "coalesce(heading_path, '') || ' ' || coalesce(content, ''))"
)


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[UUIDPk]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[Language] = mapped_column(str_enum(Language, "chat_language"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="SET NULL")
    )
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("thread_id", "seq"),)

    id: Mapped[UUIDPk]
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chat_threads.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[ChatRole] = mapped_column(str_enum(ChatRole, "chat_role"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # intent, model, tool name/ok/args summary, token usage. No raw PII.
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DemoState(Base):
    """Singleton row (id=1): demo step pointer and the anchor date the seed was built with."""

    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    step: Mapped[int] = mapped_column(Integer, default=0)
    anchor_date: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LlmCache(Base):
    """Cache of LLM results keyed by sha256(model + prompt version + masked input)."""

    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(64))
    prompt_id: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[Created]


class KbChunk(Base):
    """One heading-sized chunk of a knowledge-base source (backend/kb/sources)."""

    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("source_id", "seq"),
        Index(
            "ix_kb_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_kb_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[UUIDPk]
    source_id: Mapped[str] = mapped_column(String(120), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    heading_path: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # 'simple' config: no stemming or stop words, so codes like "FOB" and Bangla tokens match as-is.
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(KB_TSV, persisted=True),
    )
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
