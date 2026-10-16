"""Chat API models (POST /chat, POST /chat/stream, thread reads)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChatLanguage = Literal["en", "bn", "zh"]
MAX_MESSAGE_CHARS = 4000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    language: ChatLanguage | None = None
    deal_id: str | None = Field(None, max_length=64, pattern=r"^[A-Za-z0-9-]+$")

    @field_validator("language", mode="before")
    @classmethod
    def _lower(cls, v: Any) -> Any:
        return v.lower() if isinstance(v, str) else v

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank")
        return v


class ToolCallOut(BaseModel):
    name: str
    args_summary: str
    ok: bool


class UsageOut(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    thread_total: int
    thread_budget: int


class ChatResponse(BaseModel):
    simulated: Literal[True] = True
    thread_id: uuid.UUID
    answer: str
    intent: str | None
    model_used: str | None
    language: ChatLanguage
    tool_calls: list[ToolCallOut]
    usage: UsageOut
    stopped: Literal["budget", "tool_cap", "injection", "model_error"] | None = None
    trace_url: str | None = Field(None, description="LangSmith run URL; admin and judge only.")


class ThreadOut(BaseModel):
    id: uuid.UUID
    title: str
    language: ChatLanguage
    deal_id: uuid.UUID | None
    tokens_used: int
    created_at: datetime
    updated_at: datetime | None


class ThreadList(BaseModel):
    threads: list[ThreadOut]


class MessageOut(BaseModel):
    seq: int
    role: Literal["user", "assistant", "tool"]
    content: str
    created_at: datetime
    meta: dict[str, Any] | None


class MessageList(BaseModel):
    thread_id: uuid.UUID
    messages: list[MessageOut]
