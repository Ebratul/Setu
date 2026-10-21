"""Outgoing SMS behind one interface. `ConsoleSms` (SMS_PROVIDER=console, dev) logs a message id
and the masked number, never the text or the code. `WebhookSms` (SMS_PROVIDER=webhook, required in
prod) posts to the operator's gateway over https. `OutboxSms` is the test double."""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import structlog

from app.config import get_settings
from app.security.crypto import mask_phone

log = structlog.get_logger("setu.sms")


class SmsError(Exception):
    """Delivery failed (never carries the number or the text)."""


@dataclass(frozen=True, slots=True)
class Sms:
    to: str
    text: str
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class SmsProvider(Protocol):
    def send(self, sms: Sms) -> None: ...


class ConsoleSms:
    def send(self, sms: Sms) -> None:
        log.info("sms_console", message_id=sms.message_id, to=mask_phone(sms.to))


class WebhookSms:
    """Hands the message to an SMS gateway of the operator's choice: one authenticated JSON POST
    `{to, text, message_id}` to SMS_WEBHOOK_URL with `Authorization: Bearer SMS_WEBHOOK_TOKEN`
    (any 2xx = sent). The gateway owns real delivery; nothing about the text is logged here."""

    def __init__(self, url: str, token: str) -> None:
        self.url, self.token = url, token

    def send(self, sms: Sms) -> None:
        try:
            res = httpx.post(
                self.url,
                json={"to": sms.to, "text": sms.text, "message_id": sms.message_id},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5.0,
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("sms_webhook_failed", error=type(exc).__name__, message_id=sms.message_id)
            raise SmsError("gateway refused the message") from None


class OutboxSms:
    def __init__(self) -> None:
        self.sent: list[Sms] = []
        self.fail = False

    def send(self, sms: Sms) -> None:
        if self.fail:
            raise SmsError("outbox set to fail")
        self.sent.append(sms)


_override: SmsProvider | None = None


def set_provider(provider: SmsProvider | None) -> None:
    global _override
    _override = provider


def get_provider() -> SmsProvider:
    if _override is not None:
        return _override
    s = get_settings()
    if s.sms_provider == "webhook":
        token = s.sms_webhook_token.get_secret_value() if s.sms_webhook_token else ""
        if not s.sms_webhook_url or not token:
            raise SmsError("SMS webhook is not configured")
        if not s.sms_webhook_url.startswith("https://") and s.app_env != "test":
            raise SmsError("SMS webhook must use https")
        return WebhookSms(s.sms_webhook_url, token)
    return ConsoleSms()
