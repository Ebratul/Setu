from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.margin import (
    break_even_price,
    gross_margin,
    margin_band,
    pct,
    price_for_margin,
)
from app.domain.money import D, Money, q2


def test_golden_setu_2026_0001() -> None:
    """(13,660 - 11,200) / 13,660 = 2,460 / 13,660 = 18.0088%  -> 18.01%
    markup = 2,460 / 11,200 = 21.9643% -> 21.96%; break-even = 11,200 / 8,000 = 1.40
    price for a 20% margin = 1.40 / 0.80 = 1.75"""
    m = gross_margin(Money.of("13660.00", "USD"), Money.of("11200.00", "USD"))
    assert m.gross_profit == Money.of("2460.00", "USD")
    assert m.margin is not None and pct(m.margin) == D("18.01")
    assert m.markup is not None and pct(m.markup) == D("21.96")
    assert margin_band(m.margin) == "healthy"
    cost = Money.of("11200.00", "USD")
    assert break_even_price(cost, D("8000")).amount == D("1.4")
    assert q2(price_for_margin(cost, D("8000"), D("0.20")).amount) == D("1.75")


@pytest.mark.parametrize(
    ("margin", "band"),
    [
        (D("0.15"), "healthy"),
        (D("0.149950"), "healthy"),  # shows as 15.00%
        (D("0.149949"), "thin"),  # shows as 14.99%
        (D("0.08"), "thin"),
        (D("0.0799"), "low"),
        (D("-0.2"), "low"),
        (None, None),
    ],
)
def test_band_boundaries(margin: Decimal | None, band: str | None) -> None:
    assert margin_band(margin) == band


def test_zero_revenue_and_zero_cost() -> None:
    m = gross_margin(Money.of("0", "USD"), Money.of("10", "USD"))
    assert m.margin is None and m.markup is not None
    m = gross_margin(Money.of("10", "USD"), Money.of("0", "USD"))
    assert m.markup is None and m.margin == D("1")


@pytest.mark.parametrize("target", [D("1"), D("1.5"), D("-0.01")])
def test_target_margin_out_of_range(target: Decimal) -> None:
    with pytest.raises(ValueError):
        price_for_margin(Money.of("10", "USD"), D("1"), target)


@given(
    cost=st.decimals(min_value="0.01", max_value=10**8, places=2),
    qty=st.decimals(min_value=1, max_value=10**6, places=0),
    target=st.decimals(min_value=0, max_value="0.95", places=4),
)
def test_price_for_margin_round_trips(cost: Decimal, qty: Decimal, target: Decimal) -> None:
    price = price_for_margin(Money(cost, "USD"), qty, target)
    m = gross_margin(Money(price.amount * qty, "USD"), Money(cost, "USD"))
    assert m.margin is not None
    assert abs(m.margin - target) < D("1e-20")
