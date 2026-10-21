"""Order margin (FR-3).

gross_profit = revenue − landed_cost
gross_margin = gross_profit / revenue          (fraction; None when revenue is 0)
markup       = gross_profit / landed_cost      (fraction; None when cost is 0)
break_even_price = landed_cost / quantity
price_for_margin(m) = (landed_cost / quantity) / (1 − m), for 0 ≤ m < 1

Margin band (UI colour and explanation wording) is judged on the margin rounded to 2 dp in percent,
so the colour always agrees with the number shown: healthy ≥ 15.00%, thin ≥ 8.00%, else low.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.money import ONE, ZERO, Money, q2

HEALTHY_MIN_PCT = Decimal("15")
THIN_MIN_PCT = Decimal("8")
HUNDRED = Decimal("100")

MarginBand = Literal["healthy", "thin", "low"]


@dataclass(frozen=True, slots=True)
class MarginResult:
    revenue: Money
    cost: Money
    gross_profit: Money
    margin: Decimal | None
    markup: Decimal | None
    facts: tuple[str, ...]


def gross_margin(revenue: Money, cost: Money) -> MarginResult:
    profit = revenue - cost
    margin = profit.amount / revenue.amount if revenue.amount != ZERO else None
    markup = profit.amount / cost.amount if cost.amount != ZERO else None
    facts = [f"gross profit = {revenue.format()} − {cost.format()} = {profit.format()}"]
    if margin is not None:
        facts.append(f"gross margin = gross profit / revenue = {pct(margin)}%")
    if markup is not None:
        facts.append(f"markup = gross profit / landed cost = {pct(markup)}%")
    return MarginResult(revenue, cost, profit, margin, markup, tuple(facts))


def break_even_price(cost: Money, quantity: Decimal) -> Money:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return Money(cost.amount / quantity, cost.currency)


def price_for_margin(cost: Money, quantity: Decimal, target_margin: Decimal) -> Money:
    """Selling price per unit that yields `target_margin` (a fraction) on revenue."""
    if not ZERO <= target_margin < ONE:
        raise ValueError("target margin must be in [0, 1)")
    return Money(break_even_price(cost, quantity).amount / (ONE - target_margin), cost.currency)


def pct(fraction: Decimal) -> Decimal:
    """Fraction → percent rounded to 2 dp (display boundary)."""
    return q2(fraction * HUNDRED)


def margin_band(margin: Decimal | None) -> MarginBand | None:
    if margin is None:
        return None
    shown = pct(margin)
    if shown >= HEALTHY_MIN_PCT:
        return "healthy"
    if shown >= THIN_MIN_PCT:
        return "thin"
    return "low"
