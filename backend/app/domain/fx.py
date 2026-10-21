"""FX conversion with explicit, recorded rates. Spreads and fees are never baked into a rate.

A quote means 1 `base` = `rate` `quote`. `FxTable.rate(a, b)` resolves, in order: identity (1),
a direct quote, the inverse of a direct quote (1 / rate), or a cross through USD.
Converted amounts keep full precision; callers quantize at the display boundary.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.domain.money import ONE, Currency, Money

PIVOT: Currency = "USD"


class FxRateMissing(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class FxQuote:
    base: Currency
    quote: Currency
    rate: Decimal
    as_of: date
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.rate, Decimal) or self.rate <= 0:
            raise ValueError("FX rate must be a positive Decimal")

    def fact(self) -> str:
        return f"1 {self.base} = {self.rate} {self.quote} ({self.source}, as of {self.as_of})"


class FxTable:
    """Rates for one valuation date; remembers which quotes a conversion used."""

    def __init__(self, quotes: Iterable[FxQuote]) -> None:
        self._quotes = {(q.base, q.quote): q for q in quotes}

    @property
    def quotes(self) -> list[FxQuote]:
        return list(self._quotes.values())

    def path(self, base: Currency, quote: Currency) -> list[FxQuote]:
        """Quotes needed to go from `base` to `quote` (empty when equal)."""
        if base == quote:
            return []
        for pair in ((base, quote), (quote, base)):
            if pair in self._quotes:
                return [self._quotes[pair]]
        if PIVOT not in (base, quote):
            return self.path(base, PIVOT) + self.path(PIVOT, quote)
        raise FxRateMissing(f"no rate for {base}/{quote}")

    def rate(self, base: Currency, quote: Currency) -> Decimal:
        if base == quote:
            return ONE
        direct = self._quotes.get((base, quote))
        if direct is not None:
            return direct.rate
        inverse = self._quotes.get((quote, base))
        if inverse is not None:
            return ONE / inverse.rate
        if PIVOT not in (base, quote):
            return self.rate(base, PIVOT) * self.rate(PIVOT, quote)
        raise FxRateMissing(f"no rate for {base}/{quote}")

    def convert(self, money: Money, to: Currency) -> Money:
        """amount_to = amount_from × rate(from, to); full precision."""
        return Money(money.amount * self.rate(money.currency, to), to)
