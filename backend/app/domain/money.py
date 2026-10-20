"""Decimal money primitives. No floats anywhere in money math (see .claude/rules/money-logic.md)."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Literal

getcontext().prec = 28

Currency = Literal["BDT", "USD", "CNY"]
CURRENCIES: tuple[Currency, ...] = ("BDT", "USD", "CNY")

CENT = Decimal("0.01")
ONE = Decimal("1")
ZERO = Decimal("0")


class CurrencyMismatch(ValueError):
    pass


def D(value: str | int | Decimal) -> Decimal:
    """Build a Decimal from a string/int. Floats are rejected on purpose."""
    if isinstance(value, float):
        raise TypeError("float is not allowed for money; pass a string")
    return Decimal(value)


def q2(value: Decimal) -> Decimal:
    """Quantize to 2 dp with ROUND_HALF_UP (display and ledger boundaries only)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")
        if self.currency not in CURRENCIES:
            raise ValueError(f"unsupported currency {self.currency}")

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: Currency) -> "Money":
        return cls(D(amount), currency)

    def _check(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, factor: Decimal) -> "Money":
        if not isinstance(factor, Decimal):
            raise TypeError("multiply Money by Decimal only")
        return Money(self.amount * factor, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def quantized(self) -> "Money":
        return Money(q2(self.amount), self.currency)

    def format(self) -> str:
        """Human string for explanations, e.g. 'USD 11,200.00'."""
        return f"{self.currency} {q2(self.amount):,.2f}"


def money_sum(items: list[Money], currency: Currency) -> Money:
    total = Money(ZERO, currency)
    for m in items:
        total = total + m
    return total


def split_by_ratios(total: Money, ratios: list[Decimal]) -> list[Money]:
    """Split `total` by `ratios` (must sum to exactly 1). Each part is quantized to 2 dp and the
    last part absorbs the rounding remainder, so the parts always sum to q2(total)."""
    if not ratios:
        raise ValueError("ratios must not be empty")
    if any(r < ZERO for r in ratios):
        raise ValueError("ratios must be non-negative")
    if sum(ratios, ZERO) != ONE:
        raise ValueError("ratios must sum to exactly 1")
    grand = q2(total.amount)
    parts = [q2(grand * r) for r in ratios[:-1]]
    parts.append(grand - sum(parts, ZERO))
    return [Money(p, total.currency) for p in parts]
