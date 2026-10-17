"""Tier 0 finance tools (P09). Read-only or simulate-only: nothing is saved and no money moves.

Each tool checks buyer isolation, calls a deterministic service (no math here), and returns a
result card {card_type, data, explanation_codes, explanation_en, explanation_bn, simulated}.
Deals are resolved as: explicit `deal_id` → the chat's deal scope → the most recent active deal
(`defaulted_deal=true`, so the answer can say which one was used).
"""

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal, cast
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.persistence import resolve_deal
from app.agent.registry import ToolContext, ToolError
from app.agent.tools.readonly import REGISTRY
from app.db.enums import DealStatus
from app.db.models import Deal, Milestone
from app.domain.money import Money
from app.errors import NotFound
from app.schemas.analysis import CostLineIn, InDec, LandedCostRequest, OrderAnalysis
from app.schemas.cards import (
    APP_ROUTE_PATTERN,
    AlertItem,
    AlertsCard,
    AlertsData,
    Bilingual,
    CashflowCard,
    CashflowData,
    CashflowSide,
    CostLine,
    FinancingComparisonCard,
    FinancingComparisonData,
    FinancingOptionItem,
    FxCompareCard,
    LandedCostCard,
    LandedCostData,
    MonthlySummaryCard,
    MonthlySummaryData,
    MonthPoint,
    Payment,
    Point,
    Recommendation,
    ScorecardCard,
    ScorecardData,
    Shortfall,
    SupplierItem,
)
from app.schemas.cashflow import ForecastOut, LoanIn, MoveIn, ScenarioRequest
from app.schemas.financing import ImpactRequest, MatchRequest
from app.security.tiers import Tier
from app.services import alerts as alert_service
from app.services import analysis, cashflow, financing, fx_route, scenario
from app.services.scope import demo_today

ACTIVE = (
    DealStatus.DRAFT,
    DealStatus.PROPOSED,
    DealStatus.CONFIRMED,
    DealStatus.FUNDED,
    DealStatus.IN_PRODUCTION,
    DealStatus.SHIPPED,
    DealStatus.ARRIVED,
)
OPEN_MILESTONES = ("PROPOSED", "PENDING", "READY", "PENDING_APPROVAL", "FROZEN")
UPCOMING_DAYS = 30
UPCOMING_MAX = 5
APP_ROUTE_RE = re.compile(APP_ROUTE_PATTERN)
OptionId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
DealId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _db(ctx: ToolContext):  # type: ignore[no-untyped-def]
    if ctx.db is None:
        raise ToolError("unavailable", "database is not available")
    return ctx.db


def pick_deal(ctx: ToolContext, deal_id: str | None) -> tuple[Deal, bool]:
    """(deal, defaulted). Another buyer's deal looks missing (no existence oracle)."""
    db = _db(ctx)
    ref = deal_id or ctx.deal_ref
    if ref:
        try:
            return resolve_deal(db, ctx.user, ref), False
        except NotFound as exc:
            raise ToolError("not_found", "deal not found") from exc
    if ctx.user.party_id is None:
        raise ToolError("needs_deal", "say which deal (e.g. SETU-2026-0001)")
    deal = db.scalars(
        select(Deal)
        .where(Deal.buyer_id == ctx.user.party_id, Deal.status.in_(ACTIVE))
        # In-flight deals (funded, in production, shipped) before drafts, newest first.
        .order_by(
            Deal.status.in_((DealStatus.DRAFT, DealStatus.PROPOSED, DealStatus.CONFIRMED)).asc(),
            Deal.opened_on.desc(),
        )
    ).first()
    if deal is None:
        raise ToolError("needs_deal", "no active deal found; ask which deal")
    return deal, True


def _financing_deal(ctx: ToolContext, deal_id: str | None, mode: str) -> tuple[str | None, bool]:
    """Shortfall mode without a deal: None, so the service picks the deal behind the first
    shortfall. Otherwise the usual deal resolution."""
    if not deal_id and not ctx.deal_ref and mode == "shortfall":
        return None, True
    deal, defaulted = pick_deal(ctx, deal_id)
    return deal.reference, defaulted


