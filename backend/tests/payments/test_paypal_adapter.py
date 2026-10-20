import json
from decimal import Decimal

import httpx
import pytest

from app.config import Settings, get_settings
from app.errors import ServiceUnavailable
from app.services.payments import paypal_sandbox as pp

HEADERS = {
    "PAYPAL-AUTH-ALGO": "SHA256withRSA",
    "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1",
    "PAYPAL-TRANSMISSION-ID": "tid-1",
    "PAYPAL-TRANSMISSION-SIG": "sig",
    "PAYPAL-TRANSMISSION-TIME": "2026-10-24T00:00:00Z",
}


def client(handler: httpx.MockTransport, webhook_id: str | None = "WH-1") -> pp.PayPalSandboxClient:
    return pp.PayPalSandboxClient("cid", "secret", webhook_id, transport=handler)


def order_json(status: str = "CREATED", captures: list[dict] | None = None) -> dict:
    unit: dict = {"custom_id": "pay-1", "amount": {"currency_code": "USD", "value": "100.00"}}
    if captures is not None:
        unit["payments"] = {"captures": captures}
    return {"id": "ORD-1", "status": status, "purchase_units": [unit]}


class Recorder:
    def __init__(self, routes: dict[tuple[str, str], tuple[int, dict]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        status, body = self.routes[(request.method, request.url.path)]
        return httpx.Response(status, json=body)


def test_every_request_goes_to_the_sandbox_host_only() -> None:
    rec = Recorder({("GET", "/v2/checkout/orders/ORD-1"): (200, order_json())})
    c = client(httpx.MockTransport(rec))
    c.get_order("ORD-1")
    assert {r.url.host for r in rec.requests} == {"api-m.sandbox.paypal.com"}
    assert pp.SANDBOX_API == "https://api-m.sandbox.paypal.com"
    assert not any("paypal" in name and "url" in name for name in Settings.model_fields)


def test_token_is_fetched_once_and_cached() -> None:
    rec = Recorder({("GET", "/v2/checkout/orders/ORD-1"): (200, order_json())})
    c = client(httpx.MockTransport(rec))
    c.get_order("ORD-1")
    c.get_order("ORD-1")
    assert sum(r.url.path == "/v1/oauth2/token" for r in rec.requests) == 1
    assert rec.requests[-1].headers["authorization"] == "Bearer tok"


def test_create_order_sends_the_server_amount_and_request_id() -> None:
    rec = Recorder({("POST", "/v2/checkout/orders"): (201, order_json())})
    c = client(httpx.MockTransport(rec))
    out = c.create_order(
        amount=Decimal("100"),
        currency="USD",
        reference="SETU-1",
        custom_id="pay-1",
        description="d",
        request_id="req-1",
    )
    sent = rec.requests[-1]
    body = json.loads(sent.content)
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "100.00"}
    assert body["purchase_units"][0]["custom_id"] == "pay-1"
    assert sent.headers["paypal-request-id"] == "req-1"
    assert (out.id, out.amount, out.custom_id) == ("ORD-1", Decimal("100.00"), "pay-1")


def test_capture_parses_the_completed_capture() -> None:
    caps = [
        {
            "id": "CAP-1",
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "100.00"},
        }
    ]
    rec = Recorder(
        {("POST", "/v2/checkout/orders/ORD-1/capture"): (201, order_json("COMPLETED", caps))}
    )
    out = client(httpx.MockTransport(rec)).capture_order("ORD-1", request_id="req-1")
    assert out.status == "COMPLETED"
    assert out.captures[0].id == "CAP-1" and out.captures[0].amount == Decimal("100.00")
    assert rec.requests[-1].headers["paypal-request-id"] == "req-1"


def test_paypal_error_issue_is_surfaced() -> None:
    err = {"name": "UNPROCESSABLE_ENTITY", "details": [{"issue": "INSTRUMENT_DECLINED"}]}
    rec = Recorder({("POST", "/v2/checkout/orders/ORD-1/capture"): (422, err)})
    with pytest.raises(pp.PayPalError) as exc:
        client(httpx.MockTransport(rec)).capture_order("ORD-1", request_id="r")
    assert exc.value.issue == "INSTRUMENT_DECLINED"


def test_server_error_and_network_error_are_unavailable() -> None:
    rec = Recorder({("GET", "/v2/checkout/orders/ORD-1"): (503, {})})
    with pytest.raises(pp.PayPalUnavailable):
        client(httpx.MockTransport(rec)).get_order("ORD-1")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(pp.PayPalUnavailable):
        client(httpx.MockTransport(boom)).get_order("ORD-1")


def test_rejected_credentials_are_unavailable_not_a_crash() -> None:
    def deny(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client"})

    with pytest.raises(pp.PayPalUnavailable):
        client(httpx.MockTransport(deny)).get_order("ORD-1")


def test_webhook_verification_success_failure_and_malformed() -> None:
    ok = Recorder(
        {
            ("POST", "/v1/notifications/verify-webhook-signature"): (
                200,
                {"verification_status": "SUCCESS"},
            )
        }
    )
    assert client(httpx.MockTransport(ok)).verify_webhook(HEADERS, {"id": "WH-EVT"}) is True
    sent = json.loads(ok.requests[-1].content)
    assert sent["webhook_id"] == "WH-1" and sent["transmission_id"] == "tid-1"

    bad = Recorder(
        {
            ("POST", "/v1/notifications/verify-webhook-signature"): (
                200,
                {"verification_status": "FAILURE"},
            )
        }
    )
    assert client(httpx.MockTransport(bad)).verify_webhook(HEADERS, {"id": "x"}) is False

    never = Recorder({})
    c = client(httpx.MockTransport(never))
    assert (
        c.verify_webhook({k: v for k, v in HEADERS.items() if k != "PAYPAL-TRANSMISSION-SIG"}, {})
        is False
    )
    assert (
        c.verify_webhook({**HEADERS, "PAYPAL-CERT-URL": "https://evil.example.com/cert"}, {})
        is False
    )
    assert client(httpx.MockTransport(never), webhook_id=None).verify_webhook(HEADERS, {}) is False
    assert never.requests == []  # nothing was sent to PayPal for a request that cannot be genuine


def test_gateway_is_unavailable_until_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENABLED", "CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.delenv(f"PAYPAL_SANDBOX_{name}", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ServiceUnavailable) as exc:
        pp.get_gateway()
    assert exc.value.code == "PAYPAL_NOT_CONFIGURED"
    monkeypatch.setenv("PAYPAL_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("PAYPAL_SANDBOX_CLIENT_ID", "cid")
    get_settings.cache_clear()
    with pytest.raises(ServiceUnavailable):  # id without a secret is still not configured
        pp.get_gateway()
    get_settings.cache_clear()
