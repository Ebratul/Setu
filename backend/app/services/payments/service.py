"""PayPal Sandbox checkout orchestration (simulated money only).

Boundaries:
- A payment's amount, currency, owner and status come from this module's own rows and the deal,
  never from the request. PayPal's answers are compared with the stored row before they are
  believed; a mismatch fails the payment.
- A CAPTURED payment touches neither the escrow nor the ledger. `fund_escrow_from` is the one
  explicit step that deposits into the simulated escrow, through `escrow.fund_escrow` unchanged:
  the same role checks, risk gate (BLOCK, approval), ledger and audit apply. The link
  `escrow_funded_at` is written in the funding transaction, so a payment funds the escrow once.
- Webhooks are signature-verified, de-duplicated by event id, and only ever move a payment's own
  status. They never post to the ledger.

Funding is also the only place money rules are shared with the existing code: the deposit is the
deal-currency amount stored on the payment; the PayPal charge is USD (the only currency PayPal
Sandbox accounts reliably share) converted server-side with the recorded FX rate.
"""

import contextlib
import hashlib
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import (
    ApprovalStatus,
    Role,
    SandboxPaymentCoverage,
    SandboxPaymentStatus,
)
from app.db.models import (
    ApprovalRequest,
    Deal,
    EscrowAccount,
    SandboxPayment,
    SandboxPaymentEvent,
)
from app.domain import escrow as rules
from app.domain.fx import FxRateMissing
from app.domain.money import ZERO, Currency, Money, q2
from app.errors import Conflict, DomainError, NotFound, ServiceUnavailable, Unauthorized
from app.services import deals as deals_service
from app.services import escrow as escrow_service
from app.services.analysis import fx_table
from app.services.payments.paypal_sandbox import (
    PayPalError,
    PayPalGateway,
    PayPalUnavailable,
    ProviderCapture,
    ProviderOrder,
)
from app.services.risk.gate import ApprovalPending
from app.services.scope import demo_today

log = structlog.get_logger("setu.payments")

