"""FR-7: total cost of paying a Chinese supplier via USD or directly in CNY.

The supplier must receive the CNY value of the invoice (a USD invoice is valued at the USD/CNY mid
rate). Two routes, each priced from the recorded mid rates plus explicit spreads and fees:

- USD route: the buyer's bank sells USD (USD/BDT mid × (1 + USD_SELL_SPREAD)); the supplier's bank
  converts USD to CNY at USD/CNY mid × (1 − SUPPLIER_CONVERSION_SPREAD), so the buyer must send
  enough USD to cover that loss; plus a SWIFT fee and a correspondent fee in USD.
- CNY route: the buyer's bank sells CNY directly (CNY/BDT mid × (1 + CNY_SELL_SPREAD)); plus a
  flat CNY transfer fee in BDT.

Spreads and fees are MOCK demo assumptions (labelled in every result), never baked into a rate.
Amounts keep full precision; the caller quantizes for display.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.fx import FxTable
from app.domain.money import ONE, ZERO, Currency, Money

USD_SELL_SPREAD = Decimal("0.0050")
SUPPLIER_CONVERSION_SPREAD = Decimal("0.0060")
USD_SWIFT_FEE_USD = Decimal("20")
USD_CORRESPONDENT_FEE_USD = Decimal("15")
CNY_SELL_SPREAD = Decimal("0.0080")
CNY_TRANSFER_FEE_BDT = Decimal("1000")


def _pct(x: Decimal) -> str:
    return f"{(x * 100).normalize():f}%"


ASSUMPTIONS = (
    f"MOCK: bank sells USD at mid + {_pct(USD_SELL_SPREAD)}",
    f"MOCK: supplier's bank converts USD to CNY at mid − {_pct(SUPPLIER_CONVERSION_SPREAD)}",
    f"MOCK: USD route fees: SWIFT USD {USD_SWIFT_FEE_USD} + correspondent USD "
    f"{USD_CORRESPONDENT_FEE_USD}",
    f"MOCK: bank sells CNY at mid + {_pct(CNY_SELL_SPREAD)}",
    f"MOCK: CNY route fee: BDT {CNY_TRANSFER_FEE_BDT}",
)


@dataclass(frozen=True, slots=True)
class RouteCost:
    route: Currency  # currency the buyer sends: "USD" or "CNY"
    sent: Money  # amount sent in the route currency (before fees)
    rate_used: Decimal  # payer currency per 1 unit of the route currency, incl. spread
    conversion: Money  # payer-currency cost of the conversion (sent × rate_used)
    fees: Money  # payer currency
    total: Money  # payer currency


@dataclass(frozen=True, slots=True)
class RouteComparison:
    invoice: Money
    supplier_receives: Money  # CNY
    payer: Currency
    usd_route: RouteCost
    cny_route: RouteCost
    cheaper: Currency
    saving: Money  # payer currency, ≥ 0
    saving_pct: Decimal  # of the dearer route, 0–100


def compare_routes(invoice: Money, payer: Currency, fx: FxTable) -> RouteComparison:
    if invoice.amount <= ZERO:
        raise ValueError("invoice amount must be positive")
    if invoice.currency not in ("USD", "CNY"):
        raise ValueError("invoice currency must be USD or CNY")
    cny_needed = fx.convert(invoice, "CNY")
    usd_cny_received = fx.rate("USD", "CNY") * (ONE - SUPPLIER_CONVERSION_SPREAD)
    usd_sent = Money(cny_needed.amount / usd_cny_received, "USD")
    usd_rate = fx.rate("USD", payer) * (ONE + USD_SELL_SPREAD)
    usd_fees = fx.convert(Money(USD_SWIFT_FEE_USD + USD_CORRESPONDENT_FEE_USD, "USD"), payer)
    usd_conv = Money(usd_sent.amount * usd_rate, payer)
    usd = RouteCost("USD", usd_sent, usd_rate, usd_conv, usd_fees, usd_conv + usd_fees)

    cny_rate = fx.rate("CNY", payer) * (ONE + CNY_SELL_SPREAD)
    cny_fees = fx.convert(Money(CNY_TRANSFER_FEE_BDT, "BDT"), payer)
    cny_conv = Money(cny_needed.amount * cny_rate, payer)
    cny = RouteCost("CNY", cny_needed, cny_rate, cny_conv, cny_fees, cny_conv + cny_fees)

    cheap, dear = (cny, usd) if cny.total.amount <= usd.total.amount else (usd, cny)
    saving = dear.total - cheap.total
    pct = saving.amount / dear.total.amount * 100 if dear.total.amount > ZERO else ZERO
    return RouteComparison(
        invoice=invoice,
        supplier_receives=cny_needed,
        payer=payer,
        usd_route=usd,
        cny_route=cny,
        cheaper=cheap.route,
        saving=saving,
        saving_pct=pct,
    )
