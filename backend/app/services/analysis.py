"""FR-3 analysis service: loads rows with SQLAlchemy, computes with app/domain only, shapes API
models. Read-only; nothing here writes to the database."""

import contextlib
import uuid
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, can_read_party
from app.db.enums import DealStatus, FxKind, PartyKind
from app.db.models import Deal, DealCost, FxRate, Party, SupplierScore
from app.domain import narrative
from app.domain.fx import FxQuote, FxRateMissing, FxTable
from app.domain.landed_cost import CostLine, LandedCostResult, landed_cost
from app.domain.margin import (
    MarginResult,
    break_even_price,
    gross_margin,
    margin_band,
    pct,
    price_for_margin,
)
from app.domain.money import CURRENCIES, Currency, Money, q2
from app.domain.scorecard import ScoreMonth, SupplierDeal, supplier_scorecard
from app.domain.summary import (
    DealMonthInput,
    MonthTotals,
    add_months,
    month_start,
    monthly_summary,
)
from app.errors import DomainError, Forbidden, NotFound, ServiceUnavailable
from app.schemas.analysis import (
    Amounts,
    CostDriverOut,
    CostLineOut,
    DealSummary,
    Explanation,
    FxRateOut,
    LandedCostRequest,
    MonthlyChange,
    MonthlyDeal,
    MonthlySummaryOut,
    MonthTotalsOut,
    OrderAnalysis,
    OrderList,
    ScorePoint,
    SupplierScorecardOut,
    SupplierScoreOut,
    TargetPrice,
)
from app.services.scope import demo_today, party, require_buyer, scope_party

FX_PAIRS: tuple[tuple[Currency, Currency], ...] = (("USD", "BDT"), ("USD", "CNY"), ("CNY", "BDT"))
COMMITTED = (
    DealStatus.FUNDED,
    DealStatus.IN_PRODUCTION,
    DealStatus.SHIPPED,
    DealStatus.ARRIVED,
    DealStatus.COMPLETED,
    DealStatus.DISPUTED,
)
SCORE_WINDOW_MONTHS = 6
HUNDRED = Decimal("100")
Q4 = Decimal("0.0001")


# ---------- formatting at the API boundary ----------


def fmt(value: Decimal) -> str:
    return f"{q2(value)}"


def fmt_unit(value: Decimal) -> str:
    """Per-unit amounts: up to 4 dp, at least 2 (1.4 → '1.40', 0.04594 → '0.0459')."""
    q = value.quantize(Q4, rounding=ROUND_HALF_UP)
    s = f"{q}".rstrip("0")
    whole, _, frac = s.partition(".")
    return f"{whole}.{frac.ljust(2, '0')}"


def fmt_qty(value: Decimal) -> str:
    return f"{value.normalize():f}"


def amounts(m: Money, fx: FxTable, per_unit: bool = False) -> Amounts:
    f = fmt_unit if per_unit else fmt
    vals = {c: f(fx.convert(m, c).amount) for c in CURRENCIES}
    return Amounts(USD=vals["USD"], BDT=vals["BDT"], CNY=vals["CNY"])


def fx_out(quotes: Sequence[FxQuote]) -> list[FxRateOut]:
    return [
        FxRateOut(base=q.base, quote=q.quote, rate=f"{q.rate}", as_of=q.as_of, source=q.source)
        for q in quotes
    ]


def explanations(sentences: Sequence[narrative.Sentence]) -> list[Explanation]:
    return [Explanation(code=s.code, en=s.en, bn=s.bn) for s in sentences]


# ---------- loading ----------


def fx_table(db: Session, on: date) -> FxTable:
    """Latest HISTORY (not forecast) rate per pair on or before `on`."""
    quotes = []
    for base, quote in FX_PAIRS:
        row = db.scalars(
            select(FxRate)
            .where(
                FxRate.base == base,
                FxRate.quote == quote,
                FxRate.kind == FxKind.HISTORY,
                FxRate.as_of <= on,
            )
            .order_by(FxRate.as_of.desc())
            .limit(1)
        ).first()
        if row is not None:
            quotes.append(FxQuote(base, quote, row.rate.normalize(), row.as_of, row.source))
    if not quotes:
        raise ServiceUnavailable("no FX rates are loaded; run the demo seed")
    return FxTable(quotes)


