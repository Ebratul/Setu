"""Production startup guard (phase D): one refusal per unsafe or missing setting, no dev-secret
fallbacks in prod, and the cooling-off floor. No database."""

import uuid
from datetime import UTC, datetime

import pytest

from app.auth import demo
from app.config import get_settings
from app.main import check_prod_settings, create_app
from app.services import approval_otp
from app.services.documents import signing

GOOD = {
    "APP_ENV": "prod",
    "AUTH_MODE": "neon",
    "NEON_AUTH_BASE_URL": "https://ep-test.neonauth.example/neondb/auth",
    "ALLOWED_ORIGINS": "https://setu.example,https://www.setu.example",
    "DEMO_SESSION_SECRET": "x" * 40,
    "DEMO_COOKIE_SECURE": "true",
    "DEMO_MODE": "false",
    "COOLING_OFF_SECONDS": "600",
    "OTP_SECRET_SEED": "o" * 40,
    "DOCUMENT_URL_SECRET": "d" * 40,
    "CRON_SECRET": "c" * 40,
    "MAIL_PROVIDER": "resend",
    "MAIL_RESEND_API_KEY": "re_test_key",
    "MAIL_FROM": "Setu <no-reply@setu.example>",
    "DEMO_REPLAY": "false",
    "SANDBOXES_ENABLED": "false",
    "ENABLE_DEV_EVIDENCE": "false",
    "ONBOARDING_AUTO_APPROVE": "false",
    "STEPUP_REQUIRED": "true",
    "FOUR_EYES_ENFORCE": "true",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    def apply(**over: str) -> None:
        for k, v in {**GOOD, **over}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()

    yield apply
    get_settings.cache_clear()


def test_the_good_configuration_starts(env) -> None:
    env()
    check_prod_settings(get_settings())
    assert create_app() is not None


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"OTP_SECRET_SEED": ""}, "OTP_SECRET_SEED"),
        ({"OTP_SECRET_SEED": "short"}, "OTP_SECRET_SEED"),
        ({"OTP_SECRET_SEED": "o" * 31}, "OTP_SECRET_SEED"),
        ({"DOCUMENT_URL_SECRET": ""}, "DOCUMENT_URL_SECRET"),
        ({"DOCUMENT_URL_SECRET": "d" * 31}, "DOCUMENT_URL_SECRET"),
        ({"CRON_SECRET": ""}, "CRON_SECRET"),
        ({"CRON_SECRET": "c" * 31}, "CRON_SECRET"),
        ({"MAIL_PROVIDER": "console"}, "MAIL_PROVIDER"),
        ({"MAIL_RESEND_API_KEY": ""}, "MAIL_RESEND_API_KEY"),
        ({"MAIL_FROM": ""}, "MAIL_FROM"),
        ({"DEMO_REPLAY": "true"}, "DEMO_REPLAY"),
        ({"SANDBOXES_ENABLED": "true"}, "SANDBOXES_ENABLED"),
        ({"ENABLE_DEV_EVIDENCE": "true"}, "ENABLE_DEV_EVIDENCE"),
        ({"STEPUP_REQUIRED": "false"}, "STEPUP_REQUIRED"),
        ({"FOUR_EYES_ENFORCE": "false"}, "FOUR_EYES_ENFORCE"),
        ({"ONBOARDING_AUTO_APPROVE": "true"}, "ONBOARDING_AUTO_APPROVE"),
        ({"ALLOWED_ORIGINS": "http://setu.example"}, "https"),
        ({"ALLOWED_ORIGINS": "https://setu.example,http://localhost:3000"}, "https"),
        ({"ALLOWED_ORIGINS": "http://localhost:3000"}, "https"),
        ({"COOLING_OFF_SECONDS": "599"}, "COOLING_OFF_SECONDS"),
        ({"DEMO_MODE": "true"}, "DEMO_MODE"),
        ({"AUTH_MODE": "demo"}, "AUTH_MODE"),
    ],
)
def test_prod_refuses_each_unsafe_setting(env, over: dict[str, str], match: str) -> None:
    env(**over)
    with pytest.raises(RuntimeError, match=match):
        check_prod_settings(get_settings())
    with pytest.raises(RuntimeError):
        create_app()


