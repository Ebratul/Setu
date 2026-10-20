"""FR-1 financing: gap, eligibility, cost, ranking and repayment schedule. Pure Decimal logic.

Gap
  shortfall mode: amount = min_buffer − closing(first day below buffer)      (demo 1,560.00)
                  needed_by = that day; recover_on = next day closing ≥ buffer (or horizon end);
                  needed_for_days = recover_on − needed_by; peak = largest deficit in between.
  order mode:     amount = max(0, landed cost − available cash)              (demo 11,200 − 6,000)
                  needed_by = today; needed_for_days = days until milestone 3 is released.

Tenor (days) per option
  fixed (min == max) → that tenor · UNTIL_MILESTONE_3 → start … arrival + CLEARANCE_DAYS (capped at
  tenor_days_max) · ranged line (min < max) → priced at tenor_days_max (product rule, see PROGRESS).

Cost at the option's tenor d on principal P (each term only when the option sets it)
  interest = P × annual_rate × d / 365
  fees     = P × fee_rate + fee_fixed
  uplift   = P × price_uplift_rate        (supplier credit: goods priced higher)
  flat     = P × flat_cost_rate           (insured terms)
  total    = interest + fees + uplift + flat
  per_30_days = total × 30 / d
  effective_annual_rate = (1 + total / P) ^ (365 / d) − 1, capped at 999,900%

Eligibility = the option's JSON rule tree {"all": [{fact, op, value}]} plus code rules:
  min/max amount, tenor ≥ needed_for_days, and INSURED_SUPPLIER_TERMS not offered once the deal's
  escrow is funded (open-account terms replace escrow).

Ranking: eligible first, then total cost, then shorter tenor, then fewer conditions, then code.
Schedule: one bullet repayment of principal + total cost at start + tenor.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.cashflow import Forecast
from app.domain.money import ONE, ZERO, Money, q2
from app.domain.narrative import bn, p1

CLEARANCE_DAYS = 5
DAYS_PER_YEAR = Decimal(365)
THIRTY = Decimal(30)
EAR_CAP = Decimal(9999)  # 999,900%: tiny principals with fixed fees explode the formula


@dataclass(frozen=True, slots=True)
class Gap:
    mode: str
    amount: Money
    needed_by: date
    needed_for_days: int
    recover_on: date | None
    peak: Money
    facts: tuple[str, ...]


def shortfall_gap(fc: Forecast, buffer: Money) -> Gap | None:
    days = fc.days
    first = next((i for i, d in enumerate(days) if d.closing.amount < buffer.amount), None)
    if first is None:
        return None
    start = days[first]
    recover = next((d for d in days[first + 1 :] if d.closing.amount >= buffer.amount), None)
    window = days[first : days.index(recover)] if recover else days[first:]
    worst = min(window, key=lambda d: d.closing.amount)
    end = recover.on if recover else days[-1].on
    amount = Money(buffer.amount - start.closing.amount, buffer.currency)
    peak = Money(buffer.amount - worst.closing.amount, buffer.currency)
    return Gap(
        "shortfall",
        amount,
        start.on,
        max(1, (end - start.on).days),
        recover.on if recover else None,
        peak,
        (
            f"first day below buffer {start.on}: closing {start.closing.format()}",
            f"shortfall = buffer {buffer.format()} − closing = {amount.format()}",
            f"balance recovers on {recover.on}" if recover else "no recovery inside the forecast",
            f"largest deficit until then {peak.format()} on {worst.on}",
        ),
    )


def order_gap(landed: Money, cash: Money, today: date, release_on: date) -> Gap:
    amount = Money(max(ZERO, landed.amount - cash.amount), landed.currency)
    return Gap(
        "order",
        amount,
        today,
        max(1, (release_on - today).days),
        release_on,
        amount,
        (
            f"order gap = landed cost {landed.format()} − available cash {cash.format()} "
            f"= {amount.format()}",
            f"needed from {today} until milestone 3 is released (~{release_on})",
        ),
    )


@dataclass(frozen=True, slots=True)
class Terms:
    code: str
    kind: str
    annual_rate: Decimal | None = None
    flat_cost_rate: Decimal | None = None
    price_uplift_rate: Decimal | None = None
    fee_rate: Decimal | None = None
    fee_fixed: Decimal | None = None
    tenor_days_min: int | None = None
    tenor_days_max: int | None = None
    tenor_rule: str | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    collateral: str = ""
    conditions: str = ""
    eligibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def condition_count(self) -> int:
        rules = len(self.eligibility.get("all", []))
        return rules + (0 if self.collateral.strip().lower() in ("", "none") else 1)


def option_tenor(t: Terms, start: date, milestone3_release: date | None) -> int:
    if t.tenor_rule == "UNTIL_MILESTONE_3" and milestone3_release is not None:
        days = max(1, (milestone3_release - start).days)
        return min(days, t.tenor_days_max) if t.tenor_days_max else days
    if t.tenor_days_max is not None:
        return t.tenor_days_max
    if t.tenor_days_min is not None:
        return t.tenor_days_min
    raise ValueError(f"option {t.code} has no tenor")


@dataclass(frozen=True, slots=True)
class Cost:
    principal: Money
    days: int
    interest: Money
    fees: Money
    uplift: Money
    flat: Money
    total: Money
    per_30_days: Money
    effective_annual_rate: Decimal
    facts: tuple[str, ...]


def option_cost(t: Terms, principal: Money, days: int) -> Cost:
    if days <= 0:
        raise ValueError("tenor must be positive")
    if principal.amount <= ZERO:
        raise ValueError("principal must be positive")
    p, ccy, d = principal.amount, principal.currency, Decimal(days)
    interest = p * (t.annual_rate or ZERO) * d / DAYS_PER_YEAR
    fees = p * (t.fee_rate or ZERO) + (t.fee_fixed or ZERO)
    uplift = p * (t.price_uplift_rate or ZERO)
    flat = p * (t.flat_cost_rate or ZERO)
    total = interest + fees + uplift + flat
    ear = min((ONE + total / p) ** (DAYS_PER_YEAR / d) - ONE, EAR_CAP)
    facts = (
        f"principal {principal.format()} for {days} days",
        f"interest = P × {t.annual_rate or 0} × {days}/365 = {Money(interest, ccy).format()}",
        f"fees = P × {t.fee_rate or 0} + {t.fee_fixed or 0} = {Money(fees, ccy).format()}",
        f"price uplift = P × {t.price_uplift_rate or 0} = {Money(uplift, ccy).format()}",
        f"flat cost = P × {t.flat_cost_rate or 0} = {Money(flat, ccy).format()}",
        f"total = {Money(total, ccy).format()}; effective annual rate "
        f"(1 + total/P)^(365/{days}) − 1 = {q2(ear * 100)}%",
    )
    return Cost(
        principal,
        days,
        Money(interest, ccy),
        Money(fees, ccy),
        Money(uplift, ccy),
        Money(flat, ccy),
        Money(total, ccy),
        Money(total * THIRTY / d, ccy),
        ear,
        facts,
    )


@dataclass(frozen=True, slots=True)
class Check:
    code: str
    ok: bool
    en: str
    bn: str
    params: dict[str, str]


FACT_TEXT: dict[str, tuple[str, str]] = {
    "supplier_code": ("Offered only for supplier {value}", "শুধু সরবরাহকারী {value}-এর জন্য"),
    "supplier_kyb_status": (
        "Supplier KYB must be {value} (it is {actual})",
        "সরবরাহকারীর কেওয়াইবি {value} হতে হবে (এখন {actual})",
    ),
    "buyer_kyb_status": (
        "Your KYB must be {value} (it is {actual})",
        "আপনার কেওয়াইবি {value} হতে হবে (এখন {actual})",
    ),
    "completed_deals_with_supplier": (
        "Needs {value}+ completed deals with this supplier (you have {actual})",
        "এই সরবরাহকারীর সাথে অন্তত {value}টি সম্পন্ন চুক্তি লাগবে (আপনার আছে {actual}টি)",
    ),
    "completed_deals_total": (
        "Needs {value}+ completed deals (you have {actual})",
        "অন্তত {value}টি সম্পন্ন চুক্তি লাগবে (আপনার আছে {actual}টি)",
    ),
    "escrow_funded": (
        "Needs a funded Setu escrow for this deal",
        "এই চুক্তির জন্য অর্থায়িত সেতু এসক্রো লাগবে",
    ),
    "amount_usd": ("Amount must be at least USD {value}", "পরিমাণ অন্তত USD {value} হতে হবে"),
    "months_trading": (
        "Needs {value}+ months of trading history (you have {actual})",
        "অন্তত {value} মাসের ব্যবসার ইতিহাস লাগবে (আপনার আছে {actual} মাস)",
    ),
}


def _compare(op: str, actual: Any, value: Any) -> bool:
    if isinstance(actual, Decimal) or (isinstance(value, str) and _is_decimal(value)):
        actual, value = Decimal(str(actual)), Decimal(str(value))
    if op == "eq":
        return bool(actual == value)
    if op == "gte":
        return bool(actual >= value)
    if op == "lte":
        return bool(actual <= value)
    if op == "in":
        return actual in value
    raise ValueError(f"unknown op {op}")


def _is_decimal(s: str) -> bool:
    try:
        Decimal(s)
    except ArithmeticError:
        return False
    return True


def _fmt(v: Any) -> str:
    return "yes" if v is True else "no" if v is False else str(v)


def evaluate_rules(tree: Mapping[str, Any], facts: Mapping[str, Any]) -> list[Check]:
    out = []
    for r in tree.get("all", []):
        fact, op, value = r["fact"], r["op"], r["value"]
        if fact not in facts:
            out.append(Check(f"MISSING_{fact.upper()}", False, f"Unknown fact {fact}", fact, {}))
            continue
        actual = facts[fact]
        ok = _compare(op, actual, value)
        en, bn_ = FACT_TEXT.get(fact, (f"{fact} {op} {{value}}", f"{fact} {op} {{value}}"))
        params = {"value": _fmt(value), "actual": _fmt(actual)}
        out.append(
            Check(f"RULE_{fact.upper()}", ok, en.format(**params), bn(bn_.format(**params)), params)
        )
    return out


def code_rules(
    t: Terms, amount: Money, tenor: int, needed_days: int, escrow_funded: bool
) -> list[Check]:
    out = []
    a = q2(amount.amount)
    if t.min_amount is not None:
        lo = q2(t.min_amount)
        out.append(
            Check(
                "MIN_AMOUNT",
                a >= lo,
                f"Minimum amount {amount.currency} {lo:,}",
                bn(f"সর্বনিম্ন পরিমাণ {amount.currency} {lo:,}"),
                {"min": f"{lo}", "amount": f"{a}"},
            )
        )
    if t.max_amount is not None:
        hi = q2(t.max_amount)
        out.append(
            Check(
                "MAX_AMOUNT",
                a <= hi,
                f"Maximum amount {amount.currency} {hi:,}",
                bn(f"সর্বোচ্চ পরিমাণ {amount.currency} {hi:,}"),
                {"max": f"{hi}", "amount": f"{a}"},
            )
        )
    out.append(
        Check(
            "TENOR_FITS",
            tenor >= needed_days,
            f"Tenor {tenor} days must cover the {needed_days} days you need the money",
            bn(f"মেয়াদ {tenor} দিন, আপনার প্রয়োজন {needed_days} দিন"),
            {"tenor": str(tenor), "needed": str(needed_days)},
        )
    )
    if t.kind == "INSURED_SUPPLIER_TERMS":
        out.append(
            Check(
                "NOT_WITH_FUNDED_ESCROW",
                not escrow_funded,
                "Open-account insured terms replace escrow; not offered once escrow is funded",
                "ইনস্যুরড ওপেন-অ্যাকাউন্ট শর্ত এসক্রোর বিকল্প; এসক্রো অর্থায়িত হলে প্রযোজ্য নয়",
                {"escrow_funded": _fmt(escrow_funded)},
            )
        )
    return out


@dataclass(frozen=True, slots=True)
class Quote:
    terms: Terms
    cost: Cost
    checks: tuple[Check, ...]
    start: date

    @property
    def eligible(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.ok)

    @property
    def maturity(self) -> date:
        return self.start + timedelta(days=self.cost.days)


def rank(quotes: Sequence[Quote]) -> list[Quote]:
    return sorted(
        quotes,
        key=lambda q: (
            not q.eligible,
            q.cost.total.amount,
            q.cost.days,
            q.terms.condition_count,
            q.terms.code,
        ),
    )


@dataclass(frozen=True, slots=True)
class Instalment:
    due_on: date
    principal: Money
    cost: Money

    @property
    def total(self) -> Money:
        return self.principal + self.cost


def schedule(cost: Cost, start: date) -> list[Instalment]:
    return [Instalment(start + timedelta(days=cost.days), cost.principal, cost.total)]


def why_codes(pick: Quote, nxt: Quote | None) -> list[str]:
    t = pick.terms
    codes = (
        ["LOWEST_COST"] if nxt is None or pick.cost.total.amount <= nxt.cost.total.amount else []
    )
    if t.collateral.strip().lower() in ("", "none"):
        codes.append("NO_COLLATERAL")
    if t.kind == "ESCROW_BACKED_LOAN":
        codes.append("USES_ESCROW")
    if (t.annual_rate or ZERO) == ZERO and t.kind != "INSURED_SUPPLIER_TERMS":
        codes.append("NO_INTEREST")
    if t.tenor_rule == "UNTIL_MILESTONE_3":
        codes.append("MATCHES_DEAL_TIMELINE")
    return codes


WHY_TEXT: dict[str, tuple[str, str]] = {
    "LOWEST_COST": (
        "Lowest total cost of the eligible options.",
        "যোগ্য বিকল্পগুলোর মধ্যে মোট খরচ সবচেয়ে কম।",
    ),
    "NO_COLLATERAL": ("No collateral needed.", "জামানত লাগে না।"),
    "USES_ESCROW": (
        "Secured by your funded Setu escrow, not by your property.",
        "আপনার সম্পত্তি নয়, অর্থায়িত সেতু এসক্রো জামানত হিসেবে কাজ করে।",
    ),
    "NO_INTEREST": ("No interest is charged.", "কোনো সুদ নেই।"),
    "MATCHES_DEAL_TIMELINE": (
        "Repaid when milestone 3 is released, so it follows the deal timeline.",
        "মাইলস্টোন ৩ ছাড় হলে পরিশোধ, তাই চুক্তির সময়সূচির সাথে মেলে।",
    ),
}


def pick_sentences(pick: Quote, nxt: Quote | None, name: str) -> list[tuple[str, str, str]]:
    total = pick.cost.total.format()
    out = [
        (
            "PICK",
            f"Recommended: {name}, total cost {total} over {pick.cost.days} days.",
            bn(f"প্রস্তাবিত: {name}, {pick.cost.days} দিনে মোট খরচ {total}।"),
        )
    ]
    if nxt is not None:
        saving = (nxt.cost.total - pick.cost.total).format()
        out.append(
            (
                "SAVING_VS_NEXT",
                f"That is {saving} cheaper than the next eligible option.",
                bn(f"পরবর্তী যোগ্য বিকল্পের চেয়ে {saving} কম।"),
            )
        )
    for code in why_codes(pick, nxt):
        en, bn_ = WHY_TEXT[code]
        out.append((code, en, bn_))
    return out


def risk_notes(q: Quote) -> list[tuple[str, str, str]]:
    t = q.terms
    out = []
    if t.price_uplift_rate:
        pct = p1(t.price_uplift_rate)
        out.append(
            (
                "PRICE_UPLIFT",
                f"Supplier credit raises the unit price by {pct}%.",
                bn(f"সাপ্লায়ার ক্রেডিটে একক মূল্য {pct}% বাড়ে।"),
            )
        )
    if t.kind == "ESCROW_BACKED_LOAN":
        out.append(
            (
                "ESCROW_ASSIGNED",
                "Your escrow tranches are assigned to the lender until repayment.",
                "পরিশোধ না হওয়া পর্যন্ত এসক্রো কিস্তিগুলো ঋণদাতার কাছে হস্তান্তরিত থাকে।",
            )
        )
    if t.collateral.strip().lower() not in ("", "none") and t.kind != "ESCROW_BACKED_LOAN":
        out.append(
            (
                "COLLATERAL",
                f"Collateral: {t.collateral}.",
                f"জামানত: {t.collateral}।",
            )
        )
    if t.tenor_days_min is not None and t.tenor_days_max and t.tenor_days_min < t.tenor_days_max:
        out.append(
            (
                "PRICED_AT_MAX_TENOR",
                f"Priced at the maximum {t.tenor_days_max}-day tenor; repaying early costs less.",
                bn(f"সর্বোচ্চ {t.tenor_days_max} দিনের মেয়াদে হিসাব; আগে পরিশোধে খরচ কম।"),
            )
        )
    if q.cost.effective_annual_rate > Decimal("0.13"):
        ear = q2(q.cost.effective_annual_rate * 100)
        out.append(
            (
                "HIGH_EFFECTIVE_RATE",
                f"High effective annual rate ({ear}%).",
                bn(f"কার্যকর বার্ষিক হার বেশি ({ear}%)।"),
            )
        )
    return out