def used_quotes(fx: FxTable, currency: Currency) -> list[FxQuote]:
    seen: dict[tuple[str, str], FxQuote] = {}
    for target in CURRENCIES:
        try:
            for q in fx.path(currency, target):
                seen[(q.base, q.quote)] = q
        except FxRateMissing as exc:
            raise ServiceUnavailable(f"missing FX rate for {currency}/{target}") from exc
    return list(seen.values())


def find_deal(db: Session, ref_or_id: str) -> Deal:
    cond = Deal.reference == ref_or_id
    with contextlib.suppress(ValueError):
        cond = cond | (Deal.id == uuid.UUID(ref_or_id))
    deal = db.scalars(select(Deal).where(cond)).first()
    if deal is None:
        raise NotFound(f"deal {ref_or_id} not found")
    return deal


def deal_summary(db: Session, deal: Deal) -> DealSummary:
    buyer, supplier = party(db, deal.buyer_id), party(db, deal.supplier_id)
    return DealSummary(
        id=deal.id,
        reference=deal.reference,
        title=deal.title,
        status=deal.status,
        buyer_name=buyer.legal_name,
        supplier_id=supplier.id,
        supplier_name=supplier.legal_name,
        supplier_kyb_status=supplier.kyb_status,
        hs_code=deal.hs_code,
        incoterm=deal.incoterm,
        quantity=fmt_qty(deal.quantity),
        unit=deal.unit,
        unit_price=fmt_unit(deal.unit_price),
        currency=cast(Currency, deal.currency),
        goods_value=fmt(deal.goods_value),
        opened_on=deal.opened_on,
    )


def deal_figures(
    db: Session, deal: Deal, fx: FxTable, currency: Currency | None = None
) -> tuple[LandedCostResult, MarginResult | None]:
    """Landed cost and margin of a stored deal, in `currency` (default: the deal currency)."""
    ccy = currency or cast(Currency, deal.currency)
    costs = db.scalars(select(DealCost).where(DealCost.deal_id == deal.id)).all()
    goods = fx.convert(Money(deal.goods_value, cast(Currency, deal.currency)), ccy)
    lines = [
        CostLine(c.kind, fx.convert(Money(c.amount, cast(Currency, c.currency)), ccy), c.note)
        for c in sorted(costs, key=lambda c: list(narrative.COST_LABELS).index(c.kind))
    ]
    lc = landed_cost(goods, deal.quantity, lines)
    margin = None
    if deal.expected_sale_value is not None:
        revenue = fx.convert(Money(deal.expected_sale_value, cast(Currency, deal.currency)), ccy)
        margin = gross_margin(revenue, lc.total)
    return lc, margin


# ---------- order analysis ----------


def build_analysis(
    lc: LandedCostResult,
    margin: MarginResult | None,
    unit: str,
    fx: FxTable,
    deal: DealSummary | None,
    target_margin_pct: Decimal | None,
) -> OrderAnalysis:
    ccy = lc.total.currency
    quotes = used_quotes(fx, ccy)
    selling = Money(margin.revenue.amount / lc.quantity, ccy) if margin is not None else None
    target = None
    if target_margin_pct is not None:
        frac = target_margin_pct / HUNDRED
        if not Decimal(0) <= frac < 1:
            raise DomainError("target margin must be between 0 and 100%")
        price = price_for_margin(lc.total, lc.quantity, frac)
        target = TargetPrice(
            margin_pct=fmt(target_margin_pct),
            price_per_unit=amounts(price, fx, per_unit=True),
            revenue=amounts(price * lc.quantity, fx),
        )
    sentences = narrative.order_sentences(lc, margin, unit, selling, quotes)
    return OrderAnalysis(
        deal=deal,
        currency=ccy,
        quantity=fmt_qty(lc.quantity),
        unit=unit,
        breakdown=[
            CostLineOut(
                kind=line.kind,  # type: ignore[arg-type]
                label=line.label,
                amount=amounts(line.amount, fx),
                share_pct=fmt(line.share * HUNDRED),
            )
            for line in lc.lines
        ],
        goods_value=amounts(lc.goods, fx),
        extra_costs=amounts(lc.extras, fx),
        landed_cost=amounts(lc.total, fx),
        cost_per_unit=amounts(lc.per_unit, fx, per_unit=True),
        expected_revenue=amounts(margin.revenue, fx) if margin else None,
        selling_price_per_unit=amounts(selling, fx, per_unit=True) if selling else None,
        gross_margin=amounts(margin.gross_profit, fx) if margin else None,
        gross_margin_pct=fmt(pct(margin.margin)) if margin and margin.margin is not None else None,
        markup_pct=fmt(pct(margin.markup)) if margin and margin.markup is not None else None,
        margin_band=margin_band(margin.margin) if margin else None,
        break_even_price_per_unit=amounts(break_even_price(lc.total, lc.quantity), fx, True),
        target=target,
        fx=fx_out(quotes),
        explanations=explanations(sentences),
        facts=[*lc.facts, *(margin.facts if margin else ())],
    )


