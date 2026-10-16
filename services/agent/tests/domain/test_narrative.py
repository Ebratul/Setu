from datetime import date

from app.domain import narrative
from app.domain.fx import FxQuote
from app.domain.landed_cost import CostLine, landed_cost
from app.domain.margin import gross_margin
from app.domain.money import D, Money


def main_deal():
    lc = landed_cost(
        Money.of("9600", "USD"),
        D("8000"),
        [
            CostLine("FREIGHT", Money.of("600", "USD")),
            CostLine("INSURANCE", Money.of("50", "USD")),
            CostLine("DUTY", Money.of("800", "USD")),
            CostLine("BANK_CHARGES", Money.of("150", "USD")),
        ],
    )
    return lc, gross_margin(Money.of("13660", "USD"), lc.total)


FX = [FxQuote("USD", "BDT", D("122.59"), date(2026, 10, 20), "MOCK")]


def test_order_sentences_golden() -> None:
    lc, m = main_deal()
    out = narrative.order_sentences(lc, m, "m", Money.of("1.7075", "USD"), FX)
    by_code = {s.code: s for s in out}
    assert list(by_code) == [
        "LARGEST_EXTRA_COST",
        "EXTRA_COSTS_TOTAL",
        "GROSS_MARGIN",
        "BREAK_EVEN",
        "FX_RATES_USED",
    ]
    assert by_code["LARGEST_EXTRA_COST"].en == (
        "Duty is the largest extra cost at 7.1% of landed cost (USD 800.00)."
    )
    assert "শুল্ক" in by_code["LARGEST_EXTRA_COST"].bn
    assert "৭.১%" in by_code["LARGEST_EXTRA_COST"].bn
    assert "18.01%" in by_code["GROSS_MARGIN"].en and "healthy" in by_code["GROSS_MARGIN"].en
    assert "USD 1.40 per m" in by_code["BREAK_EVEN"].en
    assert "USD 1.71 per m" in by_code["BREAK_EVEN"].en
    assert "মিটার" in by_code["BREAK_EVEN"].bn
    assert "as of 2026-10-20" in by_code["FX_RATES_USED"].en


def test_bn_sentences_use_bengali_digits_only() -> None:
    lc, m = main_deal()
    for s in narrative.order_sentences(lc, m, "m", None, FX):
        assert not any(ch.isascii() and ch.isdigit() for ch in s.bn), s.bn


def test_no_selling_price_sentence() -> None:
    lc, _ = main_deal()
    codes = [s.code for s in narrative.order_sentences(lc, None, "m", None, [])]
    assert "NO_SELLING_PRICE" in codes and "GROSS_MARGIN" not in codes


def test_small_unit_prices_keep_four_decimals() -> None:
    assert narrative.unit_price(Money.of("0.04594", "USD")) == "USD 0.0459"
    assert narrative.unit_price(Money.of("1234.5", "USD")) == "USD 1,234.50"
