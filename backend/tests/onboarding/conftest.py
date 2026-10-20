from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import ratelimit
from app.auth import neon
from app.config import get_settings
from app.main import create_app
from app.services import mail, sms
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.auth.support import BASE_URL, FakeNeon

pytestmark = pytest.mark.db


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, seeded_db: str) -> Iterator[FakeNeon]:  # noqa: F811
    f = FakeNeon()
    monkeypatch.setenv("AUTH_MODE", "neon")
    monkeypatch.setenv("NEON_AUTH_BASE_URL", BASE_URL)
    monkeypatch.setenv("STEPUP_REQUIRED", "false")  # step-up has its own tests (tests/auth)
    monkeypatch.setenv("DEMO_MODE", "true")  # the OTP demo_code; DEMO_MODE=false has its own tests
    get_settings.cache_clear()
    monkeypatch.setattr(neon, "_cache", f.cache())
    ratelimit.reset_limits()
    yield f
    ratelimit.reset_limits()
    get_settings.cache_clear()


@pytest.fixture
def client(fake: FakeNeon) -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def sms_box() -> Iterator[sms.OutboxSms]:
    box = sms.OutboxSms()
    sms.set_provider(box)
    yield box
    sms.set_provider(None)


@pytest.fixture
def mail_box() -> Iterator[mail.OutboxSender]:
    box = mail.OutboxSender()
    mail.set_sender(box)
    yield box
    mail.set_sender(None)
