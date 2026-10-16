from datetime import date

import pytest

from app.domain.fx import FxQuote, FxRateMissing, FxTable
from app.domain.money import D, Money, q2

AS_OF = date(2026, 10, 20)


def table() -> FxTable:
    return FxTable(
        [
            FxQuote("USD", "BDT", D("122.59"), AS_OF, "MOCK"),
            FxQuote("USD", "CNY", D("7.099"), AS_OF, "MOCK"),
        ]
    )


def test_direct_inverse_and_identity() -> None:
    fx = table()
    assert fx.convert(Money.of("11200", "USD"), "BDT") == Money.of("1373008.00", "BDT")
    assert fx.rate("USD", "USD") == D("1")
    assert q2(fx.convert(Money.of("122.59", "BDT"), "USD").amount) == D("1.00")


def test_cross_through_usd_when_no_direct_pair() -> None:
    fx = table()
    assert q2(fx.convert(Money.of("7.099", "CNY"), "BDT").amount) == D("122.59")
    assert [(q.base, q.quote) for q in fx.path("CNY", "BDT")] == [("USD", "CNY"), ("USD", "BDT")]


def test_direct_pair_wins_over_cross() -> None:
    fx = FxTable([*table().quotes, FxQuote("CNY", "BDT", D("17.2686"), AS_OF, "MOCK")])
    assert fx.rate("CNY", "BDT") == D("17.2686")
    assert len(fx.path("BDT", "CNY")) == 1


def test_missing_rate_raises() -> None:
    fx = FxTable([FxQuote("USD", "BDT", D("122.59"), AS_OF, "MOCK")])
    with pytest.raises(FxRateMissing):
        fx.rate("USD", "CNY")


def test_rate_must_be_positive_decimal() -> None:
    with pytest.raises(ValueError):
        FxQuote("USD", "BDT", D("0"), AS_OF, "MOCK")
