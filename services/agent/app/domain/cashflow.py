"""Day-by-day cash-flow forecast for one buyer (FR-2). Pure: callers pass the flows.

closing(d) = opening(d) + inflow(d) − outflow(d);   opening(start) = opening cash;
opening(d + 1) = closing(d)
So the balance *available* for a payment on day D is opening(D): every flow dated before D
(the seed's projected-balance rule in seed/cashflow.py). The forecast covers start … start + days
inclusive; flows outside that window are ignored. Weekly buckets are 7-day blocks from `start`.

Scenario overrides (what-if, never saved) move or remove flows by `ref` and add loan inflows with an
optional repayment outflow.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from app.domain.money import ZERO, Currency, Money, money_sum

Direction = Literal["IN", "OUT"]
WEEK = 7


@dataclass(frozen=True, slots=True)
class Flow:
    ref: str
    on: date
    direction: Direction
    amount: Money
    kind: str
    label: str
    deal_ref: str | None = None
    milestone_seq: int | None = None

    def __post_init__(self) -> None:
        if self.amount.amount <= ZERO:
            raise ValueError("flow amounts are positive; direction gives the sign")

    @property
    def signed(self) -> Decimal:
        return self.amount.amount if self.direction == "IN" else -self.amount.amount


@dataclass(frozen=True, slots=True)
class Day:
    on: date
    opening: Money
    inflow: Money
    outflow: Money
    closing: Money
    items: tuple[Flow, ...]

    @property
    def net(self) -> Money:
        return self.inflow - self.outflow


@dataclass(frozen=True, slots=True)
class Week:
    start: date
    end: date
    inflow: Money
    outflow: Money
    closing: Money
    lowest: Money


@dataclass(frozen=True, slots=True)
class Forecast:
    start: date
    opening: Money
    days: tuple[Day, ...]
    weeks: tuple[Week, ...]
    facts: tuple[str, ...]

    @property
    def lowest(self) -> Day:
        return min(self.days, key=lambda d: (d.closing.amount, d.on))

    def day(self, on: date) -> Day | None:
        index = (on - self.start).days
        return self.days[index] if 0 <= index < len(self.days) else None


def running_balance(opening: Decimal, deltas: Sequence[Decimal]) -> list[Decimal]:
    """Closing balance after each delta: [opening + d0, opening + d0 + d1, ...]."""
    out, bal = [], opening
    for delta in deltas:
        bal += delta
        out.append(bal)
    return out


def forecast(opening: Money, start: date, days: int, flows: Sequence[Flow]) -> Forecast:
    if days < 0:
        raise ValueError("days must be >= 0")
    ccy: Currency = opening.currency
    end = start + timedelta(days=days)
    by_day: dict[date, list[Flow]] = {}
    for f in flows:
        if f.amount.currency != ccy:
            raise ValueError("convert flows to the opening-balance currency first")
        if start <= f.on <= end:
            by_day.setdefault(f.on, []).append(f)

    dates = [start + timedelta(days=i) for i in range(days + 1)]
    items = [tuple(sorted(by_day.get(d, []), key=lambda f: (f.direction, f.ref))) for d in dates]
    closings = running_balance(opening.amount, [sum((f.signed for f in it), ZERO) for it in items])
    out: list[Day] = []
    prev = opening
    for d, it, closing in zip(dates, items, closings, strict=True):
        inflow = money_sum([f.amount for f in it if f.direction == "IN"], ccy)
        outflow = money_sum([f.amount for f in it if f.direction == "OUT"], ccy)
        day = Day(d, prev, inflow, outflow, Money(closing, ccy), it)
        out.append(day)
        prev = day.closing

    weeks = []
    for i in range(0, len(out), WEEK):
        block = out[i : i + WEEK]
        weeks.append(
            Week(
                start=block[0].on,
                end=block[-1].on,
                inflow=money_sum([d.inflow for d in block], ccy),
                outflow=money_sum([d.outflow for d in block], ccy),
                closing=block[-1].closing,
                lowest=min((d.closing for d in block), key=lambda m: m.amount),
            )
        )
    facts = (
        f"opening balance {opening.format()} at the start of {start}",
        "closing(d) = opening(d) + inflows(d) − outflows(d); opening(d+1) = closing(d)",
        f"window {start} … {end} ({days + 1} days), {sum(len(i) for i in items)} items",
    )
    return Forecast(start, opening, tuple(out), tuple(weeks), facts)


@dataclass(frozen=True, slots=True)
class Move:
    ref: str
    on: date


@dataclass(frozen=True, slots=True)
class Loan:
    amount: Money
    on: date
    repay_on: date | None = None
    repay_amount: Money | None = None


class UnknownFlow(LookupError):
    pass


def apply_scenario(
    flows: Sequence[Flow],
    moves: Sequence[Move] = (),
    removes: Sequence[str] = (),
    loans: Sequence[Loan] = (),
) -> list[Flow]:
    """Return a new flow list with moves/removals applied and loan in/out flows added."""
    known = {f.ref for f in flows}
    missing = [r for r in [*(m.ref for m in moves), *removes] if r not in known]
    if missing:
        raise UnknownFlow(f"{len(set(missing))} unknown item ref(s) in the scenario")
    moved = {m.ref: m.on for m in moves}
    dropped = set(removes)
    out = [replace(f, on=moved.get(f.ref, f.on)) for f in flows if f.ref not in dropped]
    for i, loan in enumerate(loans, start=1):
        out.append(Flow(f"scenario:loan:{i}", loan.on, "IN", loan.amount, "LOAN", "What-if loan"))
        if loan.repay_on is not None:
            repay = loan.repay_amount or loan.amount
            out.append(
                Flow(
                    f"scenario:loan:{i}:repay",
                    loan.repay_on,
                    "OUT",
                    repay,
                    "LOAN_REPAYMENT",
                    "What-if loan repayment",
                )
            )
    return out
