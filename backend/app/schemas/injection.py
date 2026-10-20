"""Prompt-injection console, scoreboard and admin event models (P19)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Placement = Literal["hidden_text", "visible_text", "metadata", "email"]
StepStatus = Literal["done", "caught", "clear", "off", "missed", "idle"]


class GalleryOut(BaseModel):
    id: str
    label_en: str
    label_bn: str
    style: str
    source: Placement
    target: str
    language: str
    carrier_en: str
    text: str


class GalleryList(BaseModel):
    items: list[GalleryOut]


class ConsoleRunIn(BaseModel):
    """One attack. Either a gallery id, or your own text and where it sits."""

    model_config = ConfigDict(extra="forbid")

    attack_id: str | None = Field(None, max_length=64, pattern=r"^[a-z0-9-]+$")
    text: str | None = Field(None, max_length=8000)
    source: Placement = "visible_text"
    defences: bool = True


class Highlight(BaseModel):
    start: int
    end: int
    rule: str


class Step(BaseModel):
    id: Literal["privacy", "wrap", "detector", "gating", "risk", "answer"]
    layer: int = Field(
        description="0 privacy, 1 wrap, 2 detector, 4 gating, 3 risk, 5 output guard"
    )
    ok: bool = Field(description="True = shown as ✓ (handled safely), False = ✕")
    status: StepStatus
    title_en: str
    title_bn: str
    detail_en: str
    detail_bn: str
    data: dict[str, Any] = Field(default_factory=dict)


class ToolAttempt(BaseModel):
    name: str
    outcome: Literal["dropped_by_gate", "reached_service_then_risk_engine", "executed"]
    layer: int | None = None
    risk_tier: int | None = None
    risk_decision: str | None = None


class DetectionOut(BaseModel):
    is_injection: bool
    score: int
    matched_rules: list[str]
    source: str
    snippet: str
    highlights: list[Highlight]


class ConsoleRunOut(BaseModel):
    simulated: Literal[True] = True
    defences: bool
    attack_id: str | None
    source: Placement
    text: str
    steps: list[Step]
    detection: DetectionOut | None
    attempts: list[ToolAttempt]
    answer: str
    blocked_at_layer: int | None
    outcome: Literal["blocked", "stopped_by_risk_engine", "no_effect", "attack_succeeded"]
    result_en: str
    result_bn: str
    money_moved: Literal[False] = False
    event_id: uuid.UUID | None = None


class ModeStats(BaseModel):
    n: int
    attack_success_rate: float
    forbidden_attempts: int
    reached_services: int
    answers_that_followed: int
    detected: int
    money_moved: int
    per_style: dict[str, dict[str, Any]]


class DetectionStats(BaseModel):
    recall: float
    end_to_end_recall: float
    clean_documents: int
    false_positives: int
    false_positive_rate: float


class ScoreboardOut(BaseModel):
    simulated: Literal[True] = True
    available: bool
    split: str = "dev"
    generated_at: datetime | None = None
    attacks: int = 0
    modes: dict[str, ModeStats] = Field(default_factory=dict)
    detection: DetectionStats | None = None
    layer_attribution: dict[str, int] = Field(default_factory=dict)
    notes: str = ""


class InjectionEventOut(BaseModel):
    id: uuid.UUID
    ts: datetime
    kind: Literal["DETECTED", "BLOCKED_TOOL"]
    source: str
    origin: str
    rules: list[str]
    score: int
    snippet: str
    attack_style: str | None
    tool: str | None
    action_taken: str
    layer: int | None
    defences_on: bool
    flags_deal: bool
    resolved: bool
    deal_id: uuid.UUID | None
    deal_reference: str | None
    document_id: uuid.UUID | None
    audit_seq: int | None


class InjectionEventList(BaseModel):
    items: list[InjectionEventOut]
    total: int
    by_style: dict[str, int]
    by_source: dict[str, int]
