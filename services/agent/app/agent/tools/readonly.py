"""Tier 0 read-only tools for P08 (prove the tool loop). They return facts and numbers only."""

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.registry import ToolContext, ToolError, ToolRegistry
from app.auth.deps import can_read_party
from app.db.models import EscrowAccount, Milestone
from app.schemas.analysis import DecStr
from app.security.tiers import Tier
from app.services import dashboard
from app.services.analysis import find_deal, fmt
from app.services.scope import party

REGISTRY = ToolRegistry()
OPEN_MILESTONES = ("PENDING", "READY", "FROZEN")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulated: Literal[True] = True


# --- get_dashboard_snapshot -----------------------------------------------------------------


class DashboardSnapshotIn(_In):
    party_id: str | None = Field(
        None,
        max_length=36,
        description="Buyer party id. Leave empty for the signed-in buyer.",
    )


class SnapshotAlert(_Out):
    type: str
    severity: str
    title: str
    amount: DecStr | None
    currency: str | None
    due_on: date | None
    deal_ref: str | None


class SnapshotDeal(_Out):
    reference: str
    status: str
    supplier_name: str
    next_milestone_seq: int | None
    next_due_on: date | None
    next_amount: DecStr | None
    next_currency: str | None


class Shortfall(_Out):
    on: date
    amount: DecStr


class DashboardSnapshotOut(_Out):
    party_name: str
    currency: str
    today: date
    cash_balance: DecStr
    in_escrow: DecStr
    due_next_30_days: DecStr
    first_shortfall: Shortfall | None
    lowest_balance: DecStr
    lowest_on: date
    open_alerts_count: int
    top_alerts: list[SnapshotAlert]
    pending_approvals: int
    active_deals: list[SnapshotDeal]


def _party_uuid(raw: str | None) -> uuid.UUID | None:
    if raw is None or raw == "":
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ToolError("not_found", "party not found") from exc


@REGISTRY.tool(
    name="get_dashboard_snapshot",
    tier=Tier.T0,
    args_schema=DashboardSnapshotIn,
    output_schema=DashboardSnapshotOut,
    tags=("dashboard",),
)
def get_dashboard_snapshot(args: DashboardSnapshotIn, ctx: ToolContext) -> DashboardSnapshotOut:
    """Simulated cash snapshot for a buyer in their home currency: cash balance, escrow, payments
    due in 30 days, first shortfall (date and amount), lowest balance, top open alerts, pending
    approvals and active deals with their next milestone."""
    if ctx.db is None:
        raise ToolError("unavailable", "database is not available")
    pid = _party_uuid(args.party_id)
    if pid is not None and not ctx.user.reads_all and pid != ctx.user.party_id:
        # Buyers only see their own business; any other id looks missing (no existence oracle).
        raise ToolError("not_found", "party not found")
    d = dashboard.dashboard(ctx.db, ctx.user, pid)
    ccy = d.currency
    return DashboardSnapshotOut(
        party_name=d.party_name,
        currency=ccy,
        today=d.today,
        cash_balance=getattr(d.cash_balance, ccy),
        in_escrow=getattr(d.in_escrow, ccy),
        due_next_30_days=getattr(d.due_next_30_days, ccy),
        first_shortfall=Shortfall(on=d.first_shortfall.on, amount=d.first_shortfall.amount)
        if d.first_shortfall
        else None,
        lowest_balance=d.lowest_balance,
        lowest_on=d.lowest_on,
        open_alerts_count=d.open_alerts_count,
        top_alerts=[
            SnapshotAlert(
                type=a.type,
                severity=a.severity,
                title=a.title_en,
                amount=a.amount,
                currency=a.currency,
                due_on=a.due_on,
                deal_ref=a.deal_ref,
            )
            for a in d.alerts
        ],
        pending_approvals=d.pending_approvals,
        active_deals=[
            SnapshotDeal(
                reference=x.reference,
                status=x.status,
                supplier_name=x.supplier_name,
                next_milestone_seq=x.next_milestone.seq if x.next_milestone else None,
                next_due_on=x.next_milestone.due_on if x.next_milestone else None,
                next_amount=getattr(x.next_milestone.amount, ccy) if x.next_milestone else None,
                next_currency=ccy if x.next_milestone else None,
            )
            for x in d.active_deals
        ],
    )


# --- get_deal_summary -----------------------------------------------------------------------


class DealSummaryIn(_In):
    deal_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Deal reference (e.g. SETU-2026-0001) or deal UUID.",
    )


