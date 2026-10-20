"""PayPal Sandbox adapter: OAuth token, order create / read / capture, webhook verification.

Sandbox only. The API host is the constant below and there is no setting for it, so a live host
cannot be configured; live credentials do not work against the Sandbox host either. The adapter
knows nothing about deals, escrow or the ledger: it moves bytes to and from PayPal and returns
parsed, typed facts. Everything it returns is provider data to be checked by the caller against
the stored payment, never trusted for amounts or ownership.
"""

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import structlog

from app.config import get_settings
from app.domain.money import q2
from app.errors import ServiceUnavailable

log = structlog.get_logger("setu.paypal")

SANDBOX_API = "https://api-m.sandbox.paypal.com"
WEBHOOK_HEADERS = (
    "paypal-auth-algo",
    "paypal-cert-url",
    "paypal-transmission-id",
    "paypal-transmission-sig",
    "paypal-transmission-time",
)
_TOKEN_SKEW_SECONDS = 60


class PayPalError(Exception):
    """PayPal answered with an error. `issue` is PayPal's own code (e.g. INSTRUMENT_DECLINED)."""

    def __init__(self, issue: str, http_status: int, message: str = "") -> None:
        super().__init__(message or issue)
        self.issue = issue
        self.http_status = http_status


class PayPalUnavailable(Exception):
    """The request never produced a usable answer (network error, timeout, 5xx)."""


@dataclass(frozen=True, slots=True)
class ProviderCapture:
    id: str
    status: str
    amount: Decimal | None
    currency: str | None


@dataclass(frozen=True, slots=True)
class ProviderOrder:
    id: str
    status: str
    amount: Decimal | None
    currency: str | None
    custom_id: str | None
    captures: tuple[ProviderCapture, ...]


class PayPalGateway(Protocol):
    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference: str,
        custom_id: str,
        description: str,
        request_id: str,
    ) -> ProviderOrder: ...

    def get_order(self, order_id: str) -> ProviderOrder: ...

    def capture_order(self, order_id: str, *, request_id: str) -> ProviderOrder: ...

    def verify_webhook(self, headers: Mapping[str, str], event: dict[str, Any]) -> bool: ...


