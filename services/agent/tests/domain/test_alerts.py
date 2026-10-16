from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.domain.alerts import (
    Deadline,
    FxPayment,
    deadline_alerts,
    fx_alerts,
    shortfall_alerts,
)
from app.domain.cashflow import Flow, forecast
from app.domain.money import D, Money

T = date(2026, 10, 20)


def usd(x: str) -> Money:
    return Money.of(x, "USD")


def m2_forecast(due_offset: int) -> tuple:
    flows = [
        Flow(
            "milestone:SETU-2026-0001:2",
            T + timedelta(days=due_offset),
            "OUT",
            usd("5760"),
            "MILESTONE_PAYMENT",
            "Fund escrow milestone 2 · SETU-2026-0001",
            "SETU-2026-0001",
            2,
        ),
        Flow("rent", T + timedelta(days=due_offset + 1), "OUT", usd("100"), "RENT", "Rent"),
    ]
    return forecast(usd("4200"), T, 90, flows), flows


def test_shortfall_golden_m2() -> None:
    fc, _ = m2_forecast(18)
    [a] = shortfall_alerts("rahima-knitwear", fc, usd("0"), T)
    assert a.type == "SHORTFALL" and a.amount == usd("1560.00")
    assert a.due_on == T + timedelta(days=18)
    assert a.severity == "WARNING"
    assert a.facts["balance"] == "4200.00" and a.facts["due"] == "5760.00"
    assert a.facts["lowest_balance"] == "-1660.00"
    assert a.action.route == "/app/financing"
    assert a.action.query == {
        "amount": "1560.00",
        "currency": "USD",
        "date": "2026-11-07",
        "deal": "SETU-2026-0001",
    }
    assert a.key == "alert:rahima-knitwear:shortfall:balance:2026-11-07"
    assert "1,560.00" in a.title_en and "১,৫৬০.০০" in a.title_bn


@pytest.mark.parametrize(("offset", "severity"), [(7, "CRITICAL"), (8, "WARNING"), (0, "CRITICAL")])
def test_shortfall_severity_boundary(offset: int, severity: str) -> None:
    fc, _ = m2_forecast(offset)
    assert shortfall_alerts("p", fc, usd("0"), T)[0].severity == severity


def test_buffer_raises_the_bar() -> None:
    fc = forecast(
        usd("1000"), T, 10, [Flow("x", T + timedelta(days=3), "OUT", usd("800"), "OTHER", "x")]
    )
    assert shortfall_alerts("p", fc, usd("0"), T) == []
    [a] = shortfall_alerts("p", fc, usd("500"), T)
    assert a.amount == usd("300.00")


def test_already_below_buffer_on_day_zero() -> None:
    fc = forecast(usd("-10"), T, 5, [])
    [a] = shortfall_alerts("p", fc, usd("0"), T)
    assert a.due_on == T and a.amount == usd("10.00")


@pytest.mark.parametrize(
    ("kind", "offset", "severity"),
    [
        ("MILESTONE", 1, "CRITICAL"),
        ("MILESTONE", 14, "WARNING"),
        ("MILESTONE", 15, "INFO"),
        ("MILESTONE", 31, None),
        ("DUTY", 7, "WARNING"),
        ("DUTY", 8, "INFO"),
        ("DUTY", 60, "INFO"),
        ("DUTY", 61, None),
        ("BILL_OF_ENTRY", 41, "INFO"),
        ("LOAN", 5, "WARNING"),
        ("LOAN", 8, None),
        ("DUTY", -1, None),
    ],
)
def test_deadline_windows(kind: str, offset: int, severity: str | None) -> None:
    d = Deadline(kind, T + timedelta(days=offset), usd("800"), "SETU-2026-0001", 2)  # type: ignore[arg-type]
    out = deadline_alerts("p", [d], T)
    assert (out[0].severity if out else None) == severity


def test_deadline_links() -> None:
    boe = Deadline("BILL_OF_ENTRY", T + timedelta(days=41), None, "SETU-2026-0001")
    duty = Deadline("DUTY", T + timedelta(days=45), usd("800"), "SETU-2026-0001")
    a, b = deadline_alerts("p", [duty, boe], T)
    assert (
        a.action.code == "UPLOAD_BILL_OF_ENTRY" and a.action.route == "/app/orders/SETU-2026-0001"
    )
    assert b.amount == usd("800.00") and "USD 800.00" in b.title_en


def fx(rates: dict[int, str], mean: str = "17.2865") -> FxPayment:
    return FxPayment(
        "SETU-2026-0001",
        2,
        T + timedelta(days=18),
        Money.of("40890.24", "CNY"),
        tuple((T + timedelta(days=o), D(r)) for o, r in rates.items()),
        D(mean),
    )


def test_fx_opportunity_golden() -> None:
    """mean 17.2865, best 16.9682 on T+2 (−1.84%) → saving 40,890.24 × 0.3183 = 13,015.36 BDT."""
    [a] = fx_alerts("p", [fx({0: "17.27", 2: "16.9682", 5: "17.20", 20: "16.0"})], T)
    assert a.due_on == T + timedelta(days=2)
    assert a.amount == Money(q := D("40890.24") * D("0.3183"), "BDT").quantized()
    assert q > 0 and a.facts["rate"] == "16.9682"


def test_fx_threshold_boundary() -> None:
    exactly_one_pct = str(D("17.2865") * D("0.99"))
    assert fx_alerts("p", [fx({1: exactly_one_pct})], T) == []
    assert len(fx_alerts("p", [fx({1: "17.0"})], T)) == 1
    assert fx_alerts("p", [fx({})], T) == []


def test_keys_are_stable() -> None:
    fc, _ = m2_forecast(18)
    one = shortfall_alerts("p", fc, usd("0"), T)
    two = shortfall_alerts("p", fc, usd("0"), T)
    assert [a.key for a in one] == [a.key for a in two]
    assert isinstance(one[0].amount.amount, Decimal)
