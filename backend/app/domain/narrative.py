"""Deterministic EN/BN explanation sentences built from domain results (no LLM).

Each sentence carries a stable `code` so the agent (Phase 3.x) can rephrase it later while the
numbers stay exactly as computed here. Percent shares use 1 dp; margins use 2 dp to match KPIs.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.fx import FxQuote
from app.domain.landed_cost import LandedCostResult
from app.domain.margin import MarginBand, MarginResult, margin_band, pct
from app.domain.money import ZERO, Money, q2
from app.domain.scorecard import Scorecard
from app.domain.summary import MonthlySummary

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

COST_LABELS: dict[str, tuple[str, str]] = {
    "GOODS": ("Goods value", "পণ্যের মূল্য"),
    "FREIGHT": ("Freight", "জাহাজ ভাড়া"),
    "INSURANCE": ("Insurance", "বীমা"),
    "DUTY": ("Duty", "শুল্ক"),
    "BANK_CHARGES": ("Bank charges", "ব্যাংক চার্জ"),
    "OTHER": ("Other costs", "অন্যান্য খরচ"),
}
UNIT_LABELS: dict[str, tuple[str, str]] = {
    "m": ("m", "মিটার"),
    "pcs": ("pc", "পিস"),
    "kg": ("kg", "কেজি"),
}
BAND_TEXT: dict[MarginBand, tuple[str, str]] = {
    "healthy": ("healthy (15% or more)", "স্বাস্থ্যকর (১৫% বা বেশি)"),
    "thin": ("thin (8% to 15%)", "পাতলা (৮%–১৫%)"),
    "low": ("low (below 8%)", "কম (৮%-এর নিচে)"),
}
MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTHS_BN = [
    "জানুয়ারি",
    "ফেব্রুয়ারি",
    "মার্চ",
    "এপ্রিল",
    "মে",
    "জুন",
    "জুলাই",
    "আগস্ট",
    "সেপ্টেম্বর",
    "অক্টোবর",
    "নভেম্বর",
    "ডিসেম্বর",
]
FLAG_TEXT: dict[str, tuple[str, str]] = {
    "KYB_NOT_VERIFIED": (
        "KYB is not verified: check the receiving account before paying.",
        "কেওয়াইবি যাচাই হয়নি: টাকা পাঠানোর আগে প্রাপক অ্যাকাউন্ট যাচাই করুন।",
    ),
    "LOW_SCORE": ("Supplier score is below 70.", "সরবরাহকারীর স্কোর ৭০-এর নিচে।"),
    "HIGH_DISPUTE_RATE": (
        "More than 10% of deals ended in a dispute.",
        "১০%-এর বেশি চুক্তিতে বিরোধ হয়েছে।",
    ),
    "LOW_ON_TIME": (
        "Fewer than 80% of deals shipped on time.",
        "৮০%-এর কম চুক্তি সময়মতো পাঠানো হয়েছে।",
    ),
}


@dataclass(frozen=True, slots=True)
class Sentence:
    code: str
    en: str
    bn: str


def bn(text: str) -> str:
    return text.translate(BN_DIGITS)


def p1(fraction: Decimal) -> str:
    """Fraction → percent with 1 dp, e.g. 0.0714 → '7.1'."""
    return f"{(fraction * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"


def money(m: Money) -> str:
    return m.format()


def unit_price(m: Money) -> str:
    """Per-unit price: 2 dp, or 4 dp when the price is below 1 (e.g. USD 0.0459)."""
    places = Decimal("0.0001") if abs(m.amount) < 1 else Decimal("0.01")
    return f"{m.currency} {m.amount.quantize(places, rounding=ROUND_HALF_UP):,}"


def month_name(month: date) -> tuple[str, str]:
    return (
        f"{MONTHS_EN[month.month - 1]} {month.year}",
        bn(f"{MONTHS_BN[month.month - 1]} {month.year}"),
    )


def cost_label(kind: str, label: str | None = None) -> tuple[str, str]:
    en, bn_ = COST_LABELS.get(kind, (kind.title(), kind))
    return (label, label) if label and kind == "OTHER" else (en, bn_)


def order_sentences(
    lc: LandedCostResult,
    margin: MarginResult | None,
    unit: str,
    selling_price: Money | None,
    fx: Sequence[FxQuote],
) -> list[Sentence]:
    out: list[Sentence] = []
    biggest = lc.largest_extra()
    if biggest is not None and biggest.amount.amount > ZERO:
        en, bn_ = cost_label(biggest.kind, biggest.label)
        share, amt = p1(biggest.share), money(biggest.amount)
        out.append(
            Sentence(
                "LARGEST_EXTRA_COST",
                f"{en} is the largest extra cost at {share}% of landed cost ({amt}).",
                bn(f"{bn_} সবচেয়ে বড় অতিরিক্ত খরচ: ল্যান্ডেড খরচের {share}% ({amt})।"),
            )
        )
    if lc.goods.amount > ZERO:
        uplift = p1(lc.extras.amount / lc.goods.amount)
        extras, goods = money(lc.extras), money(lc.goods)
        out.append(
            Sentence(
                "EXTRA_COSTS_TOTAL",
                f"Extra costs add {extras} on top of the goods value of {goods} (+{uplift}%).",
                bn(f"পণ্যের মূল্য {goods}-এর ওপর অতিরিক্ত খরচ {extras} (+{uplift}%)।"),
            )
        )
    band = margin_band(margin.margin) if margin is not None else None
    if margin is not None and margin.margin is not None and band is not None:
        m_pct, profit, rev = pct(margin.margin), money(margin.gross_profit), money(margin.revenue)
        band_en, band_bn = BAND_TEXT[band]
        out.append(
            Sentence(
                "GROSS_MARGIN",
                f"Gross margin is {m_pct}% ({profit}) on expected revenue of {rev}: {band_en}.",
                bn(f"প্রত্যাশিত আয় {rev}-এর ওপর গ্রস মার্জিন {m_pct}% ({profit}): {band_bn}।"),
            )
        )
    else:
        out.append(
            Sentence(
                "NO_SELLING_PRICE",
                "No expected selling price is set, so the margin cannot be calculated.",
                "প্রত্যাশিত বিক্রয়মূল্য দেওয়া নেই, তাই মার্জিন হিসাব করা যায়নি।",
            )
        )
    unit_en, unit_bn = UNIT_LABELS.get(unit, (unit, unit))
    be = unit_price(lc.per_unit)
    if selling_price is not None:
        sp = unit_price(selling_price)
        out.append(
            Sentence(
                "BREAK_EVEN",
                f"Break-even selling price is {be} per {unit_en}; "
                f"the expected price is {sp} per {unit_en}.",
                bn(f"ব্রেক-ইভেন বিক্রয়মূল্য প্রতি {unit_bn} {be}; প্রত্যাশিত মূল্য প্রতি {unit_bn} {sp}।"),
            )
        )
    else:
        out.append(
            Sentence(
                "BREAK_EVEN",
                f"Break-even selling price is {be} per {unit_en}.",
                bn(f"ব্রেক-ইভেন বিক্রয়মূল্য প্রতি {unit_bn} {be}।"),
            )
        )
    if fx:
        out.append(fx_sentence(fx))
    return out


def fx_sentence(fx: Sequence[FxQuote]) -> Sentence:
    rates = " and ".join(f"{q.base}/{q.quote} {q.rate}" for q in fx)
    rates_bn = " ও ".join(f"{q.base}/{q.quote} {q.rate}" for q in fx)
    as_of = max(q.as_of for q in fx)
    return Sentence(
        "FX_RATES_USED",
        f"Converted amounts use mock rates {rates} as of {as_of}.",
        bn(f"রূপান্তরিত অঙ্কে {as_of} তারিখের মক রেট {rates_bn} ব্যবহার করা হয়েছে।"),
    )


def monthly_sentences(s: MonthlySummary) -> list[Sentence]:
    cur, prev = s.current, s.previous
    m_en, m_bn = month_name(cur.month)
    p_en, p_bn = month_name(prev.month)
    out: list[Sentence] = []
    if cur.deals_count == 0:
        out.append(
            Sentence(
                "MONTH_VOLUME",
                f"No import deals were placed in {m_en}.",
                f"{m_bn}-এ কোনো আমদানি চুক্তি হয়নি।",
            )
        )
    else:
        n, goods, landed = cur.deals_count, money(cur.purchases), money(cur.landed)
        noun = "deal" if n == 1 else "deals"
        out.append(
            Sentence(
                "MONTH_VOLUME",
                f"In {m_en} you placed {n} {noun} worth {goods} in goods; "
                f"landed cost was {landed}.",
                bn(f"{m_bn}-এ আপনি {n}টি চুক্তি করেছেন, পণ্যের মূল্য {goods}; ল্যান্ডেড খরচ {landed}।"),
            )
        )
    change = s.purchases_change
    delta = money(Money(abs(change.amount), change.currency))
    if s.purchases_change_ratio is None:
        if cur.purchases.amount > ZERO:
            out.append(
                Sentence(
                    "MONTH_CHANGE",
                    f"Purchases rose from zero in {p_en} to {money(cur.purchases)}.",
                    bn(f"{p_bn}-এ কোনো কেনাকাটা ছিল না; এ মাসে {money(cur.purchases)}।"),
                )
            )
    elif change.amount == ZERO:
        out.append(
            Sentence(
                "MONTH_CHANGE",
                f"Purchases are unchanged from {p_en}.",
                f"কেনাকাটা {p_bn}-এর সমান।",
            )
        )
    else:
        ratio = p1(abs(s.purchases_change_ratio))
        up = change.amount > ZERO
        out.append(
            Sentence(
                "MONTH_CHANGE",
                f"Purchases are {'up' if up else 'down'} {ratio}% ({delta}) from {p_en}.",
                bn(f"{p_bn}-এর তুলনায় কেনাকাটা {ratio}% ({delta}) {'বেড়েছে' if up else 'কমেছে'}।"),
            )
        )
    driver = s.top_cost_driver
    if cur.average_margin is not None and driver is not None:
        d_en, d_bn = cost_label(driver.kind)
        m_pct, share = pct(cur.average_margin), p1(driver.share_of_extras)
        out.append(
            Sentence(
                "MONTH_MARGIN_DRIVER",
                f"Average gross margin is {m_pct}%; {d_en.lower()} is the biggest extra cost "
                f"at {share}% of all extra costs.",
                bn(
                    f"গড় গ্রস মার্জিন {m_pct}%; {d_bn} সবচেয়ে বড় অতিরিক্ত খরচ, "
                    f"মোট অতিরিক্ত খরচের {share}%।"
                ),
            )
        )
    return out


def supplier_sentences(card: Scorecard) -> list[Sentence]:
    out = [Sentence(f"FLAG_{f}", *FLAG_TEXT[f]) for f in card.flags]
    if not out and card.score is not None:
        score = f"{q2(card.score)}"
        out.append(
            Sentence(
                "SUPPLIER_OK",
                f"No warning signs; latest score {score}.",
                bn(f"কোনো সতর্কসংকেত নেই; সর্বশেষ স্কোর {score}।"),
            )
        )
    return out