class MilestoneOut(_Out):
    seq: int
    trigger: str
    amount: DecStr
    currency: str
    due_on: date
    status: str


class DealSummaryOut(_Out):
    reference: str
    title: str
    status: str
    supplier_name: str
    currency: str
    goods_value: DecStr
    milestones: list[MilestoneOut]
    next_milestone_seq: int | None
    next_due_on: date | None
    escrow_balance: DecStr | None
    escrow_currency: str | None
    escrow_status: str | None


@REGISTRY.tool(
    name="get_deal_summary",
    tier=Tier.T0,
    args_schema=DealSummaryIn,
    output_schema=DealSummaryOut,
    tags=("deal",),
)
def get_deal_summary(args: DealSummaryIn, ctx: ToolContext) -> DealSummaryOut:
    """Status of one deal: supplier, goods value, every milestone (amount, due date, status), the
    next due milestone and the simulated escrow balance."""
    if ctx.db is None:
        raise ToolError("unavailable", "database is not available")
    try:
        deal = find_deal(ctx.db, args.deal_id)
    except Exception as exc:
        raise ToolError("not_found", "deal not found") from exc
    if not can_read_party(ctx.user, deal.buyer_id):
        # Same answer as a missing deal: no existence oracle across buyers.
        raise ToolError("not_found", "deal not found")
    ms = ctx.db.scalars(
        select(Milestone).where(Milestone.deal_id == deal.id).order_by(Milestone.seq)
    ).all()
    nxt = next((m for m in ms if m.status in OPEN_MILESTONES), None)
    escrow = ctx.db.scalars(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id)).first()
    return DealSummaryOut(
        reference=deal.reference,
        title=deal.title,
        status=deal.status,
        supplier_name=party(ctx.db, deal.supplier_id).legal_name,
        currency=deal.currency,
        goods_value=fmt(deal.goods_value),
        milestones=[
            MilestoneOut(
                seq=m.seq,
                trigger=m.trigger,
                amount=fmt(m.amount),
                currency=m.currency,
                due_on=m.due_on,
                status=m.status,
            )
            for m in ms
        ],
        next_milestone_seq=nxt.seq if nxt else None,
        next_due_on=nxt.due_on if nxt else None,
        escrow_balance=fmt(escrow.balance) if escrow else None,
        escrow_currency=escrow.currency if escrow else None,
        escrow_status=escrow.status if escrow else None,
    )


# --- explain_how_setu_works -----------------------------------------------------------------


class ExplainIn(_In):
    pass


class TierRule(_Out):
    tier: int
    name: str
    rule: str


class ExplainOut(_Out):
    facts: list[str]
    tiers: list[TierRule]


HOW_SETU_WORKS = ExplainOut(
    facts=[
        "Setu holds each supplier payment in a simulated escrow and releases it in milestones "
        "(for example deposit, shipment, arrival), each tied to evidence such as a bill of lading.",
        "The AI assistant only reads, calculates and explains. It cannot move money.",
        "Every money action is classified into a risk tier in code; the highest triggered tier "
        "wins.",
        "All balances, payments and ledgers in this demo are simulated; no real bank is connected.",
        "Every agent action is recorded in a signed, hash-chained audit log.",
    ],
    tiers=[
        TierRule(tier=0, name="Auto", rule="Read-only analysis, checks and calculations."),
        TierRule(
            tier=1,
            name="Auto + notice",
            rule="Release to a verified, unchanged beneficiary when all checks pass and the "
            "amount is at most USD 20,000.",
        ),
        TierRule(
            tier=2,
            name="One-tap approval",
            rule="First deal with a supplier, minor document mismatch, FX rate lock, or a "
            "milestone schedule change.",
        ),
        TierRule(
            tier=3,
            name="OTP + 10-minute cooling-off",
            rule="Beneficiary or bank account change, high fraud score, duplicate document, "
            "amount over USD 20,000, or any instruction that came from document or email text.",
        ),
    ],
)


@REGISTRY.tool(
    name="explain_how_setu_works",
    tier=Tier.T0,
    args_schema=ExplainIn,
    output_schema=ExplainOut,
    tags=("static",),
)
def explain_how_setu_works(args: ExplainIn, ctx: ToolContext) -> ExplainOut:
    """Static facts about Setu: milestone escrow, what the assistant can and cannot do, and the
    four approval tiers."""
    return HOW_SETU_WORKS
