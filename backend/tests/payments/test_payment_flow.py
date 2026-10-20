"""PayPal Sandbox checkout against the real schema (Postgres) with an in-memory PayPal.

What must hold: amounts and owners come from the server; a capture never touches escrow or the
ledger; funding the escrow is an explicit, risk-gated step that happens once; webhooks are
verified and idempotent."""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.db.enums import ApprovalAction, ApprovalStatus, KybStatus, LedgerKind
from app.db.models import (
    ApprovalRequest,
    EscrowAccount,
    LedgerEntry,
    Party,
    SandboxPayment,
    SandboxPaymentEvent,
)
from app.db.session import batch_session
from app.main import create_app
from app.services import escrow
from app.services.payments.paypal_sandbox import get_gateway
from app.services.risk.engine import Origin
from app.services.risk.gate import ApprovalPending
from tests.api.conftest import dev_evidence_enabled, login, seeded_db  # noqa: F401  (fixtures)
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAXIN,
    HUAXIN_USER,
    KARIM,
    RAHIMA,
    confirmed,
    create,
    current_user_of,
    give_cash,
    propose,
    release,
    verify_evidence,
)
from tests.payments.fake_paypal import FakePayPal, capture_event

pytestmark = pytest.mark.db

BASE = "/payments/paypal"
HOOK = {"PAYPAL-TRANSMISSION-ID": "t"}


@pytest.fixture(autouse=True)
def fresh_state(seeded_db: str) -> None:  # noqa: F811
    give_cash("dhaka-stitch-works")


@pytest.fixture
def pp() -> FakePayPal:
    return FakePayPal()


@pytest.fixture
def make_client(pp: FakePayPal) -> Iterator[Any]:
    def build(email: str | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_gateway] = lambda: pp
        c = TestClient(app)
        return login(c, email) if email else c

    yield build


def new_deal(
    buyer: TestClient,
    supplier: str = BRIGHTLINE,
    goods: str = "9600.00",
    percents: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    d = create(buyer, supplier, qty=goods, price="1.00", **extra)
    propose(buyer, d["id"], **({"template": "custom", "percents": percents} if percents else {}))
    confirmed(buyer, as_supplier(supplier), d["id"])
    return d


def as_supplier(code: str) -> TestClient | None:
    from tests.api.deals_support import as_user

    return as_user(HUAXIN_USER) if code == HUAXIN else None


def order(buyer: TestClient, deal_id: str, key: str | None = None, **body: Any) -> Any:
    return buyer.post(
        f"{BASE}/orders",
        json={"deal_id": deal_id, **body},
        headers={"Idempotency-Key": key} if key else {},
    )


def paid(buyer: TestClient, pp: FakePayPal, deal_id: str) -> dict[str, Any]:
    """Order created, approved at PayPal, captured. Nothing has touched escrow yet."""
    res = order(buyer, deal_id)
    assert res.status_code == 201, res.text
    pay = res.json()
    pp.approve(pay["provider_order_id"])
    cap = buyer.post(f"{BASE}/orders/{pay['id']}/capture")
    assert cap.status_code == 200, cap.text
    return cap.json()


def fund_rows(deal_id: str) -> int:
    with batch_session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(
                    LedgerEntry.deal_id == uuid.UUID(deal_id), LedgerEntry.kind == LedgerKind.FUND
                )
            )
            or 0
        )


def funded_total(deal_id: str) -> Decimal:
    with batch_session() as s:
        return s.scalar(
            select(EscrowAccount.funded_total).where(EscrowAccount.deal_id == uuid.UUID(deal_id))
        ) or Decimal("0")


def row(payment_id: str) -> SandboxPayment:
    with batch_session() as s:
        p = s.get(SandboxPayment, uuid.UUID(payment_id))
        assert p is not None
        s.expunge(p)
        return p


def untouched(deal_id: str) -> None:
    assert fund_rows(deal_id) == 0 and funded_total(deal_id) == 0


# --- the lifecycle ----------------------------------------------------------------------------


