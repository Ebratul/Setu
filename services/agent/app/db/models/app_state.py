import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Created, UUIDPk, str_enum
from app.db.enums import ChatRole, Language

EMBEDDING_DIM = 384


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[UUIDPk]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    language: Mapped[Language] = mapped_column(str_enum(Language, "chat_language"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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
    __tablename__ = "kb_chunks"

    id: Mapped[UUIDPk]
    source: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(200))
    heading_path: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
