from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.cashflow import Flow, forecast
from app.domain.financing import (
    Quote,
    Terms,
    code_rules,
    evaluate_rules,
    option_cost,
    option_tenor,
    order_gap,
    rank,
    schedule,
    shortfall_gap,
    why_codes,
)
from app.domain.money import D, Money, q2

T = date(2026, 10, 20)
M3_RELEASE = T + timedelta(days=45)  # arrival T+40 + 5 days clearance

SUPPLIER = Terms(
    "supplier-credit-huaxin",
    "SUPPLIER_CREDIT",
    annual_rate=D("0"),
    price_uplift_rate=D("0.02"),
    tenor_days_min=60,
    tenor_days_max=60,
    collateral="None",
    eligibility={"all": [{"fact": "completed_deals_with_supplier", "op": "gte", "value": 1}]},
)
BANK = Terms(
    "import-loan-meghna",
    "BANK_IMPORT_LOAN",
    annual_rate=D("0.115"),
    fee_rate=D("0.005"),
    tenor_days_min=90,
    tenor_days_max=90,
    min_amount=D("2000"),
    collateral="Lien on goods",
)
ESCROW = Terms(
    "escrow-order-loan-setu-partner",
    "ESCROW_BACKED_LOAN",
    annual_rate=D("0.09"),
    fee_fixed=D("40"),
    tenor_rule="UNTIL_MILESTONE_3",
    tenor_days_max=120,
    collateral="Assignment of escrow",
)
INSURED = Terms(
    "insured-supplier-terms",
    "INSURED_SUPPLIER_TERMS",
    flat_cost_rate=D("0.012"),
    tenor_days_min=90,
    tenor_days_max=90,
    min_amount=D("3000"),
)
NBFI = Terms(
    "working-capital-shitalakshya",
    "WORKING_CAPITAL_LINE",
    annual_rate=D("0.14"),
    tenor_days_min=30,
    tenor_days_max=120,
)
P = Money.of("5200.00", "USD")


def total(t: Terms) -> Decimal:
    return q2(option_cost(t, P, option_tenor(t, T, M3_RELEASE)).total.amount)


def test_tc09_costs_by_hand() -> None:
    """5,200 × 9% × 45/365 + 40 = 57.70 + 40 = 97.70 · 5,200 × 2% = 104.00 ·
    5,200 × 11.5% × 90/365 + 0.5% = 147.45 + 26.00 = 173.45 · NBFI at its 120-day max:
    5,200 × 14% × 120/365 = 239.34 · insured 5,200 × 1.2% = 62.40."""
    assert option_tenor(ESCROW, T, M3_RELEASE) == 45
    assert total(ESCROW) == D("97.70")
    assert total(SUPPLIER) == D("104.00")
    assert total(BANK) == D("173.45")
    assert option_tenor(NBFI, T, M3_RELEASE) == 120
    assert total(NBFI) == D("239.34")
    assert total(INSURED) == D("62.40")


def test_effective_annual_rate_and_per_30_days() -> None:
    c = option_cost(BANK, P, 90)
    expected = (1 + c.total.amount / P.amount) ** (D(365) / D(90)) - 1
    assert c.effective_annual_rate == expected
    assert q2(c.effective_annual_rate * 100) == D("14.23")
    assert q2(c.per_30_days.amount) == q2(c.total.amount / 3)


def test_tenor_rules() -> None:
    capped = Terms("x", "ESCROW_BACKED_LOAN", tenor_rule="UNTIL_MILESTONE_3", tenor_days_max=30)
    assert option_tenor(capped, T, M3_RELEASE) == 30
    assert option_tenor(ESCROW, T, None) == 120  # no arrival milestone → max
    with pytest.raises(ValueError):
        option_tenor(Terms("y", "OTHER"), T, None)


def test_cost_input_guards() -> None:
    with pytest.raises(ValueError):
        option_cost(BANK, P, 0)
    with pytest.raises(ValueError):
        option_cost(BANK, Money.of("0", "USD"), 30)


@pytest.mark.parametrize(
    ("op", "actual", "value", "ok"),
    [
        ("gte", 2, 2, True),
        ("gte", 1, 2, False),
        ("eq", "VERIFIED", "VERIFIED", True),
        ("eq", True, True, True),
        ("lte", "1500.00", "2000.00", True),
        ("gte", "1560.00", "2000.00", False),
        ("in", "a", ["a", "b"], True),
    ],
)
def test_rule_tree_ops(op: str, actual: object, value: object, ok: bool) -> None:
    [c] = evaluate_rules({"all": [{"fact": "f", "op": op, "value": value}]}, {"f": actual})
    assert c.ok is ok


def test_rule_tree_reason_text_and_missing_fact() -> None:
    tree = {"all": [{"fact": "completed_deals_with_supplier", "op": "gte", "value": 2}]}
    [c] = evaluate_rules(tree, {"completed_deals_with_supplier": 1})
    assert not c.ok and "you have 1" in c.en and "১" in c.bn
    [m] = evaluate_rules(tree, {})
    assert not m.ok and m.code.startswith("MISSING_")