def _m(amount: str | None) -> str:
    """Display format for explanation sentences: 1560.00 → 1,560.00."""
    return f"{Decimal(amount):,.2f}" if amount is not None else ""


def _safe_route(route: str | None, query: dict[str, str] | None = None) -> str | None:
    """Internal /app routes only (the pattern the card model enforces); others are dropped."""
    if not route:
        return None
    url = route + (f"?{urlencode(query)}" if query else "")
    return url if APP_ROUTE_RE.fullmatch(url) else None


def _bi(code: str, en: str, bn: str) -> Bilingual:
    return Bilingual(code=code, en=en, bn=bn)


# --- 1/2. landed cost -----------------------------------------------------------------------


def _landed_card(oa: OrderAnalysis, defaulted: bool) -> LandedCostCard:
    ccy = oa.currency

    def pick(a):  # type: ignore[no-untyped-def]
        return getattr(a, ccy) if a is not None else None

    ref = oa.deal.reference if oa.deal else None
    first = oa.explanations[0] if oa.explanations else None
    margin = next((e for e in oa.explanations if e.code == "GROSS_MARGIN"), first)
    return LandedCostCard(
        data=LandedCostData(
            deal_ref=ref,
            title=oa.deal.title if oa.deal else None,
            defaulted_deal=defaulted,
            currency=ccy,
            quantity=oa.quantity,
            unit=oa.unit,
            lines=[
                CostLine(kind=b.kind, label=b.label, amount=pick(b.amount), share_pct=b.share_pct)
                for b in oa.breakdown
            ],
            goods_value=pick(oa.goods_value),
            extra_costs=pick(oa.extra_costs),
            landed_cost=pick(oa.landed_cost),
            landed_cost_bdt=oa.landed_cost.BDT,
            cost_per_unit=pick(oa.cost_per_unit),
            selling_price_per_unit=pick(oa.selling_price_per_unit),
            expected_revenue=pick(oa.expected_revenue),
            gross_margin=pick(oa.gross_margin),
            gross_margin_pct=oa.gross_margin_pct,
            margin_band=oa.margin_band,
            break_even_price_per_unit=pick(oa.break_even_price_per_unit),
            analysis_route=_safe_route(f"/app/orders/{ref}/analysis") if ref else None,
        ),
        explanation_codes=[e.code for e in oa.explanations],
        explanation_en=margin.en if margin else "",
        explanation_bn=margin.bn if margin else "",
    )


class AnalyzeOrderIn(_In):
    deal_id: DealId | None = Field(None, description="Deal reference, e.g. SETU-2026-0001.")


@REGISTRY.tool(
    name="analyze_order",
    tier=Tier.T0,
    args_schema=AnalyzeOrderIn,
    output_schema=LandedCostCard,
    tags=("analysis",),
)
def analyze_order(args: AnalyzeOrderIn, ctx: ToolContext) -> LandedCostCard:
    """Landed cost of one order: cost breakdown, total, cost per unit, gross margin and
    break-even price. Without deal_id it uses the chat's deal or the most recent active deal."""
    deal, defaulted = pick_deal(ctx, args.deal_id)
    return _landed_card(analysis.order_analysis(_db(ctx), ctx.user, deal.reference), defaulted)


class CostLineArg(_In):
    kind: Literal["FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER"]
    amount: InDec
    label: Annotated[str | None, Field(max_length=60)] = None


class WhatIfIn(_In):
    goods_value: InDec
    quantity: InDec
    unit: Annotated[str, Field(min_length=1, max_length=8, pattern=r"^[A-Za-z]+$")] = "pcs"
    currency: Literal["USD", "BDT", "CNY"] = "USD"
    cost_lines: Annotated[list[CostLineArg], Field(max_length=20)] = []
    selling_price: InDec | None = Field(None, description="Selling price per unit, optional.")