CHARGE_CURRENCY = "USD"
REUSE_WINDOW = timedelta(minutes=30)
OPEN_APPROVAL = (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
Status = SandboxPaymentStatus


class PaymentFailed(Conflict):
    """The payment was marked FAILED. `code` says why; the row stays for the audit trail."""


class PaymentRefused(Conflict):
    """A precondition failed; nothing changed. `code` is stable and machine-readable."""


# --- access and loading -----------------------------------------------------------------------


def _payment(db: Session, payment_id: uuid.UUID, *, lock: bool = False) -> SandboxPayment:
    q = select(SandboxPayment).where(SandboxPayment.id == payment_id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    pay = db.scalars(q).one_or_none()
    if pay is None:
        raise NotFound("payment not found")
    return pay


def load(
    db: Session, user: CurrentUser, payment_id: uuid.UUID, *, write: bool, lock: bool = False
) -> tuple[SandboxPayment, Deal]:
    """The payment and its deal, or 404. Another buyer, a supplier, or a viewer of someone else's
    payment gets the same 404 as a payment that does not exist. Only the creator (or an admin) may
    act; judges may read."""
    pay = _payment(db, payment_id, lock=lock)
    deal = db.get(Deal, pay.deal_id)
    if deal is None or escrow_service.viewer_role(user, deal) not in ("BUYER", "ADMIN", "JUDGE"):
        raise NotFound("payment not found")
    mine = pay.created_by_user_id == user.id
    if user.role == Role.ADMIN or mine:
        if write:
            escrow_service.authorize(db, user, deal, "PAYMENT")
        return pay, deal
    if not write and user.role == Role.JUDGE:
        return pay, deal
    raise NotFound("payment not found")


def to_out(db: Session, user: CurrentUser, pay: SandboxPayment, deal: Deal) -> dict[str, Any]:
    actor = user.role == Role.ADMIN or pay.created_by_user_id == user.id
    live = pay.status == Status.CREATED and actor
    funding_open = False
    if pay.funding_approval_id is not None:
        appr = db.get(ApprovalRequest, pay.funding_approval_id)
        funding_open = appr is not None and appr.status in OPEN_APPROVAL
    return {
        "id": pay.id,
        "deal_id": pay.deal_id,
        "deal_reference": deal.reference,
        "coverage": pay.coverage.value,
        "status": pay.status.value,
        "amount": f"{q2(pay.amount)}",
        "currency": pay.currency,
        "charge_amount": f"{q2(pay.charge_amount)}",
        "charge_currency": pay.charge_currency,
        "fx_rate": None if pay.fx_rate is None else f"{pay.fx_rate.normalize():f}",
        "provider_order_id": pay.provider_order_id,
        "provider_capture_id": pay.provider_capture_id,
        "provider_status": pay.provider_status,
        "failure_code": pay.failure_code,
        "created_at": pay.created_at,
        "captured_at": pay.captured_at,
        "escrow_funded_at": pay.escrow_funded_at,
        "funding_approval_id": pay.funding_approval_id,
        "can_capture": live,
        "can_cancel": live,
        "can_fund_escrow": bool(
            actor
            and pay.status == Status.CAPTURED
            and pay.escrow_funded_at is None
            and not funding_open
            and deal.status in rules.FUNDABLE_DEAL
        ),
    }


def _audit(
    db: Session, deal: Deal, action: str, pay: SandboxPayment, result: str, **extra: Any
) -> None:
    escrow_service.audit(
        db,
        deal,
        action,
        0,
        {
            "deal_id": str(deal.id),
            "payment_id": str(pay.id),
            "provider_order_id": pay.provider_order_id,
            "amount": str(q2(pay.amount)),
            "currency": pay.currency,
            **extra,
        },
        result,
    )


# --- create -----------------------------------------------------------------------------------


def _uncommitted_captured(db: Session, deal_id: uuid.UUID) -> Decimal:
    """Deal-currency amount captured at PayPal but not yet deposited: counted as covered, so one
    tranche is not paid for twice."""
    total = db.scalar(
        select(func.coalesce(func.sum(SandboxPayment.amount), 0)).where(
            SandboxPayment.deal_id == deal_id,
            SandboxPayment.status == Status.CAPTURED,
            SandboxPayment.escrow_funded_at.is_(None),
        )
    )
    return Decimal(total or 0)


def _derive_amount(
    db: Session, deal: Deal, coverage: SandboxPaymentCoverage
) -> tuple[Decimal, Decimal, Decimal | None]:
    """(amount in deal currency, PayPal charge in USD, FX rate used or None)."""
    if deal.status not in rules.FUNDABLE_DEAL:
        raise PaymentRefused(
            f"a deal in status {deal.status.value} cannot be funded; both parties must confirm "
            "the milestone schedule first",
            "DEAL_NOT_FUNDABLE",
        )
    escrow = db.scalar(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id))
    funded = escrow.funded_total if escrow is not None else ZERO
    covered = funded + _uncommitted_captured(db, deal.id)
    remaining = deal.goods_value - covered
    if remaining <= ZERO:
        raise PaymentRefused(
            "the goods value is already covered by escrow deposits and captured payments",
            "ALREADY_COVERED",
        )
    if coverage == SandboxPaymentCoverage.REMAINING:
        amount = remaining
    else:
        ms = escrow_service.milestones_of(db, deal.id)
        amount = rules.default_deposit([(m.amount, m.status) for m in ms], covered)
    amount = q2(amount)
    if amount <= ZERO:
        raise PaymentRefused("there is nothing left to pay for this deal", "NOTHING_TO_PAY")
    if deal.currency == CHARGE_CURRENCY:
        charge, rate = amount, None
    else:
        try:
            fx = fx_table(db, demo_today(db))
            ccy = cast(Currency, deal.currency)
            charge = q2(fx.convert(Money(amount, ccy), "USD").amount)
            rate = fx.rate(ccy, "USD")
        except FxRateMissing as exc:
            raise DomainError("no FX rate available for this deal", "FX_UNAVAILABLE") from exc
    if charge < Decimal("0.01"):
        raise DomainError("the amount is too small to charge", "AMOUNT_TOO_SMALL")
    return amount, charge, rate


def _by_key(db: Session, user: CurrentUser, key: str) -> SandboxPayment | None:
    return db.scalar(
        select(SandboxPayment).where(
            SandboxPayment.created_by_user_id == user.id, SandboxPayment.idempotency_key == key
        )
    )


def create_order(
    db: Session,
    user: CurrentUser,
    gw: PayPalGateway,
    deal_ref: str,
    coverage: SandboxPaymentCoverage,
    idempotency_key: str | None,
) -> tuple[SandboxPayment, Deal, bool]:
    """(payment, deal, created). A repeated Idempotency-Key, or an identical CREATED order made a
    moment ago by the same user, returns the existing payment and creates nothing at PayPal."""
    deal = deals_service.find_deal(db, user, deal_ref)
    escrow_service.authorize(db, user, deal, "PAYMENT")
    if idempotency_key:
        prior = _by_key(db, user, idempotency_key)
        if prior is not None:
            if prior.deal_id != deal.id or prior.coverage != coverage:
                raise PaymentRefused(
                    "this Idempotency-Key was used for a different request",
                    "IDEMPOTENCY_KEY_REUSED",
                )
            return prior, deal, False
    amount, charge, rate = _derive_amount(db, deal, coverage)
    now = escrow_service.utcnow()
    recent = db.scalar(
        select(SandboxPayment)
        .where(
            SandboxPayment.created_by_user_id == user.id,
            SandboxPayment.deal_id == deal.id,
            SandboxPayment.coverage == coverage,
            SandboxPayment.status == Status.CREATED,
            SandboxPayment.amount == amount,
            SandboxPayment.created_at >= now - REUSE_WINDOW,
        )
        .order_by(SandboxPayment.created_at.desc())
    )
    if recent is not None and not idempotency_key:
        return recent, deal, False

    payment_id = uuid.uuid4()
    request_id = (
        hashlib.sha256(f"{user.id}:{idempotency_key}".encode()).hexdigest()[:32]
        if idempotency_key
        else payment_id.hex
    )
    try:
        order = gw.create_order(
            amount=charge,
            currency=CHARGE_CURRENCY,
            reference=deal.reference,
            custom_id=str(payment_id),
            description=f"Setu Sandbox deposit for {deal.reference}",
            request_id=request_id,
        )
    except (PayPalError, PayPalUnavailable) as exc:
        log.warning("paypal_create_failed", deal=deal.reference, error=type(exc).__name__)
        raise ServiceUnavailable(
            "PayPal Sandbox could not create the order", "PAYPAL_UNAVAILABLE"
        ) from exc
    if order.amount != charge or order.currency != CHARGE_CURRENCY or not order.id:
        raise ServiceUnavailable("PayPal Sandbox returned an unexpected order", "PAYPAL_MISMATCH")
    pay = SandboxPayment(
        id=payment_id,
        deal_id=deal.id,
        buyer_id=deal.buyer_id,
        created_by_user_id=user.id,
        coverage=coverage,
        amount=amount,
        currency=deal.currency,
        charge_amount=charge,
        charge_currency=CHARGE_CURRENCY,
        fx_rate=rate,
        status=Status.CREATED,
        provider_order_id=order.id,
        provider_status=order.status,
        idempotency_key=idempotency_key,
        request_id=request_id,
        created_at=now,
    )
    db.add(pay)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            prior = _by_key(db, user, idempotency_key)
            if prior is not None:
                return prior, db.get(Deal, prior.deal_id) or deal, False
        raise
    _audit(
        db,
        deal,
        "PAYMENT_ORDER_CREATED",
        pay,
        "CREATED",
        charge_amount=str(charge),
        charge_currency=CHARGE_CURRENCY,
        user_id=str(user.id),
    )
    db.commit()
    return pay, deal, True


# --- capture ----------------------------------------------------------------------------------


def _order_matches(pay: SandboxPayment, order: ProviderOrder) -> bool:
    return (
        order.id == pay.provider_order_id
        and order.custom_id == str(pay.id)
        and order.amount == q2(pay.charge_amount)
        and order.currency == pay.charge_currency
    )


def _capture_matches(pay: SandboxPayment, cap: ProviderCapture) -> bool:
    return cap.amount == q2(pay.charge_amount) and cap.currency == pay.charge_currency


def _mark_captured(
    db: Session, deal: Deal, pay: SandboxPayment, cap: ProviderCapture, source: str
) -> None:
    pay.status = Status.CAPTURED
    pay.provider_capture_id = cap.id
    pay.provider_status = cap.status
    pay.failure_code = None
    pay.captured_at = escrow_service.utcnow()
    _audit(db, deal, "PAYMENT_CAPTURED", pay, "CAPTURED", capture_id=cap.id, source=source)


def _mark_failed(
    db: Session,
    deal: Deal,
    pay: SandboxPayment,
    code: str,
    provider_status: str | None,
    source: str,
) -> None:
    pay.status = Status.FAILED
    pay.failure_code = code[:48]
    if provider_status:
        pay.provider_status = provider_status[:32]
    _audit(db, deal, "PAYMENT_FAILED", pay, "FAILED", code=code[:48], source=source)


def _fail(
    db: Session,
    deal: Deal,
    pay: SandboxPayment,
    code: str,
    provider_status: str | None,
    message: str,
) -> PaymentFailed:
    _mark_failed(db, deal, pay, code, provider_status, "capture")
    db.commit()
    return PaymentFailed(message, code)


def _completed(order: ProviderOrder) -> ProviderCapture | None:
    return next((c for c in order.captures if c.status == "COMPLETED"), None)


def capture(
    db: Session, user: CurrentUser, gw: PayPalGateway, payment_id: uuid.UUID, *, _retry: bool = True
) -> tuple[SandboxPayment, Deal]:
    """Server-side capture of an order the buyer approved in PayPal. Idempotent: a captured
    payment is returned as is, and the PayPal-Request-Id makes a retried capture safe."""
    pay, deal = load(db, user, payment_id, write=True, lock=True)
    if pay.status == Status.CAPTURED:
        return pay, deal
    if pay.status != Status.CREATED:
        raise PaymentRefused(
            f"a payment in status {pay.status.value} cannot be captured", "PAYMENT_NOT_CAPTURABLE"
        )
    try:
        order = gw.get_order(pay.provider_order_id)
    except PayPalUnavailable as exc:
        raise ServiceUnavailable("PayPal Sandbox is unavailable", "PAYPAL_UNAVAILABLE") from exc
    except PayPalError as exc:
        raise PaymentRefused("PayPal does not know this order", "PROVIDER_ORDER_NOT_FOUND") from exc
    if not _order_matches(pay, order):
        raise _fail(
            db,
            deal,
            pay,
            "PROVIDER_AMOUNT_MISMATCH",
            order.status,
            "the PayPal order does not match the amount recorded by Setu",
        )
    done = _completed(order)
    if order.status == "COMPLETED" and done is not None:
        if not _capture_matches(pay, done):
            raise _fail(
                db,
                deal,
                pay,
                "PROVIDER_AMOUNT_MISMATCH",
                done.status,
                "the PayPal capture does not match the amount recorded by Setu",
            )
        _mark_captured(db, deal, pay, done, "capture_reconcile")
        db.commit()
        return pay, deal
    if order.status != "APPROVED":
        pay.provider_status = order.status[:32]
        db.commit()
        raise PaymentRefused(
            "approve the payment in PayPal before capturing it", "PAYMENT_NOT_APPROVED"
        )
    try:
        result = gw.capture_order(pay.provider_order_id, request_id=pay.request_id)
    except PayPalUnavailable as exc:
        raise ServiceUnavailable("PayPal Sandbox is unavailable", "PAYPAL_UNAVAILABLE") from exc
    except PayPalError as exc:
        if exc.issue == "ORDER_ALREADY_CAPTURED" and _retry:
            db.rollback()
            return capture(db, user, gw, payment_id, _retry=False)
        if exc.issue == "ORDER_NOT_APPROVED":
            raise PaymentRefused(
                "approve the payment in PayPal before capturing it", "PAYMENT_NOT_APPROVED"
            ) from exc
        raise _fail(db, deal, pay, exc.issue, None, "PayPal refused the capture") from exc
    cap = _completed(result)
    if cap is None:
        pending = next((c for c in result.captures if c.status == "PENDING"), None)
        if pending is not None:
            pay.provider_status = "PENDING"
            db.commit()
            raise PaymentRefused("PayPal has not completed the capture yet", "PAYMENT_PENDING")
        status = result.captures[0].status if result.captures else result.status
        raise _fail(
            db, deal, pay, f"CAPTURE_{status}", status, "PayPal did not complete the capture"
        )
    if not _order_matches(pay, result) or not _capture_matches(pay, cap):
        raise _fail(
            db,
            deal,
            pay,
            "PROVIDER_AMOUNT_MISMATCH",
            cap.status,
            "the PayPal capture does not match the amount recorded by Setu",
        )
    _mark_captured(db, deal, pay, cap, "capture")
    db.commit()
    return pay, deal


def cancel(db: Session, user: CurrentUser, payment_id: uuid.UUID) -> tuple[SandboxPayment, Deal]:
    """The buyer closed the PayPal window. Only an uncaptured payment can be cancelled."""
    pay, deal = load(db, user, payment_id, write=True, lock=True)
    if pay.status == Status.CANCELLED:
        return pay, deal
    if pay.status != Status.CREATED:
        raise PaymentRefused(
            f"a payment in status {pay.status.value} cannot be cancelled", "PAYMENT_NOT_CANCELLABLE"
        )
    pay.status = Status.CANCELLED
    _audit(db, deal, "PAYMENT_CANCELLED", pay, "CANCELLED", user_id=str(user.id))
    db.commit()
    return pay, deal


# --- read and reconcile -----------------------------------------------------------------------


def reconcile_funding(db: Session, pay: SandboxPayment, *, commit: bool = True) -> None:
    """If the approval this payment's deposit waited for has been executed, the deposit happened
    (the approval flips to EXECUTED in the funding transaction)."""
    if pay.escrow_funded_at is not None or pay.funding_approval_id is None:
        return
    appr = db.get(ApprovalRequest, pay.funding_approval_id)
    if appr is not None and appr.status == ApprovalStatus.EXECUTED:
        pay.escrow_funded_at = escrow_service.utcnow()
        if commit:
            db.commit()


def get_payment(
    db: Session,
    user: CurrentUser,
    gw: PayPalGateway | None,
    payment_id: uuid.UUID,
    *,
    refresh: bool,
) -> tuple[SandboxPayment, Deal]:
    """Stored status; with `refresh` a CREATED payment is checked against PayPal and moved on if
    PayPal says it was captured (or voided)."""
    pay, deal = load(db, user, payment_id, write=False)
    reconcile_funding(db, pay)
    if refresh and gw is not None and pay.status == Status.CREATED:
        pay, deal = load(db, user, payment_id, write=False, lock=True)
        if pay.status == Status.CREATED:
            try:
                order = gw.get_order(pay.provider_order_id)
            except PayPalUnavailable as exc:
                raise ServiceUnavailable(
                    "PayPal Sandbox is unavailable", "PAYPAL_UNAVAILABLE"
                ) from exc
            except PayPalError:
                db.rollback()
                return pay, deal
            done = _completed(order)
            if not _order_matches(pay, order):
                _mark_failed(db, deal, pay, "PROVIDER_AMOUNT_MISMATCH", order.status, "refresh")
            elif order.status == "COMPLETED" and done is not None:
                if _capture_matches(pay, done):
                    _mark_captured(db, deal, pay, done, "refresh")
                else:
                    _mark_failed(db, deal, pay, "PROVIDER_AMOUNT_MISMATCH", done.status, "refresh")
            else:
                pay.provider_status = order.status[:32]
            db.commit()
    return pay, deal


def list_for_deal(
    db: Session, user: CurrentUser, deal_ref: str
) -> list[tuple[SandboxPayment, Deal]]:
    deal = deals_service.find_deal(db, user, deal_ref)
    q = select(SandboxPayment).where(SandboxPayment.deal_id == deal.id)
    if user.role not in (Role.ADMIN, Role.JUDGE):
        if escrow_service.viewer_role(user, deal) != "BUYER":
            return []
        q = q.where(SandboxPayment.created_by_user_id == user.id)
    rows = db.scalars(q.order_by(SandboxPayment.created_at.desc()).limit(50)).all()
    for pay in rows:
        reconcile_funding(db, pay)
    return [(p, deal) for p in rows]


# --- explicit escrow funding ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FundFromPayment:
    outcome: str  # FUNDED | PENDING_APPROVAL
    replay: bool
    payment: SandboxPayment
    deal: Deal
    approval: ApprovalRequest | None = None


def fund_escrow_from(db: Session, user: CurrentUser, payment_id: uuid.UUID) -> FundFromPayment:
    """Deposit a CAPTURED payment's deal-currency amount into the simulated escrow, once.

    This is `escrow.fund_escrow` as a person would call it: role check, risk gate and ledger are
    all its own. BLOCK raises; an approval requirement leaves the payment CAPTURED with the
    approval linked and moves nothing; the deposit commits together with the payment link."""
    pay, deal = load(db, user, payment_id, write=True, lock=True)
    reconcile_funding(db, pay, commit=False)
    if pay.escrow_funded_at is not None:
        db.commit()
        return FundFromPayment("FUNDED", True, pay, deal)
    if pay.status != Status.CAPTURED:
        raise PaymentRefused("only a captured payment can fund the escrow", "PAYMENT_NOT_CAPTURED")
    if pay.funding_approval_id is not None:
        appr = db.get(ApprovalRequest, pay.funding_approval_id)
        if appr is not None and appr.status in OPEN_APPROVAL:
            return FundFromPayment("PENDING_APPROVAL", True, pay, deal, appr)
        pay.funding_approval_id = None
    now = escrow_service.utcnow()

    def linked() -> None:
        pay.escrow_funded_at = now
        _audit(db, deal, "PAYMENT_ESCROW_LINKED", pay, "FUNDED", user_id=str(user.id))

    try:
        escrow_service.fund_escrow(db, user, deal.id, q2(pay.amount), on_funded=linked, now=now)
    except ApprovalPending as pending:
        pay.funding_approval_id = pending.approval.id
        _audit(
            db,
            deal,
            "PAYMENT_ESCROW_PENDING_APPROVAL",
            pay,
            "PENDING_APPROVAL",
            approval_id=str(pending.approval.id),
        )
        db.commit()
        return FundFromPayment("PENDING_APPROVAL", False, pay, deal, pending.approval)
    except Exception:
        db.rollback()
        raise
    return FundFromPayment("FUNDED", False, pay, deal)


# --- webhook ----------------------------------------------------------------------------------

CAPTURE_DONE = "PAYMENT.CAPTURE.COMPLETED"
CAPTURE_LOST = frozenset(
    {
        "PAYMENT.CAPTURE.DENIED",
        "PAYMENT.CAPTURE.DECLINED",
        "PAYMENT.CAPTURE.REFUNDED",
        "PAYMENT.CAPTURE.REVERSED",
    }
)


def _find_for_event(db: Session, resource: Mapping[str, Any]) -> SandboxPayment | None:
    """The payment a capture/refund resource refers to: by order id, else by our custom id, else
    by capture id. Locked, so a concurrent capture call and this webhook take turns."""
    related = ((resource.get("supplementary_data") or {}).get("related_ids")) or {}
    order_id = related.get("order_id")
    conds = []
    if order_id:
        conds.append(SandboxPayment.provider_order_id == str(order_id))
    custom = resource.get("custom_id")
    if custom:
        with contextlib.suppress(ValueError):
            conds.append(SandboxPayment.id == uuid.UUID(str(custom)))
    if resource.get("id"):
        conds.append(SandboxPayment.provider_capture_id == str(resource["id"]))
    for link in resource.get("links") or []:
        if link.get("rel") == "up" and link.get("href"):
            conds.append(SandboxPayment.provider_capture_id == str(link["href"]).rsplit("/", 1)[-1])
    for cond in conds:
        pay = db.scalars(
            select(SandboxPayment)
            .where(cond)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if pay is not None:
            return pay
    return None


def _apply_event(
    db: Session, event_type: str, resource: Mapping[str, Any]
) -> tuple[str, SandboxPayment | None]:
    if event_type != CAPTURE_DONE and event_type not in CAPTURE_LOST:
        return "IGNORED", None
    pay = _find_for_event(db, resource)
    if pay is None:
        return "UNKNOWN_PAYMENT", None
    deal = db.get(Deal, pay.deal_id)
    assert deal is not None
    if event_type == CAPTURE_DONE:
        amount = resource.get("amount") or {}
        cap = ProviderCapture(
            id=str(resource.get("id", "")),
            status="COMPLETED",
            amount=_dec(amount.get("value")),
            currency=amount.get("currency_code"),
        )
        if pay.status == Status.CAPTURED:
            return "ALREADY_CAPTURED", pay
        if pay.status != Status.CREATED:
            _audit(
                db, deal, "PAYMENT_WEBHOOK_IGNORED", pay, "IGNORED_STATE", state=pay.status.value
            )
            return "IGNORED_STATE", pay
        if not cap.id or not _capture_matches(pay, cap):
            _mark_failed(db, deal, pay, "PROVIDER_AMOUNT_MISMATCH", "COMPLETED", "webhook")
            return "AMOUNT_MISMATCH", pay
        _mark_captured(db, deal, pay, cap, "webhook")
        return "CAPTURED", pay
    if pay.escrow_funded_at is not None:
        _audit(
            db,
            deal,
            "PAYMENT_PROVIDER_REVERSAL_AFTER_FUNDING",
            pay,
            "NEEDS_REVIEW",
            event_type=event_type,
        )
        return "NEEDS_REVIEW", pay
    if pay.status in (Status.CREATED, Status.CAPTURED):
        _mark_failed(db, deal, pay, event_type.rsplit(".", 1)[-1], None, "webhook")
        return "FAILED", pay
    return "IGNORED_STATE", pay


def _dec(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        return None


def handle_webhook(
    db: Session, gw: PayPalGateway, headers: Mapping[str, str], event: dict[str, Any]
) -> str:
    """Verify PayPal's signature, drop redeliveries, apply the event to the payment's own status.
    Returns the outcome label. Raises 401 for a bad signature and 503 when PayPal cannot be asked
    (PayPal then retries)."""
    try:
        genuine = gw.verify_webhook(headers, event)
    except PayPalUnavailable as exc:
        raise ServiceUnavailable("PayPal Sandbox is unavailable", "PAYPAL_UNAVAILABLE") from exc
    if not genuine:
        log.warning("paypal_webhook_rejected")
        raise Unauthorized(
            "webhook signature could not be verified", code="WEBHOOK_SIGNATURE_INVALID"
        )
    event_id = str(event.get("id") or "")[:64]
    event_type = str(event.get("event_type") or "")[:64]
    resource = event.get("resource")
    if not event_id or not event_type or not isinstance(resource, dict):
        raise DomainError("malformed webhook event", "WEBHOOK_MALFORMED")
    row = SandboxPaymentEvent(
        id=uuid.uuid4(), provider_event_id=event_id, event_type=event_type, outcome="RECEIVED"
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "DUPLICATE"
    outcome, pay = _apply_event(db, event_type, resource)
    row.outcome = outcome
    row.payment_id = pay.id if pay is not None else None
    row.summary = {"capture_id": str(resource.get("id", ""))[:64]}
    db.commit()
    return outcome


def config_out() -> dict[str, Any]:
    settings = get_settings()
    ready = settings.paypal_sandbox_ready
    return {
        "enabled": ready,
        "client_id": settings.paypal_sandbox_client_id if ready else None,
        "charge_currency": CHARGE_CURRENCY,
    }
