"""FR-2 forecaster: loads a buyer's flows, deadlines and FX inputs, computes with app/domain.

Flow sources (all converted to the buyer's cash currency):
- cashflow_items dated today or later that are *not* linked to a milestone or deal cost
  (sales, salary, rent, utilities, loan repayments, local purchases, other);
- active deals (FUNDED, IN_PRODUCTION, SHIPPED, ARRIVED): each tranche not yet deposited into escrow
  (beyond escrow.funded_total, status not RELEASED/REFUNDED/CANCELLED) on its due date, and each
  deal cost on its due date. The seed's linked cashflow_items rows mirror exactly these, so they are
  skipped to avoid double counting.
Repayments of approved financing are not modelled yet (no financing-application table).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import DealStatus, FlowDirection, FxKind, MilestoneStatus, MilestoneTrigger
from app.db.models import (
    BankAccount,
    CashflowItem,
    Deal,
    DealCost,
    EscrowAccount,
    FxRate,
    Milestone,
    Party,
)
from app.domain.alerts import BOE_DAYS_AFTER_ARRIVAL, Deadline, FxPayment
from app.domain.cashflow import Flow, Forecast, Loan, Move, UnknownFlow, apply_scenario, forecast
from app.domain.fx import FxTable
from app.domain.money import ZERO, Currency, Money
from app.errors import DomainError
from app.schemas.cashflow import (
    DayOut,
    FlowOut,
    ForecastOut,
    ScenarioRequest,
    ShortfallOut,
    WeekOut,
)
from app.services.analysis import fmt, fx_table
from app.services.scope import demo_today, require_buyer

ACTIVE = (
    DealStatus.FUNDED,
    DealStatus.IN_PRODUCTION,
    DealStatus.SHIPPED,
    DealStatus.ARRIVED,
)
SETTLED = (MilestoneStatus.RELEASED, MilestoneStatus.REFUNDED, MilestoneStatus.CANCELLED)
DEFAULT_DAYS = 90
FX_MEAN_DAYS = 30


@dataclass(frozen=True, slots=True)
class BuyerBook:
    """Everything the forecaster and alert engine need for one buyer on one day."""

    buyer: Party
    today: date
    currency: Currency
    fx: FxTable
    flows: list[Flow]
    arrivals: list[tuple[str, date]]
    pay_currency: dict[str, Currency]


def currency_of(buyer: Party) -> Currency:
    return cast(Currency, buyer.cash_currency or "USD")


def active_deals(db: Session, buyer: Party) -> list[Deal]:
    return list(
        db.scalars(
            select(Deal)
            .where(Deal.buyer_id == buyer.id, Deal.status.in_(ACTIVE))
            .order_by(Deal.reference)
        ).all()
    )


def unfunded_milestones(db: Session, deal: Deal) -> list[Milestone]:
    escrow = db.scalar(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id))
    funded = escrow.funded_total if escrow else ZERO
    out, cumulative = [], ZERO
    for ms in db.scalars(
        select(Milestone).where(Milestone.deal_id == deal.id).order_by(Milestone.seq)
    ).all():
        cumulative += ms.amount
        if cumulative > funded and ms.status not in SETTLED:
            out.append(ms)
    return out


def load_book(db: Session, buyer: Party) -> BuyerBook:
    today = demo_today(db)
    fx = fx_table(db, today)
    ccy = currency_of(buyer)

    def conv(amount: Decimal, currency: str) -> Money:
        return fx.convert(Money(amount, cast(Currency, currency)), ccy)

    flows: list[Flow] = []
    for item in db.scalars(
        select(CashflowItem)
        .where(
            CashflowItem.party_id == buyer.id,
            CashflowItem.on_date >= today,
            CashflowItem.milestone_id.is_(None),
            CashflowItem.deal_cost_id.is_(None),
        )
        .order_by(CashflowItem.on_date, CashflowItem.key)
    ).all():
        flows.append(
            Flow(
                f"cf:{item.key}",
                item.on_date,
                "IN" if item.direction == FlowDirection.IN else "OUT",
                conv(item.amount, item.currency),
                item.kind,
                item.description,
            )
        )

    arrivals: list[tuple[str, date]] = []
    pay_currency: dict[str, Currency] = {}
    for deal in active_deals(db, buyer):
        account = (
            db.get(BankAccount, deal.beneficiary_account_id)
            if deal.beneficiary_account_id
            else None
        )
        pay_currency[deal.reference] = cast(
            Currency, account.currency if account else deal.currency
        )
        for ms in unfunded_milestones(db, deal):
            if ms.due_on >= today:
                flows.append(
                    Flow(
                        f"milestone:{deal.reference}:{ms.seq}",
                        ms.due_on,
                        "OUT",
                        conv(ms.amount, ms.currency),
                        "MILESTONE_PAYMENT",
                        f"Fund escrow milestone {ms.seq} · {deal.reference}",
                        deal.reference,
                        ms.seq,
                    )
                )
        for cost in db.scalars(select(DealCost).where(DealCost.deal_id == deal.id)).all():
            if cost.due_on is not None and cost.due_on >= today and cost.amount > ZERO:
                flows.append(
                    Flow(
                        f"cost:{deal.reference}:{cost.kind}",
                        cost.due_on,
                        "OUT",
                        conv(cost.amount, cost.currency),
                        cost.kind,
                        f"{cost.note or cost.kind} · {deal.reference}",
                        deal.reference,
                    )
                )
        arrival = db.scalar(
            select(Milestone).where(
                Milestone.deal_id == deal.id, Milestone.trigger == MilestoneTrigger.ARRIVAL
            )
        )
        if arrival is not None and arrival.status not in SETTLED:
            arrivals.append((deal.reference, arrival.due_on))
    return BuyerBook(buyer, today, ccy, fx, flows, arrivals, pay_currency)


def opening(book: BuyerBook) -> Money:
    b = book.buyer
    return book.fx.convert(
        Money(b.cash_balance or ZERO, cast(Currency, b.cash_currency or "USD")), book.currency
    )


def deadlines(book: BuyerBook) -> list[Deadline]:
    out = []
    for f in book.flows:
        if f.kind == "MILESTONE_PAYMENT":
            out.append(Deadline("MILESTONE", f.on, f.amount, f.deal_ref, f.milestone_seq))
        elif f.kind == "DUTY":
            out.append(Deadline("DUTY", f.on, f.amount, f.deal_ref))
        elif f.kind == "LOAN_REPAYMENT":
            out.append(Deadline("LOAN", f.on, f.amount))
    for ref, arrival in book.arrivals:
        out.append(
            Deadline("BILL_OF_ENTRY", arrival + timedelta(days=BOE_DAYS_AFTER_ARRIVAL), None, ref)
        )
    return out


def fx_payments(db: Session, book: BuyerBook) -> list[FxPayment]:
    """Next upcoming tranche per deal paid into a foreign-currency (non-BDT) account."""
    out = []
    seen: set[str] = set()
    series_cache: dict[str, tuple[tuple[tuple[date, Decimal], ...], Decimal] | None] = {}
    for f in sorted(book.flows, key=lambda x: (x.on, x.ref)):
        if f.kind != "MILESTONE_PAYMENT" or f.deal_ref is None or f.milestone_seq is None:
            continue
        if f.deal_ref in seen:
            continue
        seen.add(f.deal_ref)
        pay = book.pay_currency.get(f.deal_ref, book.currency)
        if pay in ("BDT", book.currency):
            continue
        if pay not in series_cache:
            series_cache[pay] = _series(db, pay, book.today)
        series = series_cache[pay]
        if series is None:
            continue
        points, mean = series
        out.append(
            FxPayment(
                f.deal_ref, f.milestone_seq, f.on, book.fx.convert(f.amount, pay), points, mean
            )
        )
    return out


def _series(
    db: Session, ccy: Currency, today: date
) -> tuple[tuple[tuple[date, Decimal], ...], Decimal] | None:
    rows = db.scalars(
        select(FxRate)
        .where(FxRate.base == ccy, FxRate.quote == "BDT")
        .order_by(FxRate.as_of, FxRate.kind)
    ).all()
    history = [
        r.rate
        for r in rows
        if r.kind == FxKind.HISTORY and today - timedelta(days=FX_MEAN_DAYS - 1) <= r.as_of <= today
    ]
    if not history:
        return None
    points: dict[date, Decimal] = {}
    for r in rows:
        if (r.as_of == today and r.kind == FxKind.HISTORY) or (
            r.as_of > today and r.kind == FxKind.FORECAST
        ):
            points[r.as_of] = r.rate.normalize()
    mean = sum(history, ZERO) / Decimal(len(history))
    return tuple(sorted(points.items())), mean


def scenario_flows(
    flows: Sequence[Flow], req: ScenarioRequest, ccy: Currency, today: date
) -> list[Flow]:
    end = today + timedelta(days=req.days)
    for ln in req.loans:
        if not today <= ln.on <= end:
            raise DomainError("loan date must be inside the forecast window")
        if ln.repay_on is not None and ln.repay_on < ln.on:
            raise DomainError("loan repayment cannot be before the loan date")
        if Decimal(ln.amount) <= ZERO or (ln.repay_amount and Decimal(ln.repay_amount) <= ZERO):
            raise DomainError("loan amounts must be greater than 0")
    for mv in req.moves:
        if not today <= mv.on <= end:
            raise DomainError("moved dates must be inside the forecast window")
    try:
        return apply_scenario(
            flows,
            [Move(mv.ref, mv.on) for mv in req.moves],
            req.removes,
            [
                Loan(
                    Money(Decimal(ln.amount), ccy),
                    ln.on,
                    ln.repay_on,
                    Money(Decimal(ln.repay_amount), ccy) if ln.repay_amount else None,
                )
                for ln in req.loans
            ],
        )
    except UnknownFlow as exc:
        raise DomainError(str(exc)) from exc
    except ValueError as exc:
        raise DomainError(str(exc)) from exc


def compute(book: BuyerBook, flows: Sequence[Flow], days: int) -> Forecast:
    return forecast(opening(book), book.today, days, flows)


def forecast_out(
    book: BuyerBook, fc: Forecast, buffer: Money, scenario: bool = False
) -> ForecastOut:
    first = next((d for d in fc.days if d.closing.amount < buffer.amount), None)
    low = fc.lowest

    def flow(f: Flow) -> FlowOut:
        return FlowOut(
            ref=f.ref,
            on=f.on,
            direction=f.direction,
            amount=fmt(f.amount.amount),
            kind=f.kind,
            label=f.label,
            deal_ref=f.deal_ref,
            milestone_seq=f.milestone_seq,
        )

    return ForecastOut(
        scenario=scenario,
        party_id=book.buyer.id,
        party_name=book.buyer.legal_name,
        currency=book.currency,
        start=fc.start,
        end=fc.days[-1].on,
        opening_balance=fmt(fc.opening.amount),
        min_buffer=fmt(buffer.amount),
        lowest_balance=fmt(low.closing.amount),
        lowest_on=low.on,
        cover_amount=fmt(max(ZERO, buffer.amount - low.closing.amount)),
        first_shortfall=ShortfallOut(on=first.on, amount=fmt(buffer.amount - first.closing.amount))
        if first
        else None,
        total_inflow=fmt(sum((d.inflow.amount for d in fc.days), ZERO)),
        total_outflow=fmt(sum((d.outflow.amount for d in fc.days), ZERO)),
        daily=[
            DayOut(
                on=d.on,
                opening=fmt(d.opening.amount),
                inflow=fmt(d.inflow.amount),
                outflow=fmt(d.outflow.amount),
                net=fmt(d.net.amount),
                closing=fmt(d.closing.amount),
                below_buffer=d.closing.amount < buffer.amount,
                items=[flow(f) for f in d.items],
            )
            for d in fc.days
        ],
        weekly=[
            WeekOut(
                start=w.start,
                end=w.end,
                inflow=fmt(w.inflow.amount),
                outflow=fmt(w.outflow.amount),
                closing=fmt(w.closing.amount),
                lowest=fmt(w.lowest.amount),
            )
            for w in fc.weeks
        ],
        facts=list(fc.facts),
    )


def buffer_of(book: BuyerBook, min_buffer: str | None) -> Money:
    return Money(Decimal(min_buffer) if min_buffer is not None else ZERO, book.currency)


def get_forecast(
    db: Session,
    user: CurrentUser,
    party_id: uuid.UUID | None,
    days: int = DEFAULT_DAYS,
    min_buffer: str | None = None,
) -> ForecastOut:
    book = load_book(db, require_buyer(db, user, party_id))
    buffer = buffer_of(book, min_buffer)
    return forecast_out(book, compute(book, book.flows, days), buffer)