def authorize_deal(user: CurrentUser, deal: Deal) -> None:
    if not can_read_party(user, deal.buyer_id):
        raise Forbidden("this deal belongs to another buyer")


def order_analysis(
    db: Session, user: CurrentUser, ref_or_id: str, target_margin_pct: Decimal | None = None
) -> OrderAnalysis:
    deal = find_deal(db, ref_or_id)
    authorize_deal(user, deal)
    fx = fx_table(db, demo_today(db))
    lc, margin = deal_figures(db, deal, fx)
    return build_analysis(lc, margin, deal.unit, fx, deal_summary(db, deal), target_margin_pct)


def what_if(db: Session, req: LandedCostRequest) -> OrderAnalysis:
    ccy: Currency = req.currency
    fx = fx_table(db, demo_today(db))
    qty = Decimal(req.quantity)
    lc = landed_cost(
        Money(Decimal(req.goods_value), ccy),
        qty,
        [CostLine(c.kind, Money(Decimal(c.amount), ccy), c.label) for c in req.cost_lines],
    )
    margin = None
    if req.selling_price_per_unit is not None:
        margin = gross_margin(Money(Decimal(req.selling_price_per_unit) * qty, ccy), lc.total)
    target = Decimal(req.target_margin_pct) if req.target_margin_pct is not None else None
    return build_analysis(lc, margin, req.unit, fx, None, target)


def list_orders(db: Session, user: CurrentUser) -> OrderList:
    stmt = select(Deal).order_by(Deal.opened_on.desc(), Deal.reference)
    if not user.reads_all:
        stmt = stmt.where(Deal.buyer_id == user.party_id)
    return OrderList(orders=[deal_summary(db, d) for d in db.scalars(stmt).all()])


# ---------- monthly summary ----------


def monthly(
    db: Session, user: CurrentUser, party_id: uuid.UUID | None, month: str | None
) -> MonthlySummaryOut:
    buyer = require_buyer(db, user, party_id)
    today = demo_today(db)
    target = date(int(month[:4]), int(month[5:7]), 1) if month else month_start(today)
    fx = fx_table(db, today)
    ccy = cast(Currency, buyer.cash_currency or "USD")
    deals = db.scalars(
        select(Deal)
        .where(Deal.buyer_id == buyer.id, Deal.status.in_(COMMITTED))
        .order_by(Deal.opened_on, Deal.reference)
    ).all()
    figures = {d.id: deal_figures(db, d, fx, ccy) for d in deals}
    inputs = [DealMonthInput(d.reference, month_start(d.opened_on), *figures[d.id]) for d in deals]
    s = monthly_summary(target, inputs, ccy)

    def totals(t: MonthTotals) -> MonthTotalsOut:
        return MonthTotalsOut(
            month=f"{t.month:%Y-%m}",
            deals_count=t.deals_count,
            total_purchases=amounts(t.purchases, fx),
            total_landed_cost=amounts(t.landed, fx),
            expected_revenue=amounts(t.revenue, fx),
            average_margin_pct=fmt(pct(t.average_margin)) if t.average_margin is not None else None,
        )

    cur = totals(s.current)
    driver = s.top_cost_driver
    month_deals = [d for d in deals if month_start(d.opened_on) == s.current.month]
    return MonthlySummaryOut(
        party_id=buyer.id,
        party_name=buyer.legal_name,
        month=cur.month,
        currency=ccy,
        deals_count=cur.deals_count,
        total_purchases=cur.total_purchases,
        total_landed_cost=cur.total_landed_cost,
        expected_revenue=cur.expected_revenue,
        average_margin_pct=cur.average_margin_pct,
        top_cost_driver=CostDriverOut(
            kind=driver.kind,  # type: ignore[arg-type]
            amount=amounts(driver.amount, fx),
            share_pct=fmt(driver.share_of_extras * HUNDRED),
        )
        if driver
        else None,
        previous=totals(s.previous),
        change=MonthlyChange(
            purchases_delta=amounts(s.purchases_change, fx),
            purchases_pct=fmt(s.purchases_change_ratio * HUNDRED)
            if s.purchases_change_ratio is not None
            else None,
            deals_delta=s.current.deals_count - s.previous.deals_count,
            margin_delta_pts=fmt(s.margin_change_pts * HUNDRED)
            if s.margin_change_pts is not None
            else None,
        ),
        history=[totals(t) for t in s.history],
        deals=[
            MonthlyDeal(
                reference=d.reference,
                title=d.title,
                supplier_name=party(db, d.supplier_id).legal_name,
                status=d.status,
                landed_cost=amounts(figures[d.id][0].total, fx),
                gross_margin_pct=fmt(pct(m.margin))
                if (m := figures[d.id][1]) is not None and m.margin is not None
                else None,
            )
            for d in month_deals
        ],
        insights=explanations(narrative.monthly_sentences(s)),
        fx=fx_out(used_quotes(fx, ccy)),
        facts=list(s.facts),
    )


