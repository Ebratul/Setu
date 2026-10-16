from datetime import date

from app.domain import narrative
from app.domain.landed_cost import CostLine, landed_cost
from app.domain.margin import gross_margin
from app.domain.money import D, Money
from app.domain.scorecard import ScoreMonth, SupplierDeal, supplier_scorecard
from app.domain.summary import DealMonthInput, add_months, monthly_summary


def deal(ref: str, month: date, goods: str, duty: str, freight: str, sale: str | None):
    lc = landed_cost(
        Money.of(goods, "USD"),
        D("100"),
        [CostLine("DUTY", Money.of(duty, "USD")), CostLine("FREIGHT", Money.of(freight, "USD"))],
    )
    m = gross_margin(Money.of(sale, "USD"), lc.total) if sale else None
    return DealMonthInput(ref, month, lc, m)


SEP, OCT = date(2026, 9, 1), date(2026, 10, 1)


def test_monthly_golden() -> None:
    """Oct: A goods 1000 (+100 duty +50 freight = 1150, sale 1500) and B goods 500
    (+20 duty +80 freight = 600, no price). Sep: C goods 800 (+0 +0 = 800, sale 1000).
    Oct purchases 1500, landed 1750; avg margin = (1500-1150)/1500 = 23.33%;
    driver = FREIGHT 130 of 250 extras = 52%; change = 1500-800 = +700 = +87.5%;
    margin change = 23.33% - 20% = +3.33 pts."""
    deals = [
        deal("A", OCT, "1000", "100", "50", "1500"),
        deal("B", OCT, "500", "20", "80", None),
        deal("C", SEP, "800", "0", "0", "1000"),
    ]
    s = monthly_summary(date(2026, 10, 20), deals, "USD")
    assert s.current.deals_count == 2
    assert s.current.purchases == Money.of("1500", "USD")
    assert s.current.landed == Money.of("1750", "USD")
    assert s.current.average_margin is not None
    assert round(s.current.average_margin * 100, 2) == D("23.33")
    assert s.top_cost_driver is not None and s.top_cost_driver.kind == "FREIGHT"
    assert s.top_cost_driver.share_of_extras == D("0.52")
    assert s.purchases_change == Money.of("700", "USD")
    assert s.purchases_change_ratio == D("0.875")
    assert s.margin_change_pts is not None and round(s.margin_change_pts * 100, 2) == D("3.33")
    assert [t.month for t in s.history] == [add_months(OCT, -i) for i in range(5, -1, -1)]
    codes = [x.code for x in narrative.monthly_sentences(s)]
    assert codes == ["MONTH_VOLUME", "MONTH_CHANGE", "MONTH_MARGIN_DRIVER"]
    change = narrative.monthly_sentences(s)[1]
    assert "up 87.5%" in change.en and "বেড়েছে" in change.bn


def test_empty_month() -> None:
    s = monthly_summary(OCT, [], "USD")
    assert s.current.deals_count == 0 and s.current.average_margin is None
    assert s.top_cost_driver is None and s.purchases_change_ratio is None
    sentences = narrative.monthly_sentences(s)
    assert [x.code for x in sentences] == ["MONTH_VOLUME"]
    assert sentences[0].en.startswith("No import deals")


def months(on_time: str, disputes: tuple[int, ...], score: str) -> list[ScoreMonth]:
    return [
        ScoreMonth(add_months(SEP, -i), 2, D(on_time), D("0.01"), 1, d, D(score))
        for i, d in enumerate(disputes)
    ]


def test_scorecard_flags_weak_supplier() -> None:
    card = supplier_scorecard(
        months("0.70", (1, 0, 1), "55.00"),
        [SupplierDeal(Money.of("100", "USD"), Money.of("120", "USD"), completed=False)],
        "WARNING",
    )
    assert card.flags == ("KYB_NOT_VERIFIED", "LOW_SCORE", "HIGH_DISPUTE_RATE", "LOW_ON_TIME")
    assert card.weak
    assert card.dispute_rate == D(2) / D(6)
    assert card.price_index == D("120")
    assert card.deals_count == 6 and card.doc_mismatch_count == 3
    assert next(s.code for s in narrative.supplier_sentences(card)) == "FLAG_KYB_NOT_VERIFIED"


def test_scorecard_boundaries_and_latest_score() -> None:
    ms = months("0.80", (0, 0, 0), "70.00")
    ms[0] = ScoreMonth(SEP, 2, D("0.80"), D("0.01"), 0, 0, D("88.00"))  # latest month
    card = supplier_scorecard(ms, [], "VERIFIED")
    assert card.flags == ()
    assert card.score == D("88.00")
    assert card.price_index is None
    assert narrative.supplier_sentences(card)[0].code == "SUPPLIER_OK"


def test_scorecard_without_history() -> None:
    card = supplier_scorecard([], [], "VERIFIED")
    assert card.score is None and card.on_time_rate is None and card.flags == ()