@REGISTRY.tool(
    name="landed_cost_what_if",
    tier=Tier.T0,
    args_schema=WhatIfIn,
    output_schema=LandedCostCard,
    tags=("analysis", "what-if"),
)
def landed_cost_what_if(args: WhatIfIn, ctx: ToolContext) -> LandedCostCard:
    """What-if landed cost for hypothetical numbers (goods value, quantity, extra cost lines,
    optional selling price). Saves nothing."""
    req = LandedCostRequest(
        currency=args.currency,
        goods_value=args.goods_value,
        quantity=args.quantity,
        unit=args.unit,
        cost_lines=[
            CostLineIn(kind=c.kind, amount=c.amount, label=c.label) for c in args.cost_lines
        ],
        selling_price_per_unit=args.selling_price,
    )
    return _landed_card(analysis.what_if(_db(ctx), req), False)


# --- 3/4/7. cash flow -----------------------------------------------------------------------


def _side(fc: ForecastOut) -> CashflowSide:
    return CashflowSide(
        series=[Point(on=d.on, closing=d.closing) for d in fc.daily],
        first_shortfall=Shortfall(on=fc.first_shortfall.on, amount=fc.first_shortfall.amount)
        if fc.first_shortfall
        else None,
        lowest_balance=fc.lowest_balance,
        lowest_on=fc.lowest_on,
    )


def _upcoming(fc: ForecastOut) -> list[Payment]:
    horizon = fc.start + timedelta(days=UPCOMING_DAYS)
    outs = [
        (Decimal(i.amount), i)
        for d in fc.daily
        if d.on < horizon
        for i in d.items
        if i.direction == "OUT"
    ]
    biggest = sorted(outs, key=lambda x: (-x[0], x[1].on))[:UPCOMING_MAX]
    return [
        Payment(on=i.on, label=i.label, kind=i.kind, amount=i.amount, deal_ref=i.deal_ref)
        for _, i in sorted(biggest, key=lambda x: x[1].on)
    ]


def _shortfall_text(side: CashflowSide, ccy: str) -> tuple[list[str], str, str]:
    sf = side.first_shortfall
    if sf is None:
        return (
            ["NO_SHORTFALL"],
            f"Your balance stays above the buffer; the lowest point is {ccy} "
            f"{_m(side.lowest_balance)} on {side.lowest_on}.",
            f"আপনার ব্যালেন্স buffer-এর ওপরে থাকে; সর্বনিম্ন {ccy} {_m(side.lowest_balance)}, "
            f"{side.lowest_on} তারিখে।",
        )
    return (
        ["FIRST_SHORTFALL", "LOWEST_BALANCE"],
        f"Your cash first falls short on {sf.on} by {ccy} {_m(sf.amount)}, when a scheduled "
        "payment is larger than your balance.",
        f"{sf.on} তারিখে প্রথম cash কম পড়বে — {ccy} {_m(sf.amount)}, কারণ ওই দিনের নির্ধারিত "
        "পেমেন্ট আপনার ব্যালেন্সের চেয়ে বেশি।",
    )


def _cash_card(
    fc: ForecastOut, after: CashflowSide | None = None, label: str | None = None
) -> CashflowCard:
    before = _side(fc)
    codes, en, bn = _shortfall_text(after or before, fc.currency)
    if after is not None:
        was = before.first_shortfall
        now = after.first_shortfall
        if was and (now is None or now.on != was.on):
            codes = ["SHORTFALL_CLEARED", *codes]
            amount = _m(was.amount)
            en = (
                f"With this change the {fc.currency} {amount} shortfall on {was.on} goes away. "
                + en
            )
            bn = f"এই পরিবর্তনে {was.on} তারিখের {fc.currency} {amount} ঘাটতি থাকে না। " + bn
    return CashflowCard(
        data=CashflowData(
            currency=fc.currency,
            start=fc.start,
            end=fc.end,
            opening_balance=fc.opening_balance,
            min_buffer=fc.min_buffer,
            before=before,
            after=after,
            scenario_label=label,
            upcoming=_upcoming(fc),
        ),
        explanation_codes=codes,
        explanation_en=en,
        explanation_bn=bn,
    )


