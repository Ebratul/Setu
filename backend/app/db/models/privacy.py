"""Privacy transparency records: what the model was sent, masked, plus counters. Never the vault."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk


class PrivacyRecord(Base):
    """One row per LLM call (or per document prepared for one). `masked_payload` is the exact
    text the provider received; the token → value mapping is never stored anywhere."""

    __tablename__ = "privacy_records"

    id: Mapped[UUIDPk]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    source: Mapped[str] = mapped_column(String(16))  # chat | document
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(64))
    node: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    sent: Mapped[bool] = mapped_column(Boolean, default=True)  # False = prepared, not sent
    masked_payload: Mapped[str] = mapped_column(Text)
    masked_output: Mapped[str | None] = mapped_column(Text)
    masked_by_type: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    protected: Mapped[int] = mapped_column(Integer, default=0)
    leaked: Mapped[int] = mapped_column(Integer, default=0)
    chars_sent: Mapped[int] = mapped_column(Integer, default=0)
