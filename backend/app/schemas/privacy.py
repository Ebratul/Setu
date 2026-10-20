"""Privacy API models (Phase P18). Everything returned is either the caller's own text or the
masked payload; the token vault never appears here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    """A run of text; `type` is set when it is a protected value (NID, ACCT, PHONE, AMT …)."""

    text: str
    type: str | None = None
    token: str | None = None


class StatsOut(BaseModel):
    masked_by_type: dict[str, int] = Field(default_factory=dict)
    protected: int = 0
    leaked_count: int = 0
    chars_sent: int = 0


class HitOut(BaseModel):
    type: str
    start: int
    end: int
    confidence: float
    token: str
    obfuscated: bool
    label_en: str
    label_bn: str


class PrivacyDryRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=8000)
    mask_amounts: bool = True


class PrivacyDryRunOut(BaseModel):
    simulated: Literal[True] = True
    mask_amounts: bool
    hits: list[HitOut]
    source_segments: list[Segment]
    masked_segments: list[Segment]
    masked: str
    ai_answer_masked: str
    ai_answer_segments: list[Segment]
    restored_answer: str
    restored_segments: list[Segment]
    stats: StatsOut


class SummaryOut(BaseModel):
    protected: int
    leaked: int
    calls: int
    by_type: dict[str, int]


class LeftBlock(BaseModel):
    label: str
    segments: list[Segment]


class RightBlock(BaseModel):
    label: str
    node: str
    model: str | None
    sent: bool
    segments: list[Segment]


class XrayOut(BaseModel):
    kind: Literal["message", "document"]
    available: bool
    stats: StatsOut
    left: list[LeftBlock]
    right: list[RightBlock]


class DayPoint(BaseModel):
    day: str
    protected: int
    leaked: int


class RecentRecord(BaseModel):
    id: str
    created_at: str
    source: str
    node: str
    model: str | None
    sent: bool
    protected: int
    leaked: int
    by_type: dict[str, int]
    masked_payload: str


class TraceOut(BaseModel):
    enabled: bool
    url: str | None
    run_id: str | None
    note: str


class PrivacyConfigOut(BaseModel):
    enabled: bool
    mask_amounts: bool


class TotalsOut(BaseModel):
    protected: int
    leaked: int
    calls: int


class PrivacyOverviewOut(BaseModel):
    totals: TotalsOut
    by_type: dict[str, int]
    series: list[DayPoint]
    recent: list[RecentRecord]
    trace: TraceOut
    config: PrivacyConfigOut