class ForecastIn(_In):
    days: Annotated[int, Field(ge=7, le=180)] = 90


@REGISTRY.tool(
    name="forecast_cashflow",
    tier=Tier.T0,
    args_schema=ForecastIn,
    output_schema=CashflowCard,
    tags=("cashflow",),
)
def forecast_cashflow(args: ForecastIn, ctx: ToolContext) -> CashflowCard:
    """Day-by-day cash forecast for the signed-in buyer: balance series, first shortfall (date
    and amount), lowest balance and the biggest payments in the next 30 days."""
    return _cash_card(cashflow.get_forecast(_db(ctx), ctx.user, None, args.days))


class MoveArg(_In):
    ref: Annotated[str, Field(max_length=120, pattern=r"^[A-Za-z0-9:_\-.]+$")]
    on: date


class LoanArg(_In):
    amount: InDec
    on: date
    repay_on: date | None = None
    repay_amount: InDec | None = None


class ScenarioIn(_In):
    moves: Annotated[list[MoveArg], Field(max_length=20)] = []
    removes: Annotated[
        list[Annotated[str, Field(max_length=120, pattern=r"^[A-Za-z0-9:_\-.]+$")]],
        Field(max_length=50),
    ] = []
    loans: Annotated[list[LoanArg], Field(max_length=5)] = []
    days: Annotated[int, Field(ge=7, le=180)] = 90


@REGISTRY.tool(
    name="simulate_cashflow_scenario",
    tier=Tier.T0,
    args_schema=ScenarioIn,
    output_schema=CashflowCard,
    tags=("cashflow", "what-if"),
)
def simulate_cashflow_scenario(args: ScenarioIn, ctx: ToolContext) -> CashflowCard:
    """What-if cash forecast: move payments to other dates (by flow ref), remove flows, or add a
    short loan; returns before/after. Saves nothing."""
    db = _db(ctx)
    base = cashflow.get_forecast(db, ctx.user, None, args.days)
    out = scenario.run(
        db,
        ctx.user,
        ScenarioRequest(
            days=args.days,
            moves=[MoveIn(ref=m.ref, on=m.on) for m in args.moves],
            removes=list(args.removes),
            loans=[
                LoanIn(amount=x.amount, on=x.on, repay_on=x.repay_on, repay_amount=x.repay_amount)
                for x in args.loans
            ],
        ),
    )
    return _cash_card(base, _side(out.forecast), "what-if")


class ImpactIn(_In):
    option_id: OptionId = Field(description="Financing option code or id from match_financing.")
    amount: InDec
    deal_id: DealId | None = None
    mode: Literal["shortfall", "order"] = "shortfall"


@REGISTRY.tool(
    name="financing_impact",
    tier=Tier.T0,
    args_schema=ImpactIn,
    output_schema=CashflowCard,
    tags=("financing", "cashflow"),
)
def financing_impact(args: ImpactIn, ctx: ToolContext) -> CashflowCard:
    """Cash forecast before/after taking one financing option for an amount (inflow and
    repayment simulated; nothing is applied)."""
    db = _db(ctx)
    ref, _ = _financing_deal(ctx, args.deal_id, args.mode)
    imp = financing.impact(
        db,
        ctx.user,
        ImpactRequest(deal_id=ref, option_id=args.option_id, amount=args.amount, mode=args.mode),
    )
    base = cashflow.get_forecast(db, ctx.user, None)
    after = CashflowSide(
        series=[Point(on=p.on, closing=p.after) for p in imp.series],
        first_shortfall=Shortfall(
            on=imp.after.first_shortfall.on, amount=imp.after.first_shortfall.amount
        )
        if imp.after.first_shortfall
        else None,
        lowest_balance=imp.after.lowest_balance,
        lowest_on=imp.after.lowest_on,
    )
    card = _cash_card(base, after, imp.option_code)
    if imp.explanations:
        e = imp.explanations[0]
        card.explanation_codes = [e.code, *card.explanation_codes]
        card.explanation_en, card.explanation_bn = e.en, e.bn
    return card


