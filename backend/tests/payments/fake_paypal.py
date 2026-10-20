"""An in-memory PayPal Sandbox for tests: same interface as the real adapter, no network."""

import itertools
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.services.payments.paypal_sandbox import (
    PayPalError,
    ProviderCapture,
    ProviderOrder,
)


class FakePayPal:
    def __init__(self) -> None:
        self._n = itertools.count(1)
        self._tag = uuid.uuid4().hex[:8].upper()  # ids stay unique across tests sharing a DB
        self.orders: dict[str, dict[str, Any]] = {}
        self.create_calls = 0
        self.capture_calls = 0
        self.webhook_genuine = True
        self.decline = False
        self.capture_amount: Decimal | None = None  # tamper: capture a different amount
        self.order_amount: Decimal | None = None  # tamper: report a different order amount
        self.capture_status = "COMPLETED"

    def _order(self, o: dict[str, Any]) -> ProviderOrder:
        caps = tuple(
            ProviderCapture(c["id"], c["status"], c["amount"], c["currency"]) for c in o["captures"]
        )
        return ProviderOrder(
            id=o["id"],
            status=o["status"],
            amount=self.order_amount if self.order_amount is not None else o["amount"],
            currency=o["currency"],
            custom_id=o["custom_id"],
            captures=caps,
        )

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
        self.create_calls += 1
        order_id = f"ORDER{self._tag}{next(self._n):04d}"
        self.orders[order_id] = {
            "id": order_id,
            "status": "CREATED",
            "amount": amount,
            "currency": currency,
            "custom_id": custom_id,
            "captures": [],
        }
        return self._order(self.orders[order_id])

    def approve(self, order_id: str) -> None:
        self.orders[order_id]["status"] = "APPROVED"

    def get_order(self, order_id: str) -> ProviderOrder:
        if order_id not in self.orders:
            raise PayPalError("RESOURCE_NOT_FOUND", 404)
        return self._order(self.orders[order_id])

    def capture_order(self, order_id: str, *, request_id: str) -> ProviderOrder:
        self.capture_calls += 1
        o = self.orders[order_id]
        if self.decline:
            raise PayPalError("INSTRUMENT_DECLINED", 422)
        if o["status"] == "COMPLETED":
            raise PayPalError("ORDER_ALREADY_CAPTURED", 422)
        if o["status"] != "APPROVED":
            raise PayPalError("ORDER_NOT_APPROVED", 422)
        amount = self.capture_amount if self.capture_amount is not None else o["amount"]
        o["captures"].append(
            {
                "id": f"CAP{self._tag}{next(self._n):04d}",
                "status": self.capture_status,
                "amount": amount,
                "currency": o["currency"],
            }
        )
        o["status"] = "COMPLETED"
        return self._order(o)

    def verify_webhook(self, headers: Mapping[str, str], event: dict[str, Any]) -> bool:
        return self.webhook_genuine


def capture_event(
    event_id: str,
    order_id: str,
    capture_id: str,
    amount: str,
    *,
    currency: str = "USD",
    event_type: str = "PAYMENT.CAPTURE.COMPLETED",
    custom_id: str | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "id": capture_id,
        "status": "COMPLETED",
        "amount": {"currency_code": currency, "value": amount},
        "supplementary_data": {"related_ids": {"order_id": order_id}},
    }
    if custom_id:
        resource["custom_id"] = custom_id
    return {"id": event_id, "event_type": event_type, "resource": resource}