def test_stepup_and_four_eyes_may_be_left_unset_in_prod_because_they_default_on(env) -> None:
    env()
    import os

    os.environ.pop("STEPUP_REQUIRED")
    os.environ.pop("FOUR_EYES_ENFORCE")
    get_settings.cache_clear()
    settings = get_settings()
    check_prod_settings(settings)
    assert settings.stepup_enabled and settings.four_eyes_active


def test_localhost_and_demo_switches_are_fine_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in GOOD:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("SANDBOXES_ENABLED", "true")
    monkeypatch.setenv("STEPUP_REQUIRED", "false")
    get_settings.cache_clear()
    check_prod_settings(get_settings())
    get_settings.cache_clear()


# --- no dev-secret fallback in prod ----------------------------------------------------------


def test_otp_secret_has_no_fallback_in_prod(env) -> None:
    env(OTP_SECRET_SEED="")  # the guard is bypassed here on purpose
    with pytest.raises(RuntimeError, match="OTP_SECRET_SEED"):
        approval_otp.hash_code(uuid.uuid4(), "123456")
    env(OTP_SECRET_SEED="short")
    with pytest.raises(RuntimeError, match="OTP_SECRET_SEED"):
        approval_otp.hash_code(uuid.uuid4(), "123456")


def test_the_demo_session_secret_does_not_stand_in_for_the_otp_seed_in_prod(env) -> None:
    env(OTP_SECRET_SEED="", DEMO_SESSION_SECRET="y" * 40)
    with pytest.raises(RuntimeError):
        approval_otp.secret_key()


def test_demo_cookie_secret_has_no_fallback_in_prod(env) -> None:
    env(DEMO_SESSION_SECRET="")
    with pytest.raises(RuntimeError, match="DEMO_SESSION_SECRET"):
        demo.make_token(uuid.uuid4())


def test_document_url_secret_has_no_fallback_in_prod(env) -> None:
    env(DOCUMENT_URL_SECRET="")
    with pytest.raises(RuntimeError, match="DOCUMENT_URL_SECRET"):
        signing.encode(signing.make_token(uuid.uuid4(), uuid.uuid4()))
    env(DOCUMENT_URL_SECRET="d" * 40, DEMO_SESSION_SECRET="y" * 40)
    assert signing.encode(signing.make_token(uuid.uuid4(), uuid.uuid4()))


def test_dev_fallbacks_still_work_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("OTP_SECRET_SEED", "DEMO_SESSION_SECRET", "DOCUMENT_URL_SECRET"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    assert approval_otp.secret_key() == approval_otp.DEV_SECRET
    assert demo.parse_token(demo.make_token(uuid.uuid4())) is not None
    get_settings.cache_clear()


# --- cooling-off floor -----------------------------------------------------------------------


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("hostile", ["0", "1", "30", "599"])
def test_cooling_off_is_at_least_600_seconds_in_prod_whatever_the_setting(
    monkeypatch: pytest.MonkeyPatch, hostile: str
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("COOLING_OFF_SECONDS", hostile)
    get_settings.cache_clear()
    until = approval_otp.cooling_off_until(NOW, 3)
    assert until is not None and (until - NOW).total_seconds() == 600
    get_settings.cache_clear()


def test_cooling_off_longer_than_the_floor_is_kept_and_demo_values_work_outside_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("COOLING_OFF_SECONDS", "900")
    get_settings.cache_clear()
    until = approval_otp.cooling_off_until(NOW, 3)
    assert until is not None and (until - NOW).total_seconds() == 900
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("COOLING_OFF_SECONDS", "30")
    get_settings.cache_clear()
    until = approval_otp.cooling_off_until(NOW, 3)
    assert until is not None and (until - NOW).total_seconds() == 30
    assert approval_otp.cooling_off_until(NOW, 2) is None
    get_settings.cache_clear()