# --- 5. alerts ------------------------------------------------------------------------------


class AlertsIn(_In):
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] = "OPEN"


SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


@REGISTRY.tool(
    name="get_alerts",
    tier=Tier.T0,
    args_schema=AlertsIn,
    output_schema=AlertsCard,
    tags=("alerts",),
)
def get_alerts(args: AlertsIn, ctx: ToolContext) -> AlertsCard:
    """The buyer's alerts (shortfall, deadlines, FX timing, KYB), most severe first, with a link
    to the page that handles each one."""
    out = alert_service.list_alerts(_db(ctx), ctx.user, None, args.status)
    items = sorted(out.alerts, key=lambda a: (SEVERITY_ORDER.get(a.severity, 9), str(a.due_on)))
    alerts = [
        AlertItem(
            id=a.id,
            type=a.type,
            severity=a.severity,
            title_en=a.title_en,
            title_bn=a.title_bn,
            amount=a.amount,
            currency=a.currency,
            due_on=a.due_on,
            deal_ref=a.deal_ref,
            route=_safe_route(a.action.route, a.action.query) if a.action else None,
        )
        for a in items
    ]
    crit = sum(1 for a in alerts if a.severity == "CRITICAL")
    top = alerts[0] if alerts else None
    return AlertsCard(
        data=AlertsData(status=args.status, count=len(alerts), alerts=alerts),
        explanation_codes=["ALERT_COUNT"] + ([f"TOP_{top.type}"] if top else []),
        explanation_en=f"{len(alerts)} {args.status.lower()} alerts, "
        f"{crit} critical" + (f"; most urgent: {top.title_en}." if top else "."),
        explanation_bn=f"{len(alerts)}টি সতর্কতা, {crit}টি জরুরি"
        + (f"; সবচেয়ে জরুরি: {top.title_bn}।" if top else "।"),
    )


# --- 6. financing ---------------------------------------------------------------------------


class MatchIn(_In):
    deal_id: DealId | None = None
    mode: Literal["shortfall", "order"] = Field(
        "shortfall",
        description="shortfall: cover the first cash shortfall; order: finance the order's gap.",
    )


@REGISTRY.tool(
    name="match_financing",
    tier=Tier.T0,
    args_schema=MatchIn,
    output_schema=FinancingComparisonCard,
    tags=("financing",),
)
def match_financing(args: MatchIn, ctx: ToolContext) -> FinancingComparisonCard:
    """Ranked financing options for a deal (supplier credit, bank import loan, escrow-backed
    loan, ...): total cost, effective annual rate, tenor, eligibility, the recommended pick and
    why. Applying is done by the user on the Financing page, never here."""
    ref, defaulted = _financing_deal(ctx, args.deal_id, args.mode)
    m = financing.match(_db(ctx), ctx.user, MatchRequest(deal_id=ref, mode=args.mode))
    ccy = m.currency
    options = [
        FinancingOptionItem(
            option_id=o.option_id,
            code=o.code,
            name=o.name,
            kind=o.kind,
            rank=o.rank,
            recommended=o.recommended,
            eligible=o.eligible,
            tenor_days=o.tenor_days,
            total_cost=getattr(o.cost.total, ccy),
            effective_annual_rate_pct=o.cost.effective_annual_rate_pct,
            collateral=o.collateral,
            conditions=o.conditions,
            why_not=[_bi(c.code, c.en, c.bn) for c in o.why_not],
        )
        for o in m.options
    ]
    rec = None
    if m.top_pick:
        name = next((o.name for o in m.options if o.code == m.top_pick.code), m.top_pick.code)
        rec = Recommendation(
            code=m.top_pick.code,
            name=name,
            total_cost=getattr(m.top_pick.total_cost, ccy),
            saving_vs_next=getattr(m.top_pick.saving_vs_next, ccy)
            if m.top_pick.saving_vs_next
            else None,
            why_codes=m.top_pick.why_codes,
            reasons=[_bi(s.code, s.en, s.bn) for s in m.top_pick.sentences],
        )
    first = rec.reasons[0] if rec and rec.reasons else None
    return FinancingComparisonCard(
        data=FinancingComparisonData(
            mode=args.mode,
            deal_ref=m.deal.reference,
            defaulted_deal=defaulted,
            currency=ccy,
            amount=getattr(m.amount, ccy),
            needed_by=m.needed_by,
            needed_for_days=m.needed_for_days,
            no_financing_needed=m.no_financing_needed,
            options=options,
            recommended=rec,
            apply_route=cast(
                str, _safe_route("/app/financing", {"deal": m.deal.reference, "mode": args.mode})
            ),
        ),
        explanation_codes=rec.why_codes if rec else ["NO_FINANCING_NEEDED"],
        explanation_en=first.en if first else "No financing is needed for this deal.",
        explanation_bn=first.bn if first else "এই ডিলের জন্য অর্থায়নের দরকার নেই।",
    )


