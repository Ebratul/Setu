"""Outgoing mail. One narrow seam so the OTP and step-up codes can be delivered by email.

`ConsoleSender` (dev/test default) logs only a message id and the recipient's domain; it never
writes the body, a code or a full address. `ResendSender` posts to the Resend HTTPS API.
`OutboxSender` keeps messages in memory for tests. Any delivery problem raises `MailError`; callers
turn it into `ServiceUnavailable("could not send the code")` and never echo the code back."""

import uuid
from dataclasses import dataclass, field
from html import escape
from typing import Protocol

import httpx
import structlog

from app.config import get_settings
from app.errors import ServiceUnavailable

log = structlog.get_logger("setu.mail")
RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 5.0


class MailError(Exception):
    """Delivery failed. The message never carries the mail body, key or address."""


@dataclass(frozen=True, slots=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class MailSender(Protocol):
    def send(self, mail: Mail) -> None: ...


def domain_of(address: str) -> str:
    return address.rpartition("@")[2].lower() or "unknown"


class ConsoleSender:
    def send(self, mail: Mail) -> None:
        log.info("mail_console", message_id=mail.message_id, to_domain=domain_of(mail.to))


class OutboxSender:
    """Test double: everything "sent" lands in `.sent`."""

    def __init__(self) -> None:
        self.sent: list[Mail] = []
        self.fail = False

    def send(self, mail: Mail) -> None:
        if self.fail:
            raise MailError("outbox set to fail")
        self.sent.append(mail)


class ResendSender:
    def __init__(self, api_key: str, from_address: str) -> None:
        self._key = api_key
        self._from = from_address

    def send(self, mail: Mail) -> None:
        payload = {
            "from": self._from,
            "to": [mail.to],
            "subject": mail.subject,
            "text": mail.text,
            "html": mail.html,
        }
        try:
            res = httpx.post(
                RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            log.warning("mail_failed", message_id=mail.message_id, reason=type(exc).__name__)
            raise MailError("mail provider unreachable") from None
        if res.status_code >= 300:
            log.warning("mail_failed", message_id=mail.message_id, status=res.status_code)
            raise MailError(f"mail provider answered {res.status_code}")
        log.info("mail_sent", message_id=mail.message_id, to_domain=domain_of(mail.to))


_override: MailSender | None = None


def set_sender(sender: MailSender | None) -> None:
    """Tests install an OutboxSender here; None restores the configured one."""
    global _override
    _override = sender


def get_sender() -> MailSender:
    if _override is not None:
        return _override
    s = get_settings()
    if s.mail_provider == "resend":
        key = s.mail_resend_api_key.get_secret_value() if s.mail_resend_api_key else ""
        if not key or not s.mail_from:
            raise MailError("mail is not configured")
        return ResendSender(key, s.mail_from)
    return ConsoleSender()


def deliver(mail: Mail) -> None:
    """Send or raise ServiceUnavailable (nothing about the mail or the code in the error)."""
    try:
        get_sender().send(mail)
    except MailError:
        raise ServiceUnavailable("could not send the code") from None


def code_mail(
    to: str,
    code: str,
    *,
    subject: tuple[str, str],
    what: tuple[str, str],
    reference: str | None,
    minutes: int,
) -> Mail:
    """A one-time-code mail, English then Bangla. `what` is the action label, `reference` the
    deal reference (both already safe text; escaped again for HTML)."""
    ref_en = f" Deal: {reference}." if reference else ""
    ref_bn = f" ডিল: {reference}।" if reference else ""
    text = (
        f"Your Setu code is {code}\n"
        f"{what[0]}.{ref_en}\n"
        f"It expires in {minutes} minutes. Never share this code, not even with Setu staff.\n"
        "If you did not expect this, do not use the code: reject the request in Setu.\n"
        "\n---\n\n"
        f"আপনার সেতু কোড: {code}\n"
        f"{what[1]}।{ref_bn}\n"
        f"কোডটির মেয়াদ {minutes} মিনিট। এই কোড কাউকে বলবেন না।\n"
        "আপনি এটি আশা না করলে কোড ব্যবহার করবেন না; সেতুতে অনুরোধটি প্রত্যাখ্যান করুন।\n"
    )
    e = escape
    html = (
        '<div style="font-family:sans-serif;max-width:480px">'
        f'<p>Your Setu code is</p><p style="font-size:28px;letter-spacing:4px"><b>{e(code)}</b></p>'
        f"<p>{e(what[0])}.{e(ref_en)}</p>"
        f"<p>It expires in {minutes} minutes. <b>Never share this code.</b> "
        "If you did not expect this, reject the request in Setu.</p><hr>"
        f"<p>আপনার সেতু কোড: <b>{e(code)}</b></p>"
        f"<p>{e(what[1])}।{e(ref_bn)}</p>"
        f"<p>মেয়াদ {minutes} মিনিট। <b>কোড কাউকে বলবেন না।</b> "
        "আশা না করলে সেতুতে অনুরোধটি প্রত্যাখ্যান করুন।</p></div>"
    )
    return Mail(to=to, subject=f"{subject[0]} / {subject[1]}", text=text, html=html)
