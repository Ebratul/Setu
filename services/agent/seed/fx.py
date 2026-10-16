"""MOCK FX rates (clearly labelled source 'MOCK'): 91 days of history ending DEMO_TODAY plus a
7-day mock forecast. USD/BDT and USD/CNY follow a seeded, mean-reverting walk in integer ticks
(no floats); CNY/BDT is the cross rate USD/BDT ÷ USD/CNY. Forecast day +2 is a 'good CNY day':
USD/CNY 1.8% above its 30-day mean, so CNY is cheaper in BDT; the FX_OPPORTUNITY alert points to
it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.db.enums import FxKind
from app.db.models import FxRate
from seed.common import Ctx, Rows, rng, sid

HISTORY_FROM = -90
FORECAST_TO = 7
GOOD_CNY_OFFSET = 2
GOOD_CNY_UPLIFT = Decimal("1.018")
SOURCE = "MOCK"
TICK4 = Decimal("0.0001")
PAIRS = (("USD", "BDT"), ("USD", "CNY"), ("CNY", "BDT"))


@dataclass(frozen=True, slots=True)
class Point:
    offset: int
    rate: Decimal
    kind: FxKind


def _walk(
    stream: str, start: int, target: int, step: int, revert: int, scale: Decimal
) -> list[Decimal]:
    r = rng(stream)
    cur = start
    out = []
    for _ in range(HISTORY_FROM, 1):
        out.append(Decimal(cur) * scale)
        cur += r.randint(-step, step) + (target - cur) // revert
    return out


def _q4(value: Decimal) -> Decimal:
    return value.quantize(TICK4, rounding=ROUND_HALF_UP)


def series(ctx: Ctx) -> dict[tuple[str, str], list[Point]]:
    usd_bdt = _walk("fx:USDBDT", 12235, 12260, 9, 20, Decimal("0.01"))
    usd_cny = _walk("fx:USDCNY", 70950, 71000, 35, 15, TICK4)
    offsets = list(range(HISTORY_FROM, 1))
    hist = FxKind.HISTORY
    out: dict[tuple[str, str], list[Point]] = {
        ("USD", "BDT"): [Point(o, _q4(v), hist) for o, v in zip(offsets, usd_bdt, strict=True)],
        ("USD", "CNY"): [Point(o, _q4(v), hist) for o, v in zip(offsets, usd_cny, strict=True)],
    }
    cny_mean = mean_30d(out[("USD", "CNY")])
    r = rng("fx:forecast")
    for offset in range(1, FORECAST_TO + 1):
        bdt = _q4(usd_bdt[-1] + Decimal(r.randint(-3, 3)) * Decimal("0.01"))
        if offset == GOOD_CNY_OFFSET:
            cny = _q4(cny_mean * GOOD_CNY_UPLIFT)
        else:
            cny = _q4(usd_cny[-1] + Decimal(r.randint(-20, 20)) * TICK4)
        out[("USD", "BDT")].append(Point(offset, bdt, FxKind.FORECAST))
        out[("USD", "CNY")].append(Point(offset, cny, FxKind.FORECAST))
    out[("CNY", "BDT")] = [
        Point(b.offset, _q4(b.rate / c.rate), b.kind)
        for b, c in zip(out[("USD", "BDT")], out[("USD", "CNY")], strict=True)
    ]
    return out


def mean_30d(points: list[Point]) -> Decimal:
    window = [p.rate for p in points if p.kind == FxKind.HISTORY and -29 <= p.offset <= 0]
    return sum(window, Decimal("0")) / Decimal(len(window))


@dataclass(frozen=True, slots=True)
class FxOpportunity:
    on: date
    rate: Decimal
    mean_30d: Decimal
    change: Decimal  # fraction, negative = CNY cheaper than usual


def good_cny_day(ctx: Ctx) -> FxOpportunity:
    pts = series(ctx)[("CNY", "BDT")]
    mean = mean_30d(pts)
    point = next(p for p in pts if p.offset == GOOD_CNY_OFFSET)
    return FxOpportunity(ctx.day(point.offset), point.rate, mean, (point.rate - mean) / mean)


def build(ctx: Ctx) -> Rows:
    rows = [
        {
            "id": sid("fx", f"{base}{quote}:{p.kind}:{p.offset}"),
            "base": base,
            "quote": quote,
            "rate": p.rate,
            "as_of": ctx.day(p.offset),
            "kind": p.kind,
            "source": SOURCE,
        }
        for (base, quote), points in series(ctx).items()
        for p in points
    ]
    return [(FxRate, rows)]