# --- 8. FX route ----------------------------------------------------------------------------


class FxRouteIn(_In):
    amount: InDec | None = Field(
        None, description="Invoice amount; empty = the next unpaid milestone of the deal."
    )
    from_currency: Literal["BDT"] = "BDT"
    to_currency: Literal["USD", "CNY"] | None = Field(
        None, description="Invoice currency (default: the milestone's currency, else USD)."
    )
    deal_id: DealId | None = None


@REGISTRY.tool(
    name="compare_fx_route",
    tier=Tier.T0,
    args_schema=FxRouteIn,
    output_schema=FxCompareCard,
    tags=("fx",),
)
def compare_fx_route(args: FxRouteIn, ctx: ToolContext) -> FxCompareCard:
    """Total BDT cost of paying a Chinese supplier via USD versus directly in CNY (spreads and
    fees included, MOCK assumptions listed) and the saving. Locking a rate is not done here."""
    db = _db(ctx)
    if args.amount is not None:
        invoice = Money(Decimal(args.amount), args.to_currency or "USD")
        basis = "amount given"
    else:
        deal, _ = pick_deal(ctx, args.deal_id)
        ms = db.scalars(
            select(Milestone)
            .where(Milestone.deal_id == deal.id, Milestone.status.in_(OPEN_MILESTONES))
            .where(Milestone.due_on >= demo_today(db))
            .order_by(Milestone.seq)
        ).first()
        if ms is None or ms.currency not in ("USD", "CNY"):
            raise ToolError("needs_amount", "give an amount to compare")
        invoice = Money(ms.amount, cast("Literal['USD', 'CNY']", ms.currency))  # type: ignore[arg-type]
        basis = f"milestone {ms.seq} of {deal.reference}"
    cmp, data = fx_route.compare(db, invoice, args.from_currency, basis)
    cheaper, dearer = (
        (data.cny_route, data.usd_route)
        if cmp.cheaper == "CNY"
        else (data.usd_route, data.cny_route)
    )
    en = (
        f"Paying in {cmp.cheaper} costs BDT {_m(cheaper.total)} vs BDT {_m(dearer.total)} via "
        f"{dearer.route}, saving BDT {_m(data.saving)} ({data.saving_pct}%) after spreads and fees."
    )
    bn = (
        f"{cmp.cheaper}-তে pay করলে খরচ BDT {_m(cheaper.total)}, {dearer.route} route-এ BDT "
        f"{_m(dearer.total)}; spread ও fee ধরে সাশ্রয় BDT {_m(data.saving)} ({data.saving_pct}%)।"
    )
    return FxCompareCard(
        data=data,
        explanation_codes=[f"CHEAPER_{cmp.cheaper}", "SPREADS_AND_FEES"],
        explanation_en=en,
        explanation_bn=bn,
    )


# --- 9. monthly summary ---------------------------------------------------------------------


