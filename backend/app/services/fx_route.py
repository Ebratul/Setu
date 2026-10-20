"""FR-7 route comparison for one payment, using today's recorded MOCK mid rates."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.fx_route import ASSUMPTIONS, RouteComparison, RouteCost, compare_routes
from app.domain.money import Currency, Money, q2
from app.schemas.cards import FxCompareData, Route
from app.services.analysis import fmt, fx_table
from app.services.scope import demo_today

RATE_DP = Decimal("0.0001")


def _route(r: RouteCost) -> Route:
    return Route(
        route=r.route,  # type: ignore[arg-type]
        sent=fmt(r.sent.amount),
        sent_currency=r.sent.currency,  # type: ignore[arg-type]
        rate_used=str(r.rate_used.quantize(RATE_DP)),
        conversion=fmt(r.conversion.amount),
        fees=fmt(r.fees.amount),
        total=fmt(r.total.amount),
    )


def compare(
    db: Session, invoice: Money, payer: Currency, basis: str
) -> tuple[RouteComparison, FxCompareData]:
    today = demo_today(db)
    cmp = compare_routes(invoice, payer, fx_table(db, today))
    data = FxCompareData(
        basis=basis,
        invoice_amount=fmt(invoice.amount),
        invoice_currency=invoice.currency,  # type: ignore[arg-type]
        payer_currency=payer,
        supplier_receives_cny=fmt(cmp.supplier_receives.amount),
        usd_route=_route(cmp.usd_route),
        cny_route=_route(cmp.cny_route),
        cheaper=cmp.cheaper,  # type: ignore[arg-type]
        saving=fmt(cmp.saving.amount),
        saving_pct=str(q2(cmp.saving_pct)),
        as_of=today,
        assumptions=list(ASSUMPTIONS),
    )
    return cmp, data
