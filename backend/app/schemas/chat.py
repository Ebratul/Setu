"""Chat API models (POST /chat, POST /chat/stream, thread reads)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.cards import Card

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


class Citation(BaseModel):
    cite_id: str
    source_id: str
    title: str
    heading_path: str
    source_type: str
    original_reference: str
    last_reviewed: str
    disclaimer: str
    guide_url: str | None = Field(
        None, description="user_guide sources only: public doc URL, with #anchor when known."
    )


class IgnoredInstruction(BaseModel):
    source: str = Field(
        description="hidden_text | visible_text | metadata | email | kb | tool_result"
    )
    rules: list[str]
    score: int = 0


class BlockedTool(BaseModel):
    name: str
    code: str


class SecurityCheckOut(BaseModel):
    """What the prompt-injection defences did for this answer (the "Security check" chip)."""

    defences: bool = True
    checked: list[str] = Field(
        description="Tools whose results (documents, KB, parties) were scanned."
    )
    ignored: list[IgnoredInstruction] = Field(default_factory=list)
    blocked_tools: list[BlockedTool] = Field(default_factory=list)
    deal_flagged: bool = False
    guard: list[str] = Field(default_factory=list, description="Output-guard removals.")


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
    message_id: uuid.UUID = Field(description="The assistant message (for feedback).")
    why: str | None = Field(None, description='The "Why:" line of the answer.')
    notes: list[str] = Field(default_factory=list, description="Code-added notes (simulated…).")
    cards: list[Card] = Field(default_factory=list, description="Result cards, in tool order.")
    citations: list[Citation] = Field(
        default_factory=list, description="Knowledge-base sources cited in the answer ([S1]…)."
    )
    security: SecurityCheckOut | None = Field(
        None, description="Set when the answer involved untrusted content."
    )


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
    id: uuid.UUID
    seq: int
    role: Literal["user", "assistant", "tool"]
    content: str
    created_at: datetime
    meta: dict[str, Any] | None
    card: Card | None = Field(None, description="For tool messages that produced a card.")


class ThreadPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("title must not be blank")
        return v


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: Literal["up", "down"]
    comment: str | None = Field(None, max_length=500)


class FeedbackOut(BaseModel):
    message_id: uuid.UUID
    rating: Literal["up", "down"]


class MessageList(BaseModel):
    thread_id: uuid.UUID
    messages: list[MessageOut]