class MonthlyIn(_In):
    month: Annotated[str | None, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None


@REGISTRY.tool(
    name="get_monthly_summary",
    tier=Tier.T0,
    args_schema=MonthlyIn,
    output_schema=MonthlySummaryCard,
    tags=("analysis", "monthly"),
)
def get_monthly_summary(args: MonthlyIn, ctx: ToolContext) -> MonthlySummaryCard:
    """Month summary for the buyer (default: current month): deals, purchases, landed cost,
    expected revenue, average margin, top cost driver and change vs last month."""
    s = analysis.monthly(_db(ctx), ctx.user, None, args.month)
    ccy = s.currency
    first = s.insights[0] if s.insights else None
    return MonthlySummaryCard(
        data=MonthlySummaryData(
            month=s.month,
            currency=ccy,
            deals_count=s.deals_count,
            total_purchases=getattr(s.total_purchases, ccy),
            total_landed_cost=getattr(s.total_landed_cost, ccy),
            expected_revenue=getattr(s.expected_revenue, ccy),
            average_margin_pct=s.average_margin_pct,
            top_cost_driver=CostLine(
                kind=s.top_cost_driver.kind,
                label=None,
                amount=getattr(s.top_cost_driver.amount, ccy),
                share_pct=s.top_cost_driver.share_pct,
            )
            if s.top_cost_driver
            else None,
            purchases_delta=getattr(s.change.purchases_delta, ccy),
            purchases_pct=s.change.purchases_pct,
            margin_delta_pts=s.change.margin_delta_pts,
            history=[
                MonthPoint(month=h.month, total_landed_cost=getattr(h.total_landed_cost, ccy))
                for h in s.history
            ],
            insights=[_bi(i.code, i.en, i.bn) for i in s.insights],
        ),
        explanation_codes=[i.code for i in s.insights],
        explanation_en=first.en if first else f"{s.deals_count} deals in {s.month}.",
        explanation_bn=first.bn if first else f"{s.month}-এ {s.deals_count}টি ডিল।",
    )


# --- 10. supplier scorecard -----------------------------------------------------------------


class ScorecardIn(_In):
    pass


@REGISTRY.tool(
    name="get_supplier_scorecard",
    tier=Tier.T0,
    args_schema=ScorecardIn,
    output_schema=ScorecardCard,
    tags=("analysis", "suppliers"),
)
def get_supplier_scorecard(args: ScorecardIn, ctx: ToolContext) -> ScorecardCard:
    """Supplier scorecard: score, on-time %, dispute %, defect %, document mismatches, KYB
    status and warning flags for each supplier."""
    out = analysis.suppliers(_db(ctx), ctx.user, None)
    items = [
        SupplierItem(
            code=s.code,
            name=s.name,
            country=s.country,
            kyb_status=s.kyb_status,
            score=s.score,
            on_time_rate_pct=s.on_time_rate_pct,
            dispute_rate_pct=s.dispute_rate_pct,
            defect_rate_pct=s.defect_rate_pct,
            doc_mismatch_count=s.doc_mismatch_count,
            your_deals_count=s.your_deals_count,
            weak=s.weak,
            flags=s.flags,
        )
        for s in out.suppliers
    ]
    weak = [s for s in items if s.weak]
    best = next((s for s in items if not s.weak and s.score is not None), None)
    en = (f"Best: {best.name} ({best.score}). " if best else "") + (
        f"Watch: {', '.join(s.name for s in weak)}." if weak else "No supplier is flagged."
    )
    bn = (f"সেরা: {best.name} ({best.score})। " if best else "") + (
        f"সতর্ক থাকুন: {', '.join(s.name for s in weak)}।" if weak else "কোনো সাপ্লায়ার flagged নয়।"
    )
    return ScorecardCard(
        data=ScorecardData(window_months=out.window_months, suppliers=items),
        explanation_codes=(["BEST_SUPPLIER"] if best else []) + (["WEAK_SUPPLIER"] if weak else []),
        explanation_en=en,
        explanation_bn=bn,
    )
