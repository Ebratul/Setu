"""LangGraph state. Nested values are TypedDicts (plain dicts at runtime) so checkpoints only hold
JSON-like data and LangChain messages."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Intent = Literal[
    "greeting",
    "analysis",
    "cashflow",
    "financing",
    "documents",
    "deal_status",
    "how_it_works",
    "out_of_scope",
]
INTENTS: tuple[Intent, ...] = (
    "greeting",
    "analysis",
    "cashflow",
    "financing",
    "documents",
    "deal_status",
    "how_it_works",
    "out_of_scope",
)
Lang = Literal["en", "bn", "zh"]
ModelTier = Literal["fast", "smart"]
StopReason = Literal["budget", "tool_cap", "injection", "model_error"]


class UserCtx(TypedDict):
    id: str
    role: str
    party_id: str | None
    display_name: str
    party_name: str | None


class DealBrief(TypedDict):
    id: str
    reference: str
    status: str


class ToolCallRecord(TypedDict):
    id: str
    name: str
    args_summary: str
    ok: bool
    error_code: str | None


class ToolResult(TypedDict):
    name: str
    ok: bool
    payload: str  # JSON of data or error, rendered into prompts as untrusted data


class Usage(TypedDict):
    input_tokens: int
    output_tokens: int
    total_tokens: int


def zero_usage() -> Usage:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def add_usage(a: Usage, b: Usage) -> Usage:
    return {
        "input_tokens": a["input_tokens"] + b["input_tokens"],
        "output_tokens": a["output_tokens"] + b["output_tokens"],
        "total_tokens": a["total_tokens"] + b["total_tokens"],
    }


class AgentState(BaseModel):
    messages: Annotated[list[AnyMessage], add_messages] = Field(default_factory=list)
    user: UserCtx | None = None
    language: Lang | None = None
    deal_id: str | None = None
    active_deals: list[DealBrief] = Field(default_factory=list)

    # Per turn (reset by load_context)
    turn_start: int = 0
    privacy_checked: bool = False
    intent: Intent | None = None
    needs_smart_model: bool = False
    model_tier: ModelTier = "fast"
    model_used: str | None = None
    route_source: Literal["model", "keywords"] | None = None
    pending_tool_calls: bool = False
    tool_steps: int = 0
    tool_calls_made: list[ToolCallRecord] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    injection_flags: list[str] = Field(default_factory=list)
    token_usage: Usage = Field(default_factory=zero_usage)
    thread_tokens_before: int = 0
    citations: list[str] = Field(default_factory=list)  # RAG chunk ids (P10)
    stop_reason: StopReason | None = None
    answer: str | None = None
    trace_id: str | None = None
    run_url: str | None = None
