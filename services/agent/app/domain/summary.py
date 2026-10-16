"""Monthly purchase summary for one buyer (FR-3). A deal counts in the month it was opened.

purchases      = Σ goods value
landed         = Σ landed cost
average_margin = Σ gross profit / Σ expected revenue
                 (revenue-weighted; deals without a selling price are skipped)
top_cost_driver = extra-cost kind with the largest Σ amount; share = its Σ / Σ all extra costs
purchases_change = purchases(month) − purchases(previous month);
                   ratio = change / previous (None if 0)
margin_change_pts = average_margin(month) − average_margin(previous)   (fraction points)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.landed_cost import LandedCostResult
from app.domain.margin import MarginResult
from app.domain.money import ZERO, Currency, Money, money_sum

HISTORY_MONTHS = 6


@dataclass(frozen=True, slots=True)
class DealMonthInput:
    reference: str
    month: date
    landed: LandedCostResult
    margin: MarginResult | None


@dataclass(frozen=True, slots=True)
class MonthTotals:
    month: date
    deals_count: int
    purchases: Money
    landed: Money
    revenue: Money
    gross_profit: Money
    average_margin: Decimal | None
    extras_by_kind: dict[str, Money]


@dataclass(frozen=True, slots=True)
class CostDriver:
    kind: str
    amount: Money
    share_of_extras: Decimal


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    current: MonthTotals
    previous: MonthTotals
    history: tuple[MonthTotals, ...]
    top_cost_driver: CostDriver | None
    purchases_change: Money
    purchases_change_ratio: Decimal | None
    margin_change_pts: Decimal | None
    facts: tuple[str, ...]


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + (month.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def month_totals(month: date, deals: Sequence[DealMonthInput], currency: Currency) -> MonthTotals:
    rows = [d for d in deals if month_start(d.month) == month]
    priced = [d.margin for d in rows if d.margin is not None]
    revenue = money_sum([m.revenue for m in priced], currency)
    profit = money_sum([m.gross_profit for m in priced], currency)
    extras: dict[str, Money] = {}
    for d in rows:
        for line in d.landed.extra_lines:
            extras[line.kind] = extras.get(line.kind, Money(ZERO, currency)) + line.amount
    return MonthTotals(
        month=month,
        deals_count=len(rows),
        purchases=money_sum([d.landed.goods for d in rows], currency),
        landed=money_sum([d.landed.total for d in rows], currency),
        revenue=revenue,
        gross_profit=profit,
        average_margin=profit.amount / revenue.amount if revenue.amount != ZERO else None,
        extras_by_kind=extras,
    )


def top_cost_driver(totals: MonthTotals) -> CostDriver | None:
    if not totals.extras_by_kind:
        return None
    kind, amount = max(totals.extras_by_kind.items(), key=lambda kv: kv[1].amount)
    all_extras = sum((m.amount for m in totals.extras_by_kind.values()), ZERO)
    if amount.amount == ZERO:
        return None
    return CostDriver(kind, amount, amount.amount / all_extras)


def monthly_summary(
    month: date,
    deals: Sequence[DealMonthInput],
    currency: Currency,
    history_months: int = HISTORY_MONTHS,
) -> MonthlySummary:
    month = month_start(month)
    history = tuple(
        month_totals(add_months(month, -back), deals, currency)
        for back in range(history_months - 1, -1, -1)
    )
    current = history[-1]
    previous = (
        history[-2] if history_months > 1 else month_totals(add_months(month, -1), deals, currency)
    )
    change = current.purchases - previous.purchases
    ratio = change.amount / previous.purchases.amount if previous.purchases.amount != ZERO else None
    margin_pts = (
        current.average_margin - previous.average_margin
        if current.average_margin is not None and previous.average_margin is not None
        else None
    )
    facts = (
        f"month = {month:%Y-%m}; deals counted by opening date; drafts and cancelled excluded",
        f"purchases = Σ goods value = {current.purchases.format()} "
        f"over {current.deals_count} deals",
        f"landed cost = {current.landed.format()}",
        "average margin = Σ gross profit / Σ expected revenue",
        f"change vs {previous.month:%Y-%m}: {change.format()}",
    )
    return MonthlySummary(
        current=current,
        previous=previous,
        history=history,
        top_cost_driver=top_cost_driver(current),
        purchases_change=change,
        purchases_change_ratio=ratio,
        margin_change_pts=margin_pts,
        facts=facts,
    )