def test_code_rules() -> None:
    small = Money.of("1560.00", "USD")
    codes = {c.code: c.ok for c in code_rules(INSURED, small, 90, 12, escrow_funded=True)}
    assert codes == {"MIN_AMOUNT": False, "TENOR_FITS": True, "NOT_WITH_FUNDED_ESCROW": False}
    assert {c.code: c.ok for c in code_rules(INSURED, P, 90, 45, escrow_funded=False)} == {
        "MIN_AMOUNT": True,
        "TENOR_FITS": True,
        "NOT_WITH_FUNDED_ESCROW": True,
    }
    [*_, fits] = code_rules(SUPPLIER, P, 60, 61, escrow_funded=True)
    assert fits.code == "TENOR_FITS" and not fits.ok


def quote(t: Terms, ok: bool = True) -> Quote:
    cost = option_cost(t, P, option_tenor(t, T, M3_RELEASE))
    checks = tuple(code_rules(t, P, cost.days, 1, escrow_funded=True)) if ok else ()
    if not ok:
        checks = (*code_rules(t, P, cost.days, 999, escrow_funded=True),)
    return Quote(t, cost, checks, T)


def test_tc09_ranking_and_pick() -> None:
    quotes = [quote(BANK), quote(INSURED), quote(NBFI), quote(SUPPLIER), quote(ESCROW)]
    ranked = rank(quotes)
    assert [q.terms.code for q in ranked] == [
        "escrow-order-loan-setu-partner",
        "supplier-credit-huaxin",
        "import-loan-meghna",
        "working-capital-shitalakshya",
        "insured-supplier-terms",  # ineligible: escrow already funded
    ]
    assert not ranked[-1].eligible
    assert why_codes(ranked[0], ranked[1]) == [
        "LOWEST_COST",
        "USES_ESCROW",
        "MATCHES_DEAL_TIMELINE",
    ]
    assert rank(list(reversed(quotes))) == ranked


def test_tie_break_by_tenor_then_conditions_then_code() -> None:
    a = Terms("b-opt", "X", flat_cost_rate=D("0.01"), tenor_days_min=30, tenor_days_max=30)
    b = Terms("a-opt", "X", flat_cost_rate=D("0.01"), tenor_days_min=60, tenor_days_max=60)
    c = Terms(
        "c-opt",
        "X",
        flat_cost_rate=D("0.01"),
        tenor_days_min=30,
        tenor_days_max=30,
        collateral="Guarantee",
    )
    d = Terms("a2-opt", "X", flat_cost_rate=D("0.01"), tenor_days_min=30, tenor_days_max=30)
    qs = [Quote(t, option_cost(t, P, t.tenor_days_max or 1), (), T) for t in (a, b, c, d)]
    assert [q.terms.code for q in rank(qs)] == ["a2-opt", "b-opt", "c-opt", "a-opt"]


def test_schedule_is_one_bullet() -> None:
    c = option_cost(ESCROW, P, 45)
    [i] = schedule(c, T)
    assert i.due_on == M3_RELEASE and i.total.amount == P.amount + c.total.amount


def test_order_gap() -> None:
    g = order_gap(Money.of("11200", "USD"), Money.of("6000", "USD"), T, M3_RELEASE)
    assert g.amount == Money.of("5200", "USD") and g.needed_for_days == 45
    rich = order_gap(Money.of("11200", "USD"), Money.of("20000", "USD"), T, M3_RELEASE)
    assert rich.amount.amount == 0


def test_shortfall_gap_golden() -> None:
    """opening 4,200; T+18 −5,760 → −1,560; T+19 −600 → −2,160; T+24 +1,360 → −800;
    T+31 +1,240 → +440: gap 1,560 on T+18, recovers T+31 (13 days), peak 2,160."""
    usd = lambda x: Money.of(x, "USD")  # noqa: E731
    flows = [
        Flow("m2", T + timedelta(days=18), "OUT", usd("5760"), "MILESTONE_PAYMENT", "m2"),
        Flow("fr", T + timedelta(days=19), "OUT", usd("600"), "FREIGHT", "fr"),
        Flow("s1", T + timedelta(days=24), "IN", usd("1360"), "SALES", "s1"),
        Flow("s2", T + timedelta(days=31), "IN", usd("1240"), "SALES", "s2"),
    ]
    g = shortfall_gap(forecast(usd("4200"), T, 60, flows), usd("0"))
    assert g is not None
    assert g.amount == usd("1560") and g.needed_by == T + timedelta(days=18)
    assert g.recover_on == T + timedelta(days=31) and g.needed_for_days == 13
    assert g.peak == usd("2160")
    assert shortfall_gap(forecast(usd("10"), T, 5, []), usd("0")) is None


@given(st.decimals(min_value="0.01", max_value=10**7, places=2), st.integers(1, 365))
def test_cost_parts_sum_to_total(principal: Decimal, days: int) -> None:
    for t in (SUPPLIER, BANK, ESCROW, INSURED, NBFI):
        c = option_cost(t, Money(principal, "USD"), days)
        parts = c.interest.amount + c.fees.amount + c.uplift.amount + c.flat.amount
        assert parts == c.total.amount and c.total.amount >= 0