def test_success_capture_then_explicit_funding_then_release(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    assert pay["status"] == "CAPTURED" and pay["simulated"] is True
    assert pay["amount"] == "2880.00" and pay["currency"] == "USD"  # 30% of 9600.00
    assert pay["can_fund_escrow"] is True
    untouched(d["id"])  # a capture alone moves nothing into escrow or the ledger

    res = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outcome"] == "FUNDED" and body["idempotent_replay"] is False
    assert fund_rows(d["id"]) == 2 and funded_total(d["id"]) == Decimal("2880.00")
    assert body["payment"]["escrow_funded_at"] is not None
    assert body["payment"]["can_fund_escrow"] is False

    again = karim.post(f"{BASE}/{pay['id']}/fund-escrow")  # replay: no second deposit
    assert again.status_code == 200 and again.json()["idempotent_replay"] is True
    assert fund_rows(d["id"]) == 2 and funded_total(d["id"]) == Decimal("2880.00")

    detail = karim.get(f"/deals/{d['id']}").json()
    ms = detail["milestones"][0]["id"]
    assert detail["milestones"][0]["status"] == "READY"
    verify_evidence(make_client(ADMIN), ms)
    status, rel = release(karim, ms)
    assert status == 200 and rel["outcome"] == "RELEASED"  # the existing release path, unchanged


def test_a_payment_in_another_currency_is_charged_in_usd_but_funds_the_deal_currency(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim, HUAXIN, currency="CNY")
    assert d["currency"] == "CNY"
    res = order(karim, d["id"])
    assert res.status_code == 201, res.text
    pay = res.json()
    assert pay["currency"] == d["currency"] and pay["charge_currency"] == "USD"
    assert pay["fx_rate"] is not None and Decimal(pay["charge_amount"]) > 0
    sent = pp.orders[pay["provider_order_id"]]
    assert sent["amount"] == Decimal(pay["charge_amount"]) and sent["currency"] == "USD"
    pp.approve(pay["provider_order_id"])
    assert karim.post(f"{BASE}/orders/{pay['id']}/capture").status_code == 200
    out = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert out.status_code == 200, out.text
    assert funded_total(d["id"]) == Decimal(pay["amount"])  # deal currency, not the USD charge


def test_release_over_the_advance_limit_still_waits_for_approval(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim, goods="44000.00", percents=["50", "50"])
    pay = paid(karim, pp, d["id"])
    assert pay["amount"] == "22000.00"
    assert karim.post(f"{BASE}/{pay['id']}/fund-escrow").status_code == 200
    ms = karim.get(f"/deals/{d['id']}").json()["milestones"][0]["id"]
    verify_evidence(make_client(ADMIN), ms)
    status, rel = release(karim, ms)
    assert status == 202 and rel["outcome"] == "PENDING_APPROVAL"
    with batch_session() as s:
        released = s.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(
                LedgerEntry.deal_id == uuid.UUID(d["id"]), LedgerEntry.kind == LedgerKind.RELEASE
            )
        )
    assert released == 0  # nothing left escrow


# --- cancellation, failure, ordering ----------------------------------------------------------


