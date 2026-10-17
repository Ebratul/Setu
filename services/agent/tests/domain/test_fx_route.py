"""FR-7 route comparison: golden example on the DEMO_TODAY mid rates, invariants, guards."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.fx import FxQuote, FxTable
from app.domain.fx_route import compare_routes
from app.domain.money import Money, q2

DAY = date(2026, 10, 20)
FX = FxTable(
    [
        FxQuote("USD", "BDT", Decimal("122.59"), DAY, "MOCK"),
        FxQuote("USD", "CNY", Decimal("7.099"), DAY, "MOCK"),
        FxQuote("CNY", "BDT", Decimal("17.2686"), DAY, "MOCK"),
    ]
)


def test_golden_usd_invoice_cheaper_in_cny() -> None:
    r = compare_routes(Money(Decimal("5760"), "USD"), "BDT", FX)
    assert q2(r.supplier_receives.amount) == Decimal("40890.24")
    assert r.supplier_receives.currency == "CNY"
    assert q2(r.usd_route.total.amount) == Decimal("718223.24")
    assert q2(r.cny_route.total.amount) == Decimal("712766.14")
    assert r.cheaper == "CNY"
    assert q2(r.saving.amount) == Decimal("5457.10")
    assert q2(r.saving_pct) == Decimal("0.76")


def test_totals_are_conversion_plus_fees_and_saving_is_difference() -> None:
    r = compare_routes(Money(Decimal("12345.67"), "CNY"), "BDT", FX)
    for route in (r.usd_route, r.cny_route):
        assert route.total == route.conversion + route.fees
    dear = max(r.usd_route.total.amount, r.cny_route.total.amount)
    cheap = min(r.usd_route.total.amount, r.cny_route.total.amount)
    assert r.saving.amount == dear - cheap >= 0
    assert r.cny_route.sent == Money(Decimal("12345.67"), "CNY")


def test_usd_route_sends_more_usd_than_mid_value() -> None:
    r = compare_routes(Money(Decimal("1000"), "USD"), "BDT", FX)
    assert r.usd_route.sent.currency == "USD"
    assert r.usd_route.sent.amount > Decimal("1000")  # covers the supplier-side conversion spread


@pytest.mark.parametrize(
    "invoice", [Money(Decimal("0"), "USD"), Money(Decimal("-1"), "CNY"), Money(Decimal("5"), "BDT")]
)
def test_rejects_bad_invoices(invoice: Money) -> None:
    with pytest.raises(ValueError):
        compare_routes(invoice, "BDT", FX)
