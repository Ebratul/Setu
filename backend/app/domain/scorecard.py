"""Supplier scorecard (FR-3) from monthly SupplierScore snapshots plus the supplier's deals.

on_time_rate = Σ(on_time_rate_m × deals_m) / Σ deals_m        (deal-weighted over the window)
defect_rate  = Σ(defect_rate_m × deals_m) / Σ deals_m
dispute_rate = Σ disputes_m / Σ deals_m
score        = latest monthly score (0–100; formula in seed/scores.py)
price_index  = 100 × Σ landed cost / Σ goods value over the supplier's committed deals
               (100 = no extra costs; higher = more freight/duty/charges per unit of goods value)

Flags (any flag marks the supplier as weak): KYB status not VERIFIED, score < 70,
dispute rate > 10%, on-time rate < 80%.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.money import ZERO, Money

LOW_SCORE_BELOW = Decimal("70")
HIGH_DISPUTE_ABOVE = Decimal("0.10")
LOW_ON_TIME_BELOW = Decimal("0.80")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class ScoreMonth:
    month: date
    deals_count: int
    on_time_rate: Decimal
    defect_rate: Decimal
    doc_mismatch_count: int
    dispute_count: int
    score: Decimal


@dataclass(frozen=True, slots=True)
class SupplierDeal:
    goods: Money
    landed: Money
    completed: bool


@dataclass(frozen=True, slots=True)
class Scorecard:
    score: Decimal | None
    score_trend: tuple[tuple[date, Decimal], ...]
    deals_count: int
    on_time_rate: Decimal | None
    defect_rate: Decimal | None
    dispute_rate: Decimal | None
    doc_mismatch_count: int
    completed_deals: int
    price_index: Decimal | None
    flags: tuple[str, ...]
    facts: tuple[str, ...]

    @property
    def weak(self) -> bool:
        return bool(self.flags)


def supplier_scorecard(
    months: Sequence[ScoreMonth], deals: Sequence[SupplierDeal], kyb_status: str
) -> Scorecard:
    ordered = sorted(months, key=lambda m: m.month)
    n = sum(m.deals_count for m in ordered)
    weight = Decimal(n)
    on_time = sum((m.on_time_rate * m.deals_count for m in ordered), ZERO) / weight if n else None
    defect = sum((m.defect_rate * m.deals_count for m in ordered), ZERO) / weight if n else None
    disputes = sum(m.dispute_count for m in ordered)
    dispute_rate = Decimal(disputes) / weight if n else None
    score = ordered[-1].score if ordered else None

    goods = sum((d.goods.amount for d in deals), ZERO)
    landed = sum((d.landed.amount for d in deals), ZERO)
    if deals and len({d.goods.currency for d in deals} | {d.landed.currency for d in deals}) > 1:
        raise ValueError("supplier deals must share one currency")
    price_index = HUNDRED * landed / goods if goods != ZERO else None

    flags: list[str] = []
    if kyb_status != "VERIFIED":
        flags.append("KYB_NOT_VERIFIED")
    if score is not None and score < LOW_SCORE_BELOW:
        flags.append("LOW_SCORE")
    if dispute_rate is not None and dispute_rate > HIGH_DISPUTE_ABOVE:
        flags.append("HIGH_DISPUTE_RATE")
    if on_time is not None and on_time < LOW_ON_TIME_BELOW:
        flags.append("LOW_ON_TIME")

    facts = (
        f"window = {len(ordered)} months, {n} deals network-wide",
        f"dispute rate = {disputes} disputes / {n} deals",
        f"score = latest monthly score = {score}",
        f"price index = 100 × landed {landed} / goods {goods}",
        f"KYB status = {kyb_status}",
    )
    return Scorecard(
        score=score,
        score_trend=tuple((m.month, m.score) for m in ordered),
        deals_count=n,
        on_time_rate=on_time,
        defect_rate=defect,
        dispute_rate=dispute_rate,
        doc_mismatch_count=sum(m.doc_mismatch_count for m in ordered),
        completed_deals=sum(1 for d in deals if d.completed),
        price_index=price_index,
        flags=tuple(flags),
        facts=facts,
    )
