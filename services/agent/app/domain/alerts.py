"""Cash-flow alert rules (FR-2). Pure: forecast + deadlines + FX series in, alert drafts out.

SHORTFALL      one alert for the first day closing(d) < min_buffer in the horizon.
               amount = min_buffer − closing(d) (for SETU-2026-0001 M2: 0 − (−1,560) = 1,560);
               facts also carry the lowest balance of the horizon and its date.
               CRITICAL when the day is ≤ 7 days away, else WARNING.
DEADLINE       per rule (action window, notice window) in days before the due date:
                 milestone payment (14, 30) · customs duty (7, 60) · bill of entry (7, 60) ·
                 loan instalment (7, 7).
               INFO inside the notice window, WARNING inside the action window, CRITICAL at T-1/T-0.
               Bill of entry is due arrival date + BOE_DAYS_AFTER_ARRIVAL.
FX_OPPORTUNITY before the next tranche of each deal paid in a foreign currency, the cheapest
               day (lowest <ccy>/BDT, history or mock forecast, today ≤ d < due) is more than
               FX_THRESHOLD below the 30-day mean: "pay on <d>",
               saving ≈ amount × (mean − rate) BDT.

Keys are stable (`alert:<party>:<type>:<reference>:<date>`), so re-running the engine upserts.
Milestone DEADLINE alerts are dropped when the SHORTFALL alert is about that same payment.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.cashflow import Forecast
from app.domain.money import ZERO, Money
from app.domain.narrative import bn, p1

SHORTFALL_CRITICAL_DAYS = 7
DEADLINE_CRITICAL_DAYS = 1
BOE_DAYS_AFTER_ARRIVAL = 1
FX_THRESHOLD = Decimal("0.01")
DeadlineKind = Literal["MILESTONE", "DUTY", "BILL_OF_ENTRY", "LOAN"]
DEADLINE_RULES: dict[DeadlineKind, tuple[int, int]] = {
    "MILESTONE": (14, 30),
    "DUTY": (7, 60),
    "BILL_OF_ENTRY": (7, 60),
    "LOAN": (7, 7),
}
ENGINE_TYPES = ("SHORTFALL", "DEADLINE", "FX_OPPORTUNITY")


@dataclass(frozen=True, slots=True)
class Action:
    code: str
    route: str
    query: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlertDraft:
    key: str
    type: str
    severity: str
    title_en: str
    title_bn: str
    message_en: str
    message_bn: str
    amount: Money | None
    due_on: date
    action: Action
    deal_ref: str | None = None
    milestone_seq: int | None = None
    facts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Deadline:
    kind: DeadlineKind
    due: date
    amount: Money | None
    deal_ref: str | None = None
    milestone_seq: int | None = None


@dataclass(frozen=True, slots=True)
class FxPayment:
    deal_ref: str
    milestone_seq: int
    due: date
    amount: Money
    points: tuple[tuple[date, Decimal], ...]
    mean_30d: Decimal
    source: str = "MOCK"


KEY_MAX = 80


def key(party: str, kind: str, reference: str, on: date) -> str:
    """Stable alert key; hashed when it would not fit the 80-char column (long party codes)."""
    raw = f"alert:{party}:{kind}:{reference}:{on.isoformat()}"
    if len(raw) <= KEY_MAX:
        return raw
    return f"alert:{kind}:{hashlib.sha256(raw.encode()).hexdigest()[:48]}"


def m(x: Money) -> str:
    return x.format()


def shortfall_alerts(party: str, fc: Forecast, buffer: Money, today: date) -> list[AlertDraft]:
    out: list[AlertDraft] = []
    start = next((d for d in fc.days if d.closing.amount < buffer.amount), None)
    episodes = [(start, fc.lowest)] if start is not None else []
    for start, low in episodes:
        amount = Money(buffer.amount - start.closing.amount, buffer.currency)
        available = start.opening + start.inflow
        outs = [f for f in start.items if f.direction == "OUT"]
        trigger = max(outs, key=lambda f: f.amount.amount) if outs else None
        days = (start.on - today).days
        on = start.on.isoformat()
        what_en = trigger.label if trigger else "Planned payments"
        what_bn = (
            f"{trigger.deal_ref} মাইলস্টোন {trigger.milestone_seq}"
            if trigger and trigger.milestone_seq
            else "পরিকল্পিত খরচ"
        )
        due = trigger.amount if trigger else start.outflow
        query = {"amount": f"{amount.quantized().amount}", "currency": amount.currency, "date": on}
        if trigger and trigger.deal_ref:
            query["deal"] = trigger.deal_ref
        out.append(
            AlertDraft(
                key=key(party, "shortfall", "balance", start.on),
                type="SHORTFALL",
                severity="CRITICAL" if days <= SHORTFALL_CRITICAL_DAYS else "WARNING",
                title_en=f"Cash shortfall of {m(amount)} on {on}",
                title_bn=bn(f"{on} তারিখে {m(amount)} নগদ ঘাটতি"),
                message_en=(
                    f"On {on} {what_en} needs {m(due)}, but your projected balance is "
                    f"{m(available)}. Shortfall: {m(amount)}."
                ),
                message_bn=bn(
                    f"{on} তারিখে {what_bn}-এর জন্য {m(due)} লাগবে, কিন্তু আপনার আনুমানিক "
                    f"ব্যালেন্স {m(available)}। ঘাটতি: {m(amount)}।"
                ),
                amount=amount.quantized(),
                due_on=start.on,
                action=Action("COMPARE_FINANCING", "/app/financing", query),
                deal_ref=trigger.deal_ref if trigger else None,
                milestone_seq=trigger.milestone_seq if trigger else None,
                facts={
                    "date": on,
                    "balance": f"{available.quantized().amount}",
                    "due": f"{due.quantized().amount}",
                    "shortfall": f"{amount.quantized().amount}",
                    "min_buffer": f"{buffer.quantized().amount}",
                    "lowest_balance": f"{low.closing.quantized().amount}",
                    "lowest_on": low.on.isoformat(),
                    "days_away": str(days),
                },
            )
        )
    return out


def _deadline_text(d: Deadline, days: int) -> tuple[str, str, str, str]:
    on = d.due.isoformat()
    amt = m(d.amount) if d.amount else ""
    when_en = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
    when_bn = "আজ" if days == 0 else ("আগামীকাল" if days == 1 else f"{days} দিন পর")
    ref = d.deal_ref or ""
    if d.kind == "MILESTONE":
        return (
            f"Milestone {d.milestone_seq} payment {amt} due {on}",
            bn(f"মাইলস্টোন {d.milestone_seq}-এর {amt} পরিশোধ {on}"),
            f"Fund escrow milestone {d.milestone_seq} of {ref} ({amt}) {when_en}.",
            bn(f"{ref}-এর এসক্রো মাইলস্টোন {d.milestone_seq} ({amt}) {when_bn} জমা দিতে হবে।"),
        )
    if d.kind == "DUTY":
        return (
            f"Customs duty {amt} due {on}",
            bn(f"শুল্ক {amt} পরিশোধের শেষ তারিখ {on}"),
            f"Import duty for {ref} ({amt}) is due {when_en}, 5 days after arrival.",
            bn(f"{ref}-এর আমদানি শুল্ক ({amt}) {when_bn} পরিশোধ করতে হবে।"),
        )
    if d.kind == "BILL_OF_ENTRY":
        return (
            f"File the bill of entry by {on}",
            bn(f"{on}-এর মধ্যে বিল অব এন্ট্রি জমা দিন"),
            f"Lodge the bill of entry for {ref} {when_en}; it is the evidence for the arrival "
            f"milestone.",
            bn(f"{ref}-এর বিল অব এন্ট্রি {when_bn} জমা দিন; এটি আগমন মাইলস্টোনের প্রমাণপত্র।"),
        )
    return (
        f"Loan instalment {amt} due {on}",
        bn(f"ঋণের কিস্তি {amt} পরিশোধ {on}"),
        f"A loan instalment of {amt} is due {when_en}.",
        bn(f"{amt} ঋণের কিস্তি {when_bn} পরিশোধ করতে হবে।"),
    )


def deadline_alerts(party: str, deadlines: Sequence[Deadline], today: date) -> list[AlertDraft]:
    out = []
    for d in sorted(deadlines, key=lambda x: (x.due, x.kind, x.deal_ref or "")):
        warn, notice = DEADLINE_RULES[d.kind]
        days = (d.due - today).days
        if not 0 <= days <= notice:
            continue
        if days <= DEADLINE_CRITICAL_DAYS:
            severity = "CRITICAL"
        elif days <= warn:
            severity = "WARNING"
        else:
            severity = "INFO"
        reference = {
            "MILESTONE": f"{d.deal_ref}:m{d.milestone_seq}",
            "DUTY": f"{d.deal_ref}:duty",
            "BILL_OF_ENTRY": f"{d.deal_ref}:boe",
            "LOAN": "loan",
        }[d.kind]
        action = {
            "MILESTONE": Action("FUND_MILESTONE", f"/app/orders/{d.deal_ref}"),
            "DUTY": Action("PLAN_DUTY_PAYMENT", "/app/cashflow", {"date": d.due.isoformat()}),
            "BILL_OF_ENTRY": Action("UPLOAD_BILL_OF_ENTRY", f"/app/orders/{d.deal_ref}"),
            "LOAN": Action("REVIEW_CASHFLOW", "/app/cashflow", {"date": d.due.isoformat()}),
        }[d.kind]
        t_en, t_bn, m_en, m_bn = _deadline_text(d, days)
        out.append(
            AlertDraft(
                key=key(party, "deadline", reference, d.due),
                type="DEADLINE",
                severity=severity,
                title_en=t_en,
                title_bn=t_bn,
                message_en=m_en,
                message_bn=m_bn,
                amount=d.amount.quantized() if d.amount else None,
                due_on=d.due,
                action=action,
                deal_ref=d.deal_ref,
                milestone_seq=d.milestone_seq,
                facts={
                    "deadline": d.kind,
                    "due": d.due.isoformat(),
                    "days_away": str(days),
                    "window_days": str(warn),
                    "notice_days": str(notice),
                },
            )
        )
    return out


def fx_alerts(
    party: str, payments: Sequence[FxPayment], today: date, threshold: Decimal = FX_THRESHOLD
) -> list[AlertDraft]:
    out = []
    for p in payments:
        window = [(d, r) for d, r in p.points if today <= d < p.due]
        if not window or p.mean_30d <= ZERO:
            continue
        best_on, best = min(window, key=lambda x: (x[1], x[0]))
        gain = (p.mean_30d - best) / p.mean_30d
        if gain <= threshold:
            continue
        ccy = p.amount.currency
        saving = Money(p.amount.amount * (p.mean_30d - best), "BDT").quantized()
        on, pct, pair = best_on.isoformat(), p1(gain), f"{ccy}/BDT"
        out.append(
            AlertDraft(
                key=key(party, "fx", f"{p.deal_ref}:m{p.milestone_seq}", best_on),
                type="FX_OPPORTUNITY",
                severity="INFO",
                title_en=f"Good day to buy {ccy}: {on}",
                title_bn=bn(f"{ccy} কেনার ভালো দিন: {on}"),
                message_en=(
                    f"Mock forecast: {pair} {best} on {on}, {pct}% below the 30-day average of "
                    f"{p.mean_30d.quantize(Decimal('0.0001'))}. Pay or lock milestone "
                    f"{p.milestone_seq} of {p.deal_ref} ({m(p.amount)}) on {on} to save "
                    f"≈ {m(saving)}."
                ),
                message_bn=bn(
                    f"মক পূর্বাভাস: {on} তারিখে {pair} {best}, যা ৩০ দিনের গড়ের চেয়ে {pct}% কম। "
                    f"{p.deal_ref}-এর মাইলস্টোন {p.milestone_seq} ({m(p.amount)}) ওই দিন "
                    f"পরিশোধ বা রেট লক করলে প্রায় {m(saving)} সাশ্রয় হবে।"
                ),
                amount=saving,
                due_on=best_on,
                action=Action("REVIEW_FX_TIMING", "/app/cashflow", {"date": on}),
                deal_ref=p.deal_ref,
                milestone_seq=p.milestone_seq,
                facts={
                    "pair": pair,
                    "rate": f"{best}",
                    "mean_30d": f"{p.mean_30d.quantize(Decimal('0.0001'))}",
                    "change_pct": f"-{pct}",
                    "payment": f"{p.amount.quantized().amount}",
                    "payment_due": p.due.isoformat(),
                    "saving_bdt": f"{saving.amount}",
                    "source": p.source,
                },
            )
        )
    return out
