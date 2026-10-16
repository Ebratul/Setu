"""Landed cost of an import order (FR-3).

landed_cost = goods_value + Σ extra cost lines
              (freight, insurance, duty/taxes, bank/LC charges, other)
share(line) = line / landed_cost
cost_per_unit = landed_cost / quantity

All lines must be in the goods currency (convert first with `fx.FxTable`). Seeded deals carry duty
as a single DUTY line; HS-code based duty estimates (CD/RD/SD/VAT/AIT/AT) arrive with
`seed/hs_duty.json`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.money import ZERO, Money, money_sum

GOODS = "GOODS"
EXTRA_KINDS = ("FREIGHT", "INSURANCE", "DUTY", "BANK_CHARGES", "OTHER")


@dataclass(frozen=True, slots=True)
class CostLine:
    kind: str
    amount: Money
    label: str | None = None


@dataclass(frozen=True, slots=True)
class LandedLine:
    kind: str
    amount: Money
    share: Decimal
    label: str | None = None


@dataclass(frozen=True, slots=True)
class LandedCostResult:
    goods: Money
    extras: Money
    total: Money
    quantity: Decimal
    per_unit: Money
    lines: tuple[LandedLine, ...]
    facts: tuple[str, ...]

    @property
    def extra_lines(self) -> tuple[LandedLine, ...]:
        return tuple(line for line in self.lines if line.kind != GOODS)

    def largest_extra(self) -> LandedLine | None:
        """Largest non-goods line; ties go to the first line in input order."""
        best: LandedLine | None = None
        for line in self.extra_lines:
            if best is None or line.amount.amount > best.amount.amount:
                best = line
        return best


def landed_cost(goods: Money, quantity: Decimal, costs: Sequence[CostLine]) -> LandedCostResult:
    if not isinstance(quantity, Decimal) or quantity <= 0:
        raise ValueError("quantity must be a positive Decimal")
    if goods.amount < 0:
        raise ValueError("goods value must not be negative")
    for c in costs:
        if c.kind not in EXTRA_KINDS:
            raise ValueError(f"unknown cost kind {c.kind}")
        if c.amount.amount < 0:
            raise ValueError("cost lines must not be negative")
    extras = money_sum([c.amount for c in costs], goods.currency)
    total = goods + extras

    def share(m: Money) -> Decimal:
        return m.amount / total.amount if total.amount != ZERO else ZERO

    lines = (
        LandedLine(GOODS, goods, share(goods)),
        *(LandedLine(c.kind, c.amount, share(c.amount), c.label) for c in costs),
    )
    per_unit = Money(total.amount / quantity, goods.currency)
    facts = (
        f"goods value = {goods.format()}",
        *(f"{c.kind.lower()} = {c.amount.format()}" for c in costs),
        f"landed cost = goods + extra costs = {goods.format()} + {extras.format()} = "
        f"{total.format()}",
        f"cost per unit = {total.format()} / {quantity.normalize():f} = {per_unit.format()}",
    )
    return LandedCostResult(goods, extras, total, quantity, per_unit, lines, facts)