# ---------- supplier scorecard ----------


def suppliers(db: Session, user: CurrentUser, party_id: uuid.UUID | None) -> SupplierScorecardOut:
    buyer = scope_party(db, user, party_id)
    today = demo_today(db)
    fx = fx_table(db, today)
    since = add_months(month_start(today), -SCORE_WINDOW_MONTHS)
    out = []
    for sup in db.scalars(
        select(Party).where(Party.kind == PartyKind.SUPPLIER).order_by(Party.legal_name)
    ).all():
        months = [
            ScoreMonth(
                r.month,
                r.deals_count,
                r.on_time_rate,
                r.defect_rate,
                r.doc_mismatch_count,
                r.dispute_count,
                r.score,
            )
            for r in db.scalars(
                select(SupplierScore).where(
                    SupplierScore.supplier_id == sup.id, SupplierScore.month >= since
                )
            ).all()
        ]
        deals = db.scalars(
            select(Deal).where(Deal.supplier_id == sup.id, Deal.status.in_(COMMITTED))
        ).all()
        supplier_deals = []
        for d in deals:
            lc, _ = deal_figures(db, d, fx, "USD")
            supplier_deals.append(
                SupplierDeal(lc.goods, lc.total, d.status == DealStatus.COMPLETED)
            )
        card = supplier_scorecard(months, supplier_deals, sup.kyb_status)
        yours = 0
        if buyer is not None:
            yours = (
                db.scalar(
                    select(func.count())
                    .select_from(Deal)
                    .where(
                        Deal.supplier_id == sup.id,
                        Deal.buyer_id == buyer.id,
                        Deal.status != DealStatus.CANCELLED,
                    )
                )
                or 0
            )

        def p(x: Decimal | None) -> str | None:
            return fmt(pct(x)) if x is not None else None

        out.append(
            SupplierScoreOut(
                supplier_id=sup.id,
                code=sup.code,
                name=sup.legal_name,
                city=sup.city,
                country=sup.country,
                kyb_status=sup.kyb_status,
                score=fmt(card.score) if card.score is not None else None,
                score_trend=[
                    ScorePoint(month=f"{m:%Y-%m}", score=fmt(s)) for m, s in card.score_trend
                ],
                on_time_rate_pct=p(card.on_time_rate),
                dispute_rate_pct=p(card.dispute_rate),
                defect_rate_pct=p(card.defect_rate),
                doc_mismatch_count=card.doc_mismatch_count,
                deals_count=card.deals_count,
                completed_deals_count=card.completed_deals,
                your_deals_count=yours,
                price_index=fmt(card.price_index) if card.price_index is not None else None,
                flags=list(card.flags),
                weak=card.weak,
                notes=explanations(narrative.supplier_sentences(card)),
            )
        )
    out.sort(key=lambda s: (s.score is None, -Decimal(s.score or "0"), s.name))
    return SupplierScorecardOut(
        party_id=buyer.id if buyer else None,
        window_months=SCORE_WINDOW_MONTHS,
        suppliers=out,
        facts=[
            f"window = {SCORE_WINDOW_MONTHS} months from {since:%Y-%m}; scores are network-wide",
            "price index = 100 × Σ landed cost / Σ goods value of committed deals (USD)",
            "weak = KYB not verified, score < 70, dispute rate > 10% or on-time rate < 80%",
        ],
    )
