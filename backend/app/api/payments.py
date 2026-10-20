"""PayPal Sandbox checkout (simulated money). Humans only, like the deal and approval endpoints:
none of this is an agent tool. A captured payment never funds the escrow by itself; the buyer
asks for that explicitly with POST /payments/paypal/{id}/fund-escrow, which runs the normal
funding path (role checks, risk gate, ledger, audit)."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.deps import CurrentUser, current_user, not_viewer
from app.db.enums import SandboxPaymentCoverage
from app.db.session import get_db
from app.errors import DomainError
from app.schemas.payments import (
    CreateOrderRequest,
    FundEscrowResult,
    PaymentListOut,
    PaymentOut,
    PaypalConfigOut,
    WebhookAck,
)
from app.services.payments import service
from app.services.payments.paypal_sandbox import PayPalGateway, get_gateway

router = APIRouter(prefix="/payments/paypal", tags=["payments"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
Writer = Annotated[CurrentUser, Depends(not_viewer)]
Gateway = Annotated[PayPalGateway, Depends(get_gateway)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{8,64}$")]


def _out(db: Session, user: CurrentUser, pay: Any, deal: Any) -> PaymentOut:
    return PaymentOut.model_validate(service.to_out(db, user, pay, deal))


@router.get("/config", response_model=PaypalConfigOut)
def config(user: User) -> PaypalConfigOut:
    """Whether the Sandbox checkout is configured, plus the public client id for the JS SDK."""
    return PaypalConfigOut.model_validate(service.config_out())


@router.post("/orders", response_model=PaymentOut)
def create_order(
    body: CreateOrderRequest,
    response: Response,
    db: Db,
    user: Writer,
    gw: Gateway,
    idempotency_key: IdemKey = None,
) -> PaymentOut:
    """Create a Sandbox order for a deal. The amount is the next tranche (or the remaining goods
    value) computed by the server; the request carries neither amount nor user."""
    pay, deal, created = service.create_order(
        db,
        user,
        gw,
        body.deal_id,
        SandboxPaymentCoverage(body.coverage),
        idempotency_key,
    )
    response.status_code = 201 if created else 200
    return _out(db, user, pay, deal)


@router.get("/deals/{deal_id}", response_model=PaymentListOut)
def list_payments(deal_id: str, db: Db, user: User) -> PaymentListOut:
    """Sandbox payments for a deal (your own; admins and judges see all)."""
    rows = service.list_for_deal(db, user, deal_id)
    return PaymentListOut(payments=[_out(db, user, p, d) for p, d in rows])


@router.post("/orders/{payment_id}/capture", response_model=PaymentOut)
def capture(payment_id: uuid.UUID, db: Db, user: Writer, gw: Gateway) -> PaymentOut:
    """Capture an order the buyer approved in PayPal. Verifies the order and the captured amount
    against the stored payment. Idempotent."""
    pay, deal = service.capture(db, user, gw, payment_id)
    return _out(db, user, pay, deal)


@router.post("/orders/{payment_id}/cancel", response_model=PaymentOut)
def cancel(payment_id: uuid.UUID, db: Db, user: Writer) -> PaymentOut:
    """The buyer abandoned the PayPal window; nothing was charged."""
    pay, deal = service.cancel(db, user, payment_id)
    return _out(db, user, pay, deal)


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: uuid.UUID, db: Db, user: User, refresh: Annotated[bool, Query()] = False
) -> PaymentOut:
    """Stored status. With `refresh=true` an uncaptured payment is checked against PayPal."""
    gw = get_gateway() if refresh else None
    pay, deal = service.get_payment(db, user, gw, payment_id, refresh=refresh)
    return _out(db, user, pay, deal)


@router.post(
    "/{payment_id}/fund-escrow",
    response_model=FundEscrowResult,
    responses={202: {"model": FundEscrowResult, "description": "Waiting for human approval"}},
)
def fund_escrow(
    payment_id: uuid.UUID, response: Response, db: Db, user: Writer
) -> FundEscrowResult:
    """Explicit step: deposit a captured Sandbox payment into the simulated escrow, once. Goes
    through the normal funding path, so the risk gate can block it or ask for approval (202)."""
    out = service.fund_escrow_from(db, user, payment_id)
    pending = out.outcome == "PENDING_APPROVAL"
    if pending:
        response.status_code = 202
    return FundEscrowResult(
        outcome=out.outcome,  # type: ignore[arg-type]
        idempotent_replay=out.replay,
        approval_id=out.approval.id if out.approval else None,
        approval_tier=out.approval.tier if out.approval else None,
        notice=(
            "Waiting for approval. No money has moved (Simulated)."
            if pending
            else "Deposited into the simulated escrow (Simulated)."
        ),
        payment=_out(db, user, out.payment, out.deal),
    )


@router.post("/webhook", response_model=WebhookAck)
async def webhook(request: Request, db: Db, gw: Gateway) -> WebhookAck:
    """PayPal Sandbox webhook. Unauthenticated by session: authenticity is PayPal's signature,
    verified before anything is read from the body. Redeliveries are acknowledged and ignored."""
    raw = await request.body()
    try:
        event = json.loads(raw)
    except ValueError as exc:
        raise DomainError("webhook body is not JSON", "WEBHOOK_MALFORMED") from exc
    if not isinstance(event, dict):
        raise DomainError("webhook body is not an object", "WEBHOOK_MALFORMED")
    outcome = await run_in_threadpool(service.handle_webhook, db, gw, dict(request.headers), event)
    return WebhookAck(outcome=outcome)
