"""API shapes of the guided demo (/demo/*)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.demo.script import Bi

Status = Literal["pending", "running", "passed", "failed"]
Tag = Literal["TASK", "SECURITY", "INNOVATION"]
View = Literal["buyer", "supplier", "admin", "split"]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SceneDefOut(Out):
    k: int
    view: View
    login_as: str
    route: str = Field(description="Route template; the resolved route comes with the result.")
    highlight: str | None = Field(None, description="CSS selector of the element to spotlight.")
    caption: Bi


class StepDefOut(Out):
    n: int
    id: str
    tag: Tag
    title: Bi
    narration: Bi
    notes: Bi = Field(description="Presenter talking points (presenter mode only).")
    scenes: list[SceneDefOut]


class ScoreDefOut(Out):
    id: str
    group: Tag
    after: str = Field(description='Scene "n.k" whose success ticks this item.')
    link: str
    label: Bi


class ScriptOut(Out):
    simulated: Literal[True] = True
    steps: list[StepDefOut]
    scorecard: list[ScoreDefOut]
    total_scenes: int


class AssertionOut(Out):
    label: Bi
    ok: bool
    expected: str
    actual: str


class LlmNote(Out):
    mode: Literal["off", "replay", "record", "live"]
    fixtures_used: int
    misses: int


class SceneResultOut(Out):
    n: int
    k: int
    status: Status
    started_at: datetime | None = None
    duration_ms: int | None = None
    assertions: list[AssertionOut] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    route: str | None = Field(None, description="Resolved route to show in the embedded app.")
    message: Bi | None = Field(None, description="Friendly text when the scene could not finish.")
    error_code: str | None = None
    llm: LlmNote | None = None


class ScoreItemOut(Out):
    id: str
    group: Tag
    label: Bi
    link: str
    after: str
    ticked: bool


class SandboxOut(Out):
    simulated: Literal[True] = True
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    replay: bool = Field(description="AI answers come from recorded fixtures (identical, offline).")
    live_ai: bool
    live_ai_available: bool = Field(description="A real model key is configured on the server.")
    live_ai_budget_left: int
    resets: int


class CursorOut(Out):
    n: int
    k: int


class RunOut(Out):
    sandbox: SandboxOut
    cursor: CursorOut | None = None
    scenes: list[SceneResultOut]
    scorecard: list[ScoreItemOut]
    total_scenes: int
    passed: int
    failed: int
    completed: bool
    last: SceneResultOut | None = None


class GotoIn(Out):
    step: int = Field(ge=1, le=99, description="Run every earlier scene that has not run yet.")


class LiveAiIn(Out):
    enabled: bool


class SandboxCreateIn(Out):
    fresh: bool = Field(False, description="Discard the current sandbox and start a new one.")


class SummaryNumber(Out):
    key: str
    value: str
    label: Bi


class SummaryLink(Out):
    label: Bi
    href: str


class SummaryOut(Out):
    simulated: Literal[True] = True
    ready: bool = Field(description="All scenes have run.")
    numbers: list[SummaryNumber]
    attacks: list[Bi]
    links: list[SummaryLink]
    run_seconds: float | None = None


class PreflightItem(Out):
    id: str
    label: Bi
    ok: bool
    detail: str


class PreflightOut(Out):
    ok: bool
    replay: bool
    items: list[PreflightItem]


class CoolingOffOut(Out):
    skipped: int
    note: str = "Demo only: the cooling-off pause was skipped in this sandbox (audited)."
