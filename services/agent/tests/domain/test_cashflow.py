from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.cashflow import (
    Flow,
    Loan,
    Move,
    UnknownFlow,
    apply_scenario,
    forecast,
    running_balance,
)
from app.domain.money import D, Money

T = date(2026, 10, 20)


def usd(x: str) -> Money:
    return Money.of(x, "USD")


def flow(ref: str, offset: int, direction: str, amount: str, kind: str = "OTHER") -> Flow:
    return Flow(ref, T + timedelta(days=offset), direction, usd(amount), kind, ref)  # type: ignore[arg-type]


def test_running_balance_golden() -> None:
    assert running_balance(D("100"), [D("10"), D("-30"), D("0")]) == [D("110"), D("80"), D("80")]
    assert running_balance(D("5"), []) == []


def test_five_day_window_by_hand() -> None:
    """opening 1000; d0 +200 −50; d1 nothing; d2 −1500; d3 +400; d4 −100
    closings: 1150, 1150, −350, 50, −50; the payment on d2 sees opening(d2) = 1150."""
    flows = [
        flow("a", 0, "IN", "200"),
        flow("b", 0, "OUT", "50"),
        flow("c", 2, "OUT", "1500", "MILESTONE_PAYMENT"),
        flow("d", 3, "IN", "400"),
        flow("e", 4, "OUT", "100"),
        flow("outside", 5, "OUT", "999"),
    ]
    fc = forecast(usd("1000"), T, 4, flows)
    assert [d.closing.amount for d in fc.days] == [
        D(x) for x in ("1150", "1150", "-350", "50", "-50")
    ]
    assert fc.days[2].opening == usd("1150")
    assert fc.days[0].net == usd("150")
    assert fc.lowest.on == T + timedelta(days=2)
    assert [d.closing.amount for d in fc.days] == running_balance(
        D("1000"), [d.net.amount for d in fc.days]
    )
    assert len(fc.weeks) == 1 and fc.weeks[0].lowest == usd("-350")


def test_weeks_cover_every_day() -> None:
    fc = forecast(usd("0"), T, 90, [flow("x", 10, "IN", "5")])
    assert len(fc.days) == 91
    assert sum(len(range((w.end - w.start).days + 1)) for w in fc.weeks) == 91
    assert fc.weeks[-1].closing == usd("5")


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        forecast(usd("0"), T, 3, [Flow("x", T, "IN", Money.of("1", "BDT"), "OTHER", "x")])
    with pytest.raises(ValueError):
        Flow("x", T, "IN", usd("0"), "OTHER", "x")


def test_scenario_move_remove_and_loan() -> None:
    flows = [flow("m2", 18, "OUT", "5760", "MILESTONE_PAYMENT"), flow("rent", 3, "OUT", "720")]
    out = apply_scenario(
        flows,
        moves=[Move("m2", T + timedelta(days=25))],
        removes=["rent"],
        loans=[Loan(usd("1560"), T + timedelta(days=16), T + timedelta(days=80))],
    )
    by_ref = {f.ref: f for f in out}
    assert "rent" not in by_ref
    assert by_ref["m2"].on == T + timedelta(days=25)
    assert by_ref["scenario:loan:1"].direction == "IN"
    assert by_ref["scenario:loan:1:repay"].amount == usd("1560")
    assert flows[0].on == T + timedelta(days=18)  # input untouched


def test_scenario_unknown_ref() -> None:
    with pytest.raises(UnknownFlow):
        apply_scenario([], removes=["nope"])


@given(
    st.lists(
        st.tuples(
            st.integers(0, 30),
            st.sampled_from(["IN", "OUT"]),
            st.decimals(min_value="0.01", max_value=10**6, places=2),
        ),
        max_size=40,
    )
)
def test_conservation(items: list[tuple[int, str, Decimal]]) -> None:
    flows = [flow(f"f{i}", o, d, str(a)) for i, (o, d, a) in enumerate(items)]
    fc = forecast(usd("500"), T, 30, flows)
    net = sum((f.signed for f in flows), D("0"))
    assert fc.days[-1].closing.amount == D("500") + net
    for prev, cur in zip(fc.days, fc.days[1:], strict=False):
        assert cur.opening == prev.closing
