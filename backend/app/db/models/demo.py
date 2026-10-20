import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPk


class DemoSandbox(Base):
    """Registry of judge sandboxes. Lives in `public` (never copied into a sandbox schema): one row
    per sandbox, whose data is the Postgres schema `schema_name`. `run_state` is the guided-demo
    progress (scene results, cursor); sandboxes expire and a cleanup job drops the schema."""

    __tablename__ = "demo_sandboxes"

    id: Mapped[UUIDPk]
    schema_name: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    live_ai: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    resets: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    run_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


def new_id() -> uuid.UUID:
    return uuid.uuid4()
