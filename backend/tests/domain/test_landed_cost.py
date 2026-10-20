from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.landed_cost import EXTRA_KINDS, CostLine, landed_cost
from app.domain.money import D, Money, q2

USD = "USD"


def main_deal_lines() -> list[CostLine]:
    return [
        CostLine("FREIGHT", Money.of("600.00", USD)),
        CostLine("INSURANCE", Money.of("50.00", USD)),
        CostLine("DUTY", Money.of("800.00", USD)),
        CostLine("BANK_CHARGES", Money.of("150.00", USD)),
    ]


def test_golden_setu_2026_0001() -> None:
    """Worked by hand (data/demo/README.md):
    goods 8,000 m x USD 1.20 = 9,600.00
    extras = 600 + 50 + 800 + 150 = 1,600.00
    landed = 9,600 + 1,600 = 11,200.00; per unit = 11,200 / 8,000 = 1.40
    duty share = 800 / 11,200 = 7.142857...% (largest extra), goods share = 85.714285...%
    """
    r = landed_cost(Money.of("9600.00", USD), D("8000"), main_deal_lines())
    assert r.total == Money.of("11200.00", USD)
    assert r.extras == Money.of("1600.00", USD)
    assert r.per_unit.amount == D("1.4")
    assert [line.kind for line in r.lines] == [
        "GOODS",
        "FREIGHT",
        "INSURANCE",
        "DUTY",
        "BANK_CHARGES",
    ]
    assert q2(r.lines[0].share * 100) == D("85.71")
    biggest = r.largest_extra()
    assert biggest is not None and biggest.kind == "DUTY"
    assert q2(biggest.share * 100) == D("7.14")
    assert any("11,200.00" in f for f in r.facts)


def test_no_extra_costs() -> None:
    r = landed_cost(Money.of("100", USD), D("10"), [])
    assert r.total == Money.of("100", USD)
    assert r.largest_extra() is None
    assert r.lines[0].share == D("1")


@pytest.mark.parametrize("qty", [D("0"), D("-1")])
def test_quantity_must_be_positive(qty: Decimal) -> None:
    with pytest.raises(ValueError, match="quantity"):
        landed_cost(Money.of("100", USD), qty, [])


def test_rejects_negative_and_unknown_lines() -> None:
    with pytest.raises(ValueError, match="negative"):
        landed_cost(Money.of("100", USD), D("1"), [CostLine("DUTY", Money.of("-1", USD))])
    with pytest.raises(ValueError, match="unknown"):
        landed_cost(Money.of("100", USD), D("1"), [CostLine("TIPS", Money.of("1", USD))])


def test_mixed_currency_lines_raise() -> None:
    with pytest.raises(ValueError):
        landed_cost(Money.of("100", USD), D("1"), [CostLine("DUTY", Money.of("1", "BDT"))])


amounts = st.decimals(min_value=0, max_value=10**9, places=4, allow_nan=False)


@given(
    goods=amounts,
    qty=st.decimals(min_value="0.0001", max_value=10**7, places=4),
    extras=st.lists(st.tuples(st.sampled_from(EXTRA_KINDS), amounts), max_size=8),
)
def test_total_equals_sum_of_lines(
    goods: Decimal, qty: Decimal, extras: list[tuple[str, Decimal]]
) -> None:
    r = landed_cost(Money(goods, USD), qty, [CostLine(k, Money(a, USD)) for k, a in extras])
    assert r.total.amount == sum((line.amount.amount for line in r.lines), D("0"))
    assert r.total.amount == r.goods.amount + r.extras.amount
    assert r.per_unit.amount * qty == pytest.approx(r.total.amount, rel=D("1e-20"))
    if r.total.amount > 0:
        assert abs(sum((line.share for line in r.lines), D("0")) - 1) < D("1e-20")
