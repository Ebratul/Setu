"""Mail senders: nothing sensitive in logs, failures become a safe 503, Resend call shape."""

from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from app.config import get_settings
from app.errors import ServiceUnavailable
from app.services import mail

CODE = "482913"


def sample() -> mail.Mail:
    return mail.code_mail(
        "someone.private@customer.example",
        CODE,
        subject=("Subject", "বিষয়"),
        what=("Release <b>a tranche</b>", "কিস্তি"),
        reference="SETU-2026-0001",
        minutes=5,
    )


def test_template_has_both_languages_and_escapes_html() -> None:
    m = sample()
    assert CODE in m.text and CODE in m.html
    assert "SETU-2026-0001" in m.text and "5 minutes" in m.text and "মিনিট" in m.text
    assert "Never share" in m.text and "reject the request" in m.text
    assert "&lt;b&gt;" in m.html and "<b>a tranche</b>" not in m.html


def test_console_sender_logs_only_id_and_domain() -> None:
    m = sample()
    with capture_logs() as logs:
        mail.ConsoleSender().send(m)
    assert logs == [
        {
            "event": "mail_console",
            "log_level": "info",
            "message_id": m.message_id,
            "to_domain": "customer.example",
        }
    ]
    assert CODE not in str(logs) and "someone.private" not in str(logs)


def test_outbox_keeps_messages() -> None:
    box = mail.OutboxSender()
    box.send(sample())
    assert len(box.sent) == 1 and box.sent[0].to.endswith("@customer.example")


class FakeResponse:
    def __init__(self, code: int) -> None:
        self.status_code = code


def resend(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def post(url: str, **kw: Any) -> FakeResponse:
        calls.append({"url": url, **kw})
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr(httpx, "post", post)
    return calls


def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.setenv("MAIL_RESEND_API_KEY", "re_secret_key_value")
    monkeypatch.setenv("MAIL_FROM", "Setu <no-reply@setu.example>")
    get_settings.cache_clear()


def test_resend_posts_json_with_a_5_second_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    configured(monkeypatch)
    calls = resend(monkeypatch, 200)
    with capture_logs() as logs:
        mail.deliver(sample())
    [call] = calls
    assert call["url"] == "https://api.resend.com/emails" and call["timeout"] == 5.0
    assert call["headers"]["Authorization"] == "Bearer re_secret_key_value"
    assert call["json"]["from"] == "Setu <no-reply@setu.example>"
    assert call["json"]["to"] == ["someone.private@customer.example"]
    assert "re_secret_key_value" not in str(logs) and CODE not in str(logs)
    get_settings.cache_clear()


@pytest.mark.parametrize("outcome", [500, 422, httpx.ConnectTimeout("t"), httpx.ConnectError("c")])
def test_resend_failures_become_a_safe_503(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> None:
    configured(monkeypatch)
    resend(monkeypatch, outcome)
    with capture_logs() as logs, pytest.raises(ServiceUnavailable) as exc:
        mail.deliver(sample())
    assert exc.value.detail == "could not send the code"
    assert CODE not in str(logs) and "re_secret_key_value" not in str(logs)
    assert "someone.private" not in str(logs)
    get_settings.cache_clear()


def test_resend_without_a_key_or_sender_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_PROVIDER", "resend")
    monkeypatch.setenv("MAIL_RESEND_API_KEY", "")
    monkeypatch.setenv("MAIL_FROM", "")
    get_settings.cache_clear()
    with pytest.raises(ServiceUnavailable):
        mail.deliver(sample())
    get_settings.cache_clear()


def test_default_provider_is_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    get_settings.cache_clear()
    assert isinstance(mail.get_sender(), mail.ConsoleSender)
    get_settings.cache_clear()
