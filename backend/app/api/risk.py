"""Risk engine read models and the dry-run (Phase 5.1). The dry-run calls the real engine on facts
the caller types in and saves nothing; the overview is for admins and judges."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.db.enums import Role
from app.db.models import Deal, RiskEvent
from app.db.session import get_db
from app.errors import Forbidden
from app.schemas.analysis import InDec
from app.schemas.deals import HintOut, RiskOut, TraceItemOut
from app.security.policy import CONFIG_PATH, load_policy
from app.services.risk import engine
from app.services.risk.engine import Action, Origin, RiskContext

router = APIRouter(tags=["risk"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
SERIES_DAYS = 14


class DryRunRequest(BaseModel):
    """Facts for a what-if. Unknown fields are rejected: there is no way to pass a tier."""

    model_config = ConfigDict(extra="forbid")

    action: Action = Action.RELEASE_TRANCHE
    origin: Origin = Origin.USER_UI
    amount_usd: InDec = "5760"
    first_deal: bool = False
    beneficiary_change: bool = False
    beneficiary_changed_recently: bool = False
    kyb_status: Literal["VERIFIED", "WARNING", "BLOCKED"] = "VERIFIED"
    kyb_account_warning: bool = False
    fraud_score: int = Field(default=0, ge=0, le=100)
    document_warning: bool = False
    document_failed: bool = False
    duplicate_hash: bool = False
    hidden_instruction: bool = False
    sanctions_hit: bool = False
    fx_lock_missing: bool = False


class DryRunOut(RiskOut):
    dry_run: Literal[True] = True
    saved: Literal[False] = False


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    kind: Literal["BLOCK", "TIER3", "TIER2"]
    applies_to: list[str]
    label_en: str
    label_bn: str
    condition_en: str
    condition_bn: str


class PolicyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    yaml: str
    tier1_max_usd: str
    fraud_score_tier3_above: int
    new_beneficiary_days: int
    cooling_off_minutes: int
    rules: list[PolicyRule]


class Counters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_released: int
    one_tap: int
    otp_required: int
    blocked: int


class DayPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    auto: int
    one_tap: int
    otp: int
    blocked: int


class EventRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    ts: datetime
    deal_ref: str | None
    action: str
    origin: str
    decision: str
    tier: int
    reason_codes: list[str]
    explanation_en: str
    explanation_bn: str
    trace: list[TraceItemOut]
    hints: list[HintOut]


class OverviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulated: Literal[True] = True
    counters: Counters
    series: list[DayPoint]
    latest_blocked: list[EventRow]
    recent: list[EventRow]


def _reader(user: CurrentUser) -> None:
    if user.role not in (Role.ADMIN, Role.JUDGE):
        raise Forbidden("the risk overview is for admins and judges")


@router.post("/risk/evaluate", response_model=DryRunOut)
def dry_run(body: DryRunRequest, user: User) -> DryRunOut:
    """What-if on the real engine. Nothing is read from or written to the database."""
    amount = Decimal(body.amount_usd)
    ctx = RiskContext(
        action=body.action,
        origin=body.origin,
        amount=amount,
        currency="USD",
        amount_usd=amount,
        is_first_deal_with_supplier=body.first_deal,
        beneficiary_changed_recently=body.beneficiary_changed_recently,
        beneficiary_status="PENDING_CHANGE" if body.beneficiary_change else "ACTIVE",
        kyb_status=body.kyb_status,
        kyb_account_warning=body.kyb_account_warning,
        max_document_fraud_score=body.fraud_score,
        any_document_warning=body.document_warning,
        any_document_failed=body.document_failed,
        duplicate_hash=body.duplicate_hash,
        instruction_from_document=body.hidden_instruction,
        sanctions_hit=body.sanctions_hit,
        fx_lock_missing=body.fx_lock_missing,
    )
    d = engine.evaluate(ctx)
    return DryRunOut(
        decision=d.decision.value,  # type: ignore[arg-type]
        tier=d.tier,
        reasons=[engine.TEXT[c][0] for c in d.reason_codes],
        explanation_en=d.explanation_en,
        explanation_bn=d.explanation_bn,
        context_hash=d.context_hash,
        decided_by=d.decided_by,
        trace=[TraceItemOut.model_validate(t.model_dump()) for t in d.trace],
        hints=[HintOut.model_validate(h.model_dump()) for h in d.hints],
    )


@router.get("/risk/policy", response_model=PolicyOut)
def policy(user: User) -> PolicyOut:
    """config/risk.yaml and the rules it drives, as a table (EN/BN)."""
    p = load_policy()
    return PolicyOut(
        source="config/risk.yaml",
        yaml=CONFIG_PATH.read_text(encoding="utf-8"),
        tier1_max_usd=str(p.tier1_max_usd),
        fraud_score_tier3_above=p.fraud_score_tier3_above,
        new_beneficiary_days=p.new_beneficiary_days,
        cooling_off_minutes=p.cooling_off_minutes,
        rules=[PolicyRule.model_validate(r.model_dump()) for r in engine.rules_table(p)],
    )


def _row(e: RiskEvent, ref: str | None) -> EventRow:
    return EventRow(
        id=str(e.id),
        ts=e.ts,
        deal_ref=ref,
        action=e.action,
        origin=e.origin,
        decision=e.decision,
        tier=e.tier,
        reason_codes=list(e.reason_codes or []),
        explanation_en=e.explanation_en,
        explanation_bn=e.explanation_bn,
        trace=[TraceItemOut.model_validate(t) for t in e.trace or []],
        hints=[HintOut.model_validate(h) for h in e.hints or []],
    )


@router.get("/risk/overview", response_model=OverviewOut)
def overview(db: Db, user: User) -> OverviewOut:
    _reader(user)
    since = datetime.now(UTC) - timedelta(days=SERIES_DAYS)

    def count(*cond: object) -> int:
        return db.scalar(select(func.count()).select_from(RiskEvent).where(*cond)) or 0  # type: ignore[arg-type]

    counters = Counters(
        auto_released=count(RiskEvent.decision == "ALLOW", RiskEvent.tier == 1),
        one_tap=count(RiskEvent.decision == "REQUIRE_APPROVAL", RiskEvent.tier == 2),
        otp_required=count(RiskEvent.decision == "REQUIRE_APPROVAL", RiskEvent.tier == 3),
        blocked=count(RiskEvent.decision == "BLOCK"),
    )
    day = func.date_trunc("day", RiskEvent.ts)
    rows = db.execute(
        select(day, RiskEvent.decision, RiskEvent.tier, func.count())
        .where(RiskEvent.ts >= since)
        .group_by(day, RiskEvent.decision, RiskEvent.tier)
    ).all()
    points: dict[str, DayPoint] = {}
    for i in range(SERIES_DAYS + 1):
        d = (since + timedelta(days=i)).date().isoformat()
        points[d] = DayPoint(day=d, auto=0, one_tap=0, otp=0, blocked=0)
    for d_, decision, tier, n in rows:
        key = d_.date().isoformat()
        pt = points.get(key)
        if pt is None:
            continue
        if decision == "BLOCK":
            pt.blocked += n
        elif tier == 3:
            pt.otp += n
        elif tier == 2:
            pt.one_tap += n
        elif tier == 1:
            pt.auto += n

    def fetch(*cond: object, limit: int) -> list[EventRow]:
        q = (
            select(RiskEvent, Deal.reference)
            .outerjoin(Deal, Deal.id == RiskEvent.deal_id)
            .where(*cond)  # type: ignore[arg-type]
            .order_by(RiskEvent.ts.desc())
            .limit(limit)
        )
        return [_row(e, ref) for e, ref in db.execute(q).all()]

    return OverviewOut(
        counters=counters,
        series=list(points.values()),
        latest_blocked=fetch(RiskEvent.decision == "BLOCK", limit=10),
        recent=fetch(limit=25),
    )
