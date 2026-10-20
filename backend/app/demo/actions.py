"""Service calls the demo script can name with `call:`. Each takes the runner context and the
rendered args and returns {"status": int, "body": {...}} like an HTTP action. They use the same
services as the API, only where no single endpoint covers the beat (and always inside the judge's
own sandbox). Simulated data only."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.audit import write_audit
from app.db.enums import ApprovalStatus
from app.db.models import ApprovalRequest, Deal, Milestone, Party
from app.db.session import batch_session
from app.domain.money import Money, q2
from app.errors import DomainError, NotFound
from app.services import fx_route
from app.services.documents import release_facts
from app.services.risk import context as risk_context
from app.services.risk import engine
from app.services.risk.engine import Action, Origin

if TYPE_CHECKING:
    from app.demo.runner import SceneRun

Call = Callable[..., dict[str, Any]]
CALLS: dict[str, Call] = {}


def register(name: str) -> Callable[[Call], Call]:
    def wrap(fn: Call) -> Call:
        CALLS[name] = fn
        return fn

    return wrap


@register("fx.route_compare")
def route_compare(run: "SceneRun", *, amount: str) -> dict[str, Any]:
    """FR-7 on the tranche being released: what the supplier gets via the CNY and USD routes."""
    with batch_session() as db:
        _, data = fx_route.compare(db, Money(Decimal(amount), "USD"), "USD", "tranche")
        return {"status": 200, "body": data.model_dump(mode="json")}


@register("risk.deal_whatif")
def deal_whatif(run: "SceneRun", *, seq: int) -> dict[str, Any]:
    """Ask the real risk engine about releasing a tranche now, from the deal's real facts (KYB,
    documents, injection events). A what-if: nothing is saved, no money moves."""
    with batch_session() as db:
        deal = db.scalar(select(Deal).where(Deal.reference == run.static["deal"]["ref"]))
        if deal is None:
            raise NotFound("demo deal not found")
        ms = db.scalar(select(Milestone).where(Milestone.deal_id == deal.id, Milestone.seq == seq))
        if ms is None:
            raise NotFound("milestone not found")
        base = risk_context.deal_context(
            db,
            deal,
            Action.RELEASE_TRANCHE,
            Origin.USER_UI,
            amount=ms.amount,
            currency=ms.currency,
        )
        docs = release_facts.facts(db, deal.id, ms.id)
        ctx = base.model_copy(
            update={
                "milestone_seq": seq,
                "instruction_from_document": base.instruction_from_document or docs.instruction,
                "duplicate_hash": docs.duplicate,
                "any_document_failed": docs.failed,
                "any_document_warning": docs.warning,
                "max_document_fraud_score": docs.max_score,
            }
        )
        d = engine.evaluate(ctx)
        body = d.model_dump(mode="json")
        body["reasons"] = [engine.TEXT[c][0] for c in d.reason_codes]
        body["dry_run"] = True
        return {"status": 200, "body": body}


@register("approvals.skip_cooling_off")
def skip_cooling_off(run: "SceneRun", *, approval_id: str) -> dict[str, Any]:
    """Demo only, labelled in the UI: end the 10-minute pause of an open Tier 3 request now."""
    return {"status": 200, "body": skip_open_cooling_off(approval_id)}


def skip_open_cooling_off(
    approval_id: str | None = None, sandbox_id: str | None = None
) -> dict[str, Any]:
    """Shared by the scene above and the "Skip cooling-off (demo only)" control. Audited."""
    now = datetime.now(UTC)
    skipped = 0
    with batch_session() as db:
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.status == ApprovalStatus.PENDING,
            ApprovalRequest.tier == 3,
            ApprovalRequest.cooling_off_until.is_not(None),
            ApprovalRequest.cooling_off_until > now,
        )
        if approval_id:
            stmt = stmt.where(ApprovalRequest.id == uuid.UUID(approval_id))
        for appr in db.scalars(stmt).all():
            appr.cooling_off_until = now - timedelta(seconds=1)
            write_audit(
                db,
                actor="system",
                action="DEMO_COOLING_OFF_SKIPPED",
                tier=0,
                params={
                    "approval_id": str(appr.id),
                    "sandbox": sandbox_id,
                    "note": "demo-only control, sandbox",
                },
                result="SKIPPED",
                deal_id=appr.deal_id,
            )
            skipped += 1
    return {"skipped": skipped}


@register("injection.resolve_deal_events")
def resolve_deal_events(run: "SceneRun", *, deal: str) -> dict[str, Any]:
    """An admin closes every open injection event of the deal, through the real endpoint."""
    status, body = run.http("admin@demo.setu", "GET", "/security/injection/events", params={})
    if status != 200:
        raise DomainError("could not list the injection events", "EVENTS_UNAVAILABLE")
    open_ids = [
        e["id"]
        for e in body.get("items", [])
        if not e.get("resolved") and e.get("deal_reference") == deal
    ]
    resolved = 0
    for event_id in open_ids:
        s, _ = run.http("admin@demo.setu", "POST", f"/security/injection/events/{event_id}/resolve")
        resolved += 1 if s == 200 else 0
    return {"status": 200, "body": {"resolved": resolved, "open_before": len(open_ids)}}


@register("cashflow.receive_customer_payments")
def receive_customer_payments(run: "SceneRun", *, amount: str) -> dict[str, Any]:
    """Time skip, labelled: weeks pass between the shipment and the arrival, and Rahima's
    customers have paid. Credits her simulated cash balance so she can fund the last tranche."""
    value = q2(Decimal(amount))
    with batch_session() as db:
        buyer = db.scalar(select(Party).where(Party.code == run.static["buyer"]["code"]))
        if buyer is None or buyer.cash_balance is None:
            raise NotFound("demo buyer not found")
        buyer.cash_balance = buyer.cash_balance + value
        write_audit(
            db,
            actor="system",
            action="DEMO_CASH_RECEIPT",
            tier=0,
            params={
                "party_code": buyer.code,
                "amount": str(value),
                "currency": buyer.cash_currency,
                "note": "simulated customer payment (demo time skip)",
            },
            result="CREDITED",
        )
        return {
            "status": 200,
            "body": {"credited": str(value), "balance": str(q2(buyer.cash_balance))},
        }
