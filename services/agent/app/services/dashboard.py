"""Buyer dashboard: KPIs from the forecast, escrow, alerts, approvals and the monthly summary."""

import uuid
from datetime import timedelta
from typing import cast

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import AlertStatus, ApprovalStatus, DealStatus
from app.db.models import ApprovalRequest, Deal, EscrowAccount, Milestone
from app.domain.money import ZERO, Currency, Money, money_sum
from app.schemas.cashflow import (
    DashboardDeal,
    DashboardMonth,
    DashboardOut,
    NextMilestone,
    ShortfallOut,
)
from app.services import analysis
from app.services.alerts import alert_out, party_alerts
from app.services.cashflow import ACTIVE, DEFAULT_DAYS, compute, load_book, opening
from app.services.scope import party, require_buyer

TOP_ALERTS = 5
NEXT_DAYS = 30
OPEN_STATES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)


def dashboard(db: Session, user: CurrentUser, party_id: uuid.UUID | None) -> DashboardOut:
    buyer = require_buyer(db, user, party_id)
    book = load_book(db, buyer)
    fx, ccy = book.fx, book.currency
    fc = compute(book, book.flows, DEFAULT_DAYS)
    horizon = book.today + timedelta(days=NEXT_DAYS)
    due_30 = money_sum([d.outflow for d in fc.days if d.on < horizon], ccy)

    deals = db.scalars(
        select(Deal).where(Deal.buyer_id == buyer.id).order_by(Deal.opened_on.desc())
    ).all()
    escrow = money_sum(
        [
            fx.convert(Money(e.balance, cast(Currency, e.currency)), ccy)
            for e in db.scalars(
                select(EscrowAccount).where(
                    EscrowAccount.deal_id.in_([d.id for d in deals]) if deals else false()
                )
            ).all()
        ],
        ccy,
    )
    by_status: dict[str, int] = {}
    for d in deals:
        by_status[d.status] = by_status.get(d.status, 0) + 1

    active = []
    for d in deals:
        if d.status not in (*ACTIVE, DealStatus.DRAFT):
            continue
        ms = db.scalars(
            select(Milestone)
            .where(Milestone.deal_id == d.id, Milestone.status.in_(("PENDING", "READY", "FROZEN")))
            .order_by(Milestone.seq)
            .limit(1)
        ).first()
        active.append(
            DashboardDeal(
                reference=d.reference,
                title=d.title,
                status=d.status,
                supplier_name=party(db, d.supplier_id).legal_name,
                goods_value=analysis.amounts(Money(d.goods_value, cast(Currency, d.currency)), fx),
                next_milestone=NextMilestone(
                    seq=ms.seq,
                    trigger=ms.trigger,
                    amount=analysis.amounts(Money(ms.amount, cast(Currency, ms.currency)), fx),
                    due_on=ms.due_on,
                    status=ms.status,
                )
                if ms
                else None,
            )
        )

    pending = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .join(Deal, Deal.id == ApprovalRequest.deal_id)
            .where(Deal.buyer_id == buyer.id, ApprovalRequest.status == ApprovalStatus.PENDING)
        )
        or 0
    )
    open_alerts = party_alerts(db, buyer, OPEN_STATES)
    first = next((d for d in fc.days if d.closing.amount < ZERO), None)
    month = analysis.monthly(db, user, buyer.id, None)
    low = fc.lowest
    return DashboardOut(
        party_id=buyer.id,
        party_name=buyer.legal_name,
        currency=ccy,
        today=book.today,
        cash_balance=analysis.amounts(opening(book), fx),
        in_escrow=analysis.amounts(escrow, fx),
        due_next_30_days=analysis.amounts(due_30, fx),
        open_alerts_count=len(open_alerts),
        alerts=[alert_out(db, a) for a in open_alerts[:TOP_ALERTS]],
        pending_approvals=pending,
        deals_by_status=by_status,
        active_deals=active,
        lowest_balance=analysis.fmt(low.closing.amount),
        lowest_on=low.on,
        first_shortfall=ShortfallOut(on=first.on, amount=analysis.fmt(-first.closing.amount))
        if first
        else None,
        month=DashboardMonth(
            month=month.month,
            deals_count=month.deals_count,
            total_purchases=month.total_purchases,
            total_landed_cost=month.total_landed_cost,
            average_margin_pct=month.average_margin_pct,
        ),
    )