def _decimal(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def parse_capture(raw: Mapping[str, Any]) -> ProviderCapture:
    amount = raw.get("amount") or {}
    return ProviderCapture(
        id=str(raw.get("id", "")),
        status=str(raw.get("status", "")),
        amount=_decimal(amount.get("value")),
        currency=amount.get("currency_code"),
    )


def parse_order(raw: Mapping[str, Any]) -> ProviderOrder:
    units = raw.get("purchase_units") or [{}]
    unit = units[0]
    amount = unit.get("amount") or {}
    captures = ((unit.get("payments") or {}).get("captures")) or []
    return ProviderOrder(
        id=str(raw.get("id", "")),
        status=str(raw.get("status", "")),
        amount=_decimal(amount.get("value")),
        currency=amount.get("currency_code"),
        custom_id=unit.get("custom_id"),
        captures=tuple(parse_capture(c) for c in captures),
    )


def cert_url_is_paypal(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and (host == "paypal.com" or host.endswith(".paypal.com"))


class PayPalSandboxClient:
    """Synchronous httpx client. One OAuth token is cached per process until shortly before it
    expires. `transport` lets tests answer without the network."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        webhook_id: str | None,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._webhook_id = webhook_id
        self._http = httpx.Client(base_url=SANDBOX_API, timeout=timeout, transport=transport)
        self._lock = threading.Lock()
        self._token: str | None = None
        self._token_expires = 0.0

    def close(self) -> None:
        self._http.close()

    def _access_token(self, *, force: bool = False) -> str:
        with self._lock:
            if not force and self._token and time.monotonic() < self._token_expires:
                return self._token
            try:
                res = self._http.post(
                    "/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise PayPalUnavailable("token request failed") from exc
            if res.status_code != 200:
                log.warning("paypal_token_refused", status=res.status_code)
                raise PayPalUnavailable(f"token request refused ({res.status_code})")
            body = res.json()
            self._token = str(body["access_token"])
            self._token_expires = time.monotonic() + max(
                int(body.get("expires_in", 300)) - _TOKEN_SKEW_SECONDS, 0
            )
            return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        for attempt in (0, 1):
            headers = {
                "Authorization": f"Bearer {self._access_token(force=attempt == 1)}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            try:
                res = self._http.request(method, path, json=json, headers=headers)
            except httpx.HTTPError as exc:
                raise PayPalUnavailable(f"{method} {path} failed") from exc
            if res.status_code == 401 and attempt == 0:
                continue
            break
        if res.status_code >= 500:
            raise PayPalUnavailable(f"{method} {path} -> {res.status_code}")
        body: dict[str, Any] = res.json() if res.content else {}
        if res.status_code >= 400:
            details = body.get("details") or [{}]
            issue = str(details[0].get("issue") or body.get("name") or "UNKNOWN")
            raise PayPalError(issue, res.status_code, str(body.get("message", "")))
        return body

    def create_order(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference: str,
        custom_id: str,
        description: str,
        request_id: str,
    ) -> ProviderOrder:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": reference[:256],
                    "custom_id": custom_id,
                    "description": description[:127],
                    "amount": {"currency_code": currency, "value": f"{q2(amount):.2f}"},
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                    }
                }
            },
        }
        return parse_order(
            self._request("POST", "/v2/checkout/orders", json=body, request_id=request_id)
        )

    def get_order(self, order_id: str) -> ProviderOrder:
        return parse_order(self._request("GET", f"/v2/checkout/orders/{order_id}"))

    def capture_order(self, order_id: str, *, request_id: str) -> ProviderOrder:
        return parse_order(
            self._request(
                "POST", f"/v2/checkout/orders/{order_id}/capture", json={}, request_id=request_id
            )
        )

    def verify_webhook(self, headers: Mapping[str, str], event: dict[str, Any]) -> bool:
        """PayPal's own signature check. False for anything but an explicit SUCCESS."""
        lower = {k.lower(): v for k, v in headers.items()}
        if not self._webhook_id or any(not lower.get(h) for h in WEBHOOK_HEADERS):
            return False
        if not cert_url_is_paypal(lower["paypal-cert-url"]):
            return False
        body = {
            "auth_algo": lower["paypal-auth-algo"],
            "cert_url": lower["paypal-cert-url"],
            "transmission_id": lower["paypal-transmission-id"],
            "transmission_sig": lower["paypal-transmission-sig"],
            "transmission_time": lower["paypal-transmission-time"],
            "webhook_id": self._webhook_id,
            "webhook_event": event,
        }
        try:
            out = self._request("POST", "/v1/notifications/verify-webhook-signature", json=body)
        except PayPalError:
            return False
        return out.get("verification_status") == "SUCCESS"


_client: PayPalSandboxClient | None = None
_client_key: tuple[str, str, str | None] | None = None
_client_lock = threading.Lock()


def get_gateway() -> PayPalGateway:
    """The process-wide Sandbox client, built from settings. 503 when it is not configured."""
    global _client, _client_key
    settings = get_settings()
    secret = settings.paypal_sandbox_client_secret
    if not settings.paypal_sandbox_ready or secret is None or not settings.paypal_sandbox_client_id:
        raise ServiceUnavailable("PayPal Sandbox is not configured", "PAYPAL_NOT_CONFIGURED")
    key = (
        settings.paypal_sandbox_client_id,
        secret.get_secret_value(),
        settings.paypal_sandbox_webhook_id,
    )
    with _client_lock:
        if _client is None or _client_key != key:
            if _client is not None:
                _client.close()
            _client = PayPalSandboxClient(*key, timeout=settings.paypal_sandbox_timeout_seconds)
            _client_key = key
        return _client
