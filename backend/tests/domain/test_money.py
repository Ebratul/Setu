from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.money import CurrencyMismatch, D, Money, money_sum, q2, split_by_ratios

RATIOS_30_60_10 = [Decimal("0.30"), Decimal("0.60"), Decimal("0.10")]


def test_golden_split_main_deal() -> None:
    parts = split_by_ratios(Money.of("9600.00", "USD"), RATIOS_30_60_10)
    assert [p.amount for p in parts] == [D("2880.00"), D("5760.00"), D("960.00")]


def test_last_part_absorbs_remainder() -> None:
    parts = split_by_ratios(Money.of("100.01", "USD"), [D("0.5"), D("0.5")])
    assert [p.amount for p in parts] == [D("50.01"), D("50.00")]


def test_q2_rounds_half_up() -> None:
    assert q2(D("1.005")) == D("1.01")
    assert q2(D("-1.005")) == D("-1.01")


def test_floats_are_rejected() -> None:
    with pytest.raises(TypeError):
        D(1.2)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(1.2, "USD")  # type: ignore[arg-type]


def test_currency_mismatch_raises() -> None:
    with pytest.raises(CurrencyMismatch):
        _ = Money.of("1", "USD") + Money.of("1", "CNY")


def test_ratios_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        split_by_ratios(Money.of("10", "USD"), [D("0.3"), D("0.6")])


def test_money_sum_and_format() -> None:
    total = money_sum([Money.of("9600", "USD"), Money.of("1600", "USD")], "USD")
    assert total.format() == "USD 11,200.00"


@given(
    cents=st.integers(min_value=0, max_value=10**12),
    weights=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=6),
)
def test_split_conserves_total(cents: int, weights: list[int]) -> None:
    total = Money(Decimal(cents) / 100, "BDT")
    ratios = [Decimal(w) / Decimal(sum(weights)) for w in weights[:-1]]
    ratios.append(Decimal(1) - sum(ratios, Decimal(0)))
    parts = split_by_ratios(total, ratios)
    assert sum((p.amount for p in parts), Decimal(0)) == q2(total.amount)
    assert all(p.currency == "BDT" for p in parts)