def test_cancelled_checkout_cannot_be_captured_or_fund_escrow(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    res = karim.post(f"{BASE}/orders/{pay['id']}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "CANCELLED"
    assert karim.post(f"{BASE}/orders/{pay['id']}/cancel").json()["status"] == "CANCELLED"
    pp.approve(pay["provider_order_id"])
    cap = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert cap.status_code == 409 and cap.json()["code"] == "PAYMENT_NOT_CAPTURABLE"
    fund = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert fund.status_code == 409 and fund.json()["code"] == "PAYMENT_NOT_CAPTURED"
    assert pp.capture_calls == 0
    untouched(d["id"])


def test_capture_before_the_buyer_approved_is_refused_and_can_be_retried(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    early = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert early.status_code == 409 and early.json()["code"] == "PAYMENT_NOT_APPROVED"
    assert row(pay["id"]).status.value == "CREATED" and pp.capture_calls == 0
    pp.approve(pay["provider_order_id"])
    assert karim.post(f"{BASE}/orders/{pay['id']}/capture").json()["status"] == "CAPTURED"


def test_a_declined_capture_fails_the_payment_and_funds_nothing(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    pp.decline = True
    res = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert res.status_code == 409 and res.json()["code"] == "INSTRUMENT_DECLINED"
    stored = row(pay["id"])
    assert stored.status.value == "FAILED" and stored.failure_code == "INSTRUMENT_DECLINED"
    fund = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert fund.status_code == 409 and fund.json()["code"] == "PAYMENT_NOT_CAPTURED"
    untouched(d["id"])


def test_unavailable_paypal_leaves_the_payment_retryable(pp: FakePayPal, make_client: Any) -> None:
    from app.services.payments.paypal_sandbox import PayPalUnavailable

    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    real = pp.capture_order

    def down(order_id: str, *, request_id: str) -> Any:
        raise PayPalUnavailable("down")

    pp.capture_order = down  # type: ignore[method-assign]
    assert karim.post(f"{BASE}/orders/{pay['id']}/capture").status_code == 503
    assert row(pay["id"]).status.value == "CREATED"
    pp.capture_order = real  # type: ignore[method-assign]
    assert karim.post(f"{BASE}/orders/{pay['id']}/capture").json()["status"] == "CAPTURED"


# --- duplicates -------------------------------------------------------------------------------


def test_the_same_idempotency_key_creates_one_order(pp: FakePayPal, make_client: Any) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    first = order(karim, d["id"], key="checkout-key-0001")
    second = order(karim, d["id"], key="checkout-key-0001")
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"] and pp.create_calls == 1
    other = new_deal(karim)
    clash = order(karim, other["id"], key="checkout-key-0001")
    assert clash.status_code == 409 and clash.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert pp.create_calls == 1


def test_a_double_click_reuses_the_open_order(pp: FakePayPal, make_client: Any) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    a, b = order(karim, d["id"]), order(karim, d["id"])
    assert a.json()["id"] == b.json()["id"] and pp.create_calls == 1


def test_capturing_twice_charges_once_and_a_second_payment_cannot_double_cover(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    again = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert again.status_code == 200 and again.json()["status"] == "CAPTURED"
    assert pp.capture_calls == 1
    # the captured-but-undeposited tranche counts as covered: the next order is the next tranche
    nxt = order(karim, d["id"]).json()
    assert nxt["amount"] == "5760.00"  # 60% of 9600.00, not the first 30% again


# --- tampering --------------------------------------------------------------------------------


def test_the_request_cannot_carry_an_amount_owner_or_status(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    for extra in (
        {"amount": "1.00"},
        {"user_id": str(uuid.uuid4())},
        {"status": "CAPTURED"},
        {"currency": "BDT"},
    ):
        res = order(karim, d["id"], **extra)
        assert res.status_code == 422, extra
    assert pp.create_calls == 0
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    forged = karim.post(f"{BASE}/orders/{pay['id']}/capture", json={"amount": "1.00"})
    assert forged.status_code == 200  # the body is ignored; the stored amount is used
    assert row(pay["id"]).amount == Decimal("2880.00")


def test_a_capture_for_a_different_amount_fails_the_payment(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    pp.capture_amount = Decimal("1.00")
    res = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert res.status_code == 409 and res.json()["code"] == "PROVIDER_AMOUNT_MISMATCH"
    assert row(pay["id"]).status.value == "FAILED"
    assert karim.post(f"{BASE}/{pay['id']}/fund-escrow").status_code == 409
    untouched(d["id"])


def test_an_order_changed_at_the_provider_fails_the_payment_before_capture(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    pp.order_amount = Decimal("1.00")
    res = karim.post(f"{BASE}/orders/{pay['id']}/capture")
    assert res.status_code == 409 and res.json()["code"] == "PROVIDER_AMOUNT_MISMATCH"
    assert pp.capture_calls == 0 and row(pay["id"]).status.value == "FAILED"


# --- access -----------------------------------------------------------------------------------


def test_nobody_else_can_see_or_act_on_a_payment(pp: FakePayPal, make_client: Any) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pid = pay["id"]
    pp.approve(pay["provider_order_id"])
    rahima, supplier = make_client(RAHIMA), make_client(HUAXIN_USER)
    for other in (rahima, supplier):
        assert other.get(f"{BASE}/{pid}").status_code == 404
        assert other.post(f"{BASE}/orders/{pid}/capture").status_code == 404
        assert other.post(f"{BASE}/orders/{pid}/cancel").status_code == 404
        assert other.post(f"{BASE}/{pid}/fund-escrow").status_code == 404
        assert order(other, d["id"]).status_code in (403, 404)
    assert rahima.get(f"{BASE}/deals/{d['id']}").status_code == 404
    assert supplier.get(f"{BASE}/deals/{d['id']}").status_code == 404  # not their deal
    own = new_deal(karim, HUAXIN)  # the deal's own supplier sees the deal but none of the payments
    order(karim, own["id"])
    assert supplier.get(f"{BASE}/deals/{own['id']}").json()["payments"] == []
    assert len(karim.get(f"{BASE}/deals/{own['id']}").json()["payments"]) == 1
    assert pp.capture_calls == 0 and row(pid).status.value == "CREATED"
    assert make_client(ADMIN).get(f"{BASE}/{pid}").status_code == 200
    assert make_client("judge@demo.setu").get(f"{BASE}/{pid}").status_code == 200
    assert make_client("judge@demo.setu").post(f"{BASE}/orders/{pid}/capture").status_code == 404


def test_signed_out_callers_get_401(pp: FakePayPal, make_client: Any) -> None:
    anon = make_client(None)
    assert anon.post(f"{BASE}/orders", json={"deal_id": "x"}).status_code == 401
    assert anon.get(f"{BASE}/config").status_code == 401
    assert anon.post(f"{BASE}/{uuid.uuid4()}/fund-escrow").status_code == 401


def test_config_exposes_only_the_public_client_id(
    pp: FakePayPal, make_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("PAYPAL_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("PAYPAL_SANDBOX_CLIENT_ID", "public-client-id")
    monkeypatch.setenv("PAYPAL_SANDBOX_CLIENT_SECRET", "s3cret-value")
    get_settings.cache_clear()
    res = make_client(KARIM).get(f"{BASE}/config")
    assert res.status_code == 200 and res.json()["client_id"] == "public-client-id"
    assert "s3cret-value" not in res.text and res.json()["simulated"] is True
    get_settings.cache_clear()


# --- risk gate and approvals ------------------------------------------------------------------


def test_a_blocked_supplier_stops_the_deposit_and_nothing_is_marked_funded(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    with batch_session() as s:
        s.execute(update(Party).where(Party.code == BRIGHTLINE).values(kyb_status=KybStatus.FAILED))
    try:
        res = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
        assert res.status_code == 409, res.text
        assert res.json()["code"] == "RISK_BLOCKED"
    finally:
        with batch_session() as s:
            s.execute(
                update(Party).where(Party.code == BRIGHTLINE).values(kyb_status=KybStatus.VERIFIED)
            )
    stored = row(pay["id"])
    assert stored.status.value == "CAPTURED" and stored.escrow_funded_at is None
    untouched(d["id"])
    retry = karim.post(f"{BASE}/{pay['id']}/fund-escrow")  # blocked state cleared: it can proceed
    assert retry.status_code == 200 and fund_rows(d["id"]) == 2


def test_a_deposit_that_needs_approval_waits_links_the_approval_and_funds_once(
    pp: FakePayPal, make_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    user = current_user_of(KARIM)
    with batch_session() as s:  # a real FUND_ESCROW approval, as the gate creates for an agent
        with pytest.raises(ApprovalPending) as pending:
            escrow.fund_escrow(s, user, uuid.UUID(d["id"]), Decimal("2880.00"), origin=Origin.AGENT)
        approval_id = pending.value.approval.id
        raised = pending.value
    real = escrow.fund_escrow

    def gated(*args: Any, **kwargs: Any) -> Any:
        raise raised

    monkeypatch.setattr(escrow, "fund_escrow", gated)
    res = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert res.status_code == 202, res.text
    assert res.json()["outcome"] == "PENDING_APPROVAL" and res.json()["approval_id"] == str(
        approval_id
    )
    stored = row(pay["id"])
    assert stored.funding_approval_id == approval_id and stored.escrow_funded_at is None
    untouched(d["id"])
    replay = karim.post(f"{BASE}/{pay['id']}/fund-escrow")  # no second approval, no deposit
    assert replay.status_code == 202 and replay.json()["idempotent_replay"] is True

    monkeypatch.setattr(escrow, "fund_escrow", real)
    with batch_session() as s:  # the human approved and the approval executed the deposit
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .values(status=ApprovalStatus.EXECUTED)
        )
    done = karim.get(f"{BASE}/{pay['id']}")
    assert done.json()["escrow_funded_at"] is not None
    after = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert after.status_code == 200 and after.json()["idempotent_replay"] is True
    assert fund_rows(d["id"]) == 0  # the test's executed approval stands in; no extra deposit here
    assert approvals_for(d["id"]) == 1


def approvals_for(deal_id: str) -> int:
    with batch_session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(ApprovalRequest)
                .where(
                    ApprovalRequest.deal_id == uuid.UUID(deal_id),
                    ApprovalRequest.action == ApprovalAction.FUND_ESCROW,
                )
            )
            or 0
        )


# --- webhooks ---------------------------------------------------------------------------------


def test_a_webhook_with_a_bad_signature_changes_nothing(pp: FakePayPal, make_client: Any) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.webhook_genuine = False
    event = capture_event("WH-BAD", pay["provider_order_id"], "CAPX", "2880.00")
    res = make_client(None).post(f"{BASE}/webhook", json=event, headers=HOOK)
    assert res.status_code == 401 and res.json()["code"] == "WEBHOOK_SIGNATURE_INVALID"
    assert row(pay["id"]).status.value == "CREATED"
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(SandboxPaymentEvent)) == 0
    untouched(d["id"])


def test_a_verified_webhook_captures_once_and_a_redelivery_is_ignored(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    event = capture_event(
        "WH-1", pay["provider_order_id"], "CAP-WH-1", "2880.00", custom_id=pay["id"]
    )
    hook = make_client(None)
    first = hook.post(f"{BASE}/webhook", json=event, headers=HOOK)
    assert first.status_code == 200 and first.json()["outcome"] == "CAPTURED"
    second = hook.post(f"{BASE}/webhook", json=event, headers=HOOK)
    assert second.status_code == 200 and second.json()["outcome"] == "DUPLICATE"
    stored = row(pay["id"])
    assert stored.status.value == "CAPTURED" and stored.provider_capture_id == "CAP-WH-1"
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(SandboxPaymentEvent)) == 1
    untouched(d["id"])  # a webhook never posts to escrow or the ledger

    fresh = capture_event("WH-2", pay["provider_order_id"], "CAP-WH-1", "2880.00")
    assert (
        hook.post(f"{BASE}/webhook", json=fresh, headers=HOOK).json()["outcome"]
        == "ALREADY_CAPTURED"
    )
    funded = karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    assert funded.status_code == 200 and fund_rows(d["id"]) == 2
    karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    hook.post(f"{BASE}/webhook", json=event, headers=HOOK)
    assert fund_rows(d["id"]) == 2 and funded_total(d["id"]) == Decimal("2880.00")


def test_a_webhook_with_the_wrong_amount_fails_the_payment(
    pp: FakePayPal, make_client: Any
) -> None:
    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    event = capture_event("WH-AMT", pay["provider_order_id"], "CAP-AMT", "1.00")
    res = make_client(None).post(f"{BASE}/webhook", json=event, headers=HOOK)
    assert res.json()["outcome"] == "AMOUNT_MISMATCH"
    assert row(pay["id"]).status.value == "FAILED"
    assert karim.post(f"{BASE}/{pay['id']}/fund-escrow").status_code == 409


def test_a_refund_before_funding_voids_the_payment_and_after_funding_only_flags_it(
    pp: FakePayPal, make_client: Any
) -> None:
    karim, hook = make_client(KARIM), make_client(None)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    ev = capture_event(
        "WH-R1", pay["provider_order_id"], "x", "2880.00", event_type="PAYMENT.CAPTURE.REFUNDED"
    )
    assert hook.post(f"{BASE}/webhook", json=ev, headers=HOOK).json()["outcome"] == "FAILED"
    assert karim.post(f"{BASE}/{pay['id']}/fund-escrow").status_code == 409
    untouched(d["id"])

    pay2 = paid(karim, pp, d["id"])
    assert karim.post(f"{BASE}/{pay2['id']}/fund-escrow").status_code == 200
    ev2 = capture_event(
        "WH-R2", pay2["provider_order_id"], "y", "5760.00", event_type="PAYMENT.CAPTURE.REFUNDED"
    )
    assert hook.post(f"{BASE}/webhook", json=ev2, headers=HOOK).json()["outcome"] == "NEEDS_REVIEW"
    assert fund_rows(d["id"]) == 2  # flagged for review; the ledger is not rewritten


def test_unknown_and_unrelated_events_are_acknowledged(pp: FakePayPal, make_client: Any) -> None:
    hook = make_client(None)
    stray = capture_event("WH-U", "NOPE", "C", "1.00")
    assert (
        hook.post(f"{BASE}/webhook", json=stray, headers=HOOK).json()["outcome"]
        == "UNKNOWN_PAYMENT"
    )
    other = {"id": "WH-O", "event_type": "CUSTOMER.DISPUTE.CREATED", "resource": {}}
    assert hook.post(f"{BASE}/webhook", json=other, headers=HOOK).json()["outcome"] == "IGNORED"
    bad = hook.post(f"{BASE}/webhook", content=b"not json", headers=HOOK)
    assert bad.status_code == 400 and bad.json()["code"] == "WEBHOOK_MALFORMED"


def test_every_step_is_audited_without_secrets(pp: FakePayPal, make_client: Any) -> None:
    from app.db.models import AuditLog

    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    karim.post(f"{BASE}/{pay['id']}/fund-escrow")
    with batch_session() as s:
        actions = set(
            s.scalars(select(AuditLog.action).where(AuditLog.deal_id == uuid.UUID(d["id"])))
        )
    assert {
        "PAYMENT_ORDER_CREATED",
        "PAYMENT_CAPTURED",
        "PAYMENT_ESCROW_LINKED",
        "ESCROW_FUNDED",
    } <= actions


def test_concurrent_funding_requests_deposit_once(pp: FakePayPal, make_client: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor

    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = paid(karim, pp, d["id"])
    clients = [make_client(KARIM) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(f"{BASE}/{pay['id']}/fund-escrow"), clients))
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    assert sum(not r.json()["idempotent_replay"] for r in results) == 1
    assert fund_rows(d["id"]) == 2 and funded_total(d["id"]) == Decimal("2880.00")


def test_concurrent_captures_charge_once(pp: FakePayPal, make_client: Any) -> None:
    from concurrent.futures import ThreadPoolExecutor

    karim = make_client(KARIM)
    d = new_deal(karim)
    pay = order(karim, d["id"]).json()
    pp.approve(pay["provider_order_id"])
    clients = [make_client(KARIM) for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda c: c.post(f"{BASE}/orders/{pay['id']}/capture"), clients))
    assert [r.status_code for r in results] == [200] * 4, [r.text for r in results]
    assert pp.capture_calls == 1 and row(pay["id"]).status.value == "CAPTURED"
