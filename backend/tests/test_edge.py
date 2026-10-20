"""Edge protection: rate limits, body limits, CORS in prod, security headers. No database."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

ORIGIN = "http://localhost:3000"
PROD_ENV = {
    "APP_ENV": "prod",
    "AUTH_MODE": "neon",
    "NEON_AUTH_BASE_URL": "https://ep-test.neonauth.example/neondb/auth",
    "ALLOWED_ORIGINS": "https://setu.example",
    "DEMO_SESSION_SECRET": "x" * 40,
    "DEMO_COOKIE_SECURE": "true",
    "DEMO_MODE": "false",
    "COOLING_OFF_SECONDS": "600",
    "OTP_SECRET_SEED": "o" * 40,
    "SMS_PROVIDER": "webhook",
    "SMS_WEBHOOK_URL": "https://sms.example/send",
    "SMS_WEBHOOK_TOKEN": "tok",
    "FIELD_ENCRYPTION_KEY": "K0rcLqO1kir_Q7_s431Rg5bR2x9BWm62knnkX6Fztvo=",
    "DOCUMENT_URL_SECRET": "d" * 40,
    "CRON_SECRET": "c" * 40,
    "MAIL_PROVIDER": "resend",
    "MAIL_RESEND_API_KEY": "re_test_key",
    "MAIL_FROM": "Setu <no-reply@setu.example>",
    "SANDBOXES_ENABLED": "false",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ALLOWED_ORIGINS", ORIGIN)
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., TestClient]:
    def make(ip: str = "203.0.113.7", **env: str) -> TestClient:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        return TestClient(create_app(), client=(ip, 5000))

    return make


def test_chat_is_limited_per_minute_with_problem_json_and_cors(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(RATE_LIMIT_CHAT_PER_MINUTE="3")
    for _ in range(3):
        assert c.post("/chat", json={}).status_code != 429
    res = c.post("/chat", json={}, headers={"Origin": ORIGIN})
    assert res.status_code == 429
    assert res.headers["content-type"].startswith("application/problem+json")
    assert int(res.headers["retry-after"]) >= 1
    assert res.json()["code"] == "RATE_LIMITED" and res.json()["status"] == 429
    assert res.headers["access-control-allow-origin"] == ORIGIN
    assert res.headers["x-content-type-options"] == "nosniff"
    assert c.post("/chat/stream", json={}).status_code == 429  # same bucket
    assert c.get("/auth/me").status_code != 429  # other routes are unaffected


def test_upload_and_sandbox_create_have_their_own_limits(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(RATE_LIMIT_UPLOAD_PER_MINUTE="2", RATE_LIMIT_SANDBOX_CREATE_PER_MINUTE="1")
    url = "/deals/00000000-0000-0000-0000-000000000000/documents"
    assert [c.post(url).status_code == 429 for _ in range(3)] == [False, False, True]
    assert c.post("/registry/lender-check/file").status_code == 429  # same upload bucket
    c2 = make_client(RATE_LIMIT_SANDBOX_CREATE_PER_MINUTE="1")
    assert c2.post("/demo/sandbox", json={}).status_code != 429
    assert c2.post("/demo/sandbox", json={}).status_code == 429


def test_global_limit_applies_but_health_and_preflight_are_exempt(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(RATE_LIMIT_GLOBAL_PER_MINUTE="3")
    for _ in range(3):
        assert c.get("/auth/me").status_code != 429
    assert c.get("/auth/me").status_code == 429
    for _ in range(10):
        assert c.get("/health").status_code == 200
    pre = c.options("/auth/me", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200


def test_clients_have_separate_counters(make_client: Callable[..., TestClient]) -> None:
    a = make_client("198.51.100.1", RATE_LIMIT_GLOBAL_PER_MINUTE="1")
    assert a.get("/auth/me").status_code != 429
    assert a.get("/auth/me").status_code == 429
    b = TestClient(a.app, client=("198.51.100.2", 1))
    assert b.get("/auth/me").status_code != 429


def test_forwarded_for_is_ignored_unless_the_peer_is_a_trusted_proxy(
    make_client: Callable[..., TestClient],
) -> None:
    spoof = {"X-Forwarded-For": "1.1.1.1"}
    c = make_client(RATE_LIMIT_GLOBAL_PER_MINUTE="2")
    assert c.get("/auth/me", headers=spoof).status_code != 429
    assert c.get("/auth/me", headers={"X-Forwarded-For": "2.2.2.2"}).status_code != 429
    assert c.get("/auth/me", headers={"X-Forwarded-For": "3.3.3.3"}).status_code == 429

    t = make_client("10.0.0.5", RATE_LIMIT_GLOBAL_PER_MINUTE="1", TRUSTED_PROXIES="10.0.0.0/8")
    assert t.get("/auth/me", headers={"X-Forwarded-For": "1.1.1.1"}).status_code != 429
    assert t.get("/auth/me", headers={"X-Forwarded-For": "2.2.2.2"}).status_code != 429
    assert t.get("/auth/me", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 429
    # the client-supplied left-most entry cannot be used to dodge the limit
    assert t.get("/auth/me", headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}).status_code == 429


def test_chat_limit_is_per_session_but_global_is_per_ip(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(RATE_LIMIT_CHAT_PER_MINUTE="1", RATE_LIMIT_GLOBAL_PER_MINUTE="3")
    one, two = {"Cookie": "setu_demo_session=a"}, {"Cookie": "setu_demo_session=b"}
    assert c.post("/chat", json={}, headers=one).status_code != 429
    assert c.post("/chat", json={}, headers=one).status_code == 429
    assert c.post("/chat", json={}, headers=two).status_code != 429  # other session, same IP
    assert c.post("/chat", json={}, headers={"Cookie": "setu_demo_session=c"}).status_code != 429
    assert c.post("/chat", json={}, headers={"Cookie": "setu_demo_session=d"}).status_code == 429


def test_limits_can_be_switched_off(make_client: Callable[..., TestClient]) -> None:
    c = make_client(RATE_LIMIT_ENABLED="false", RATE_LIMIT_GLOBAL_PER_MINUTE="1")
    assert all(c.get("/auth/me").status_code != 429 for _ in range(5))


def test_json_bodies_are_capped_at_max_body_bytes(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client(MAX_BODY_BYTES="1024")
    res = c.post("/auth/demo-login", content=b"x" * 2048, headers={"Origin": ORIGIN})
    assert res.status_code == 413 and res.json()["code"] == "BODY_TOO_LARGE"
    assert res.headers["access-control-allow-origin"] == ORIGIN

    def chunks() -> Iterator[bytes]:  # chunked: no Content-Length to check
        for _ in range(4):
            yield b"y" * 600

    streamed = c.post("/auth/demo-login", content=chunks())
    assert streamed.status_code == 413 and streamed.json()["code"] == "BODY_TOO_LARGE"
    small = c.post("/auth/demo-login", json={"email": "a@b.c"})
    assert small.status_code != 413


def test_uploads_keep_their_own_larger_limit(make_client: Callable[..., TestClient]) -> None:
    c = make_client(MAX_BODY_BYTES="1024", DOCUMENT_MAX_BYTES="4096")
    url = "/deals/00000000-0000-0000-0000-000000000000/documents"
    mid = c.post(url, content=b"z" * 3000)  # over MAX_BODY_BYTES, under the upload limit
    assert mid.status_code != 413
    big = c.post(url, content=b"z" * (4096 + 64 * 1024 + 1))
    assert big.status_code == 413 and big.json()["code"] == "FILE_TOO_LARGE"


def test_default_limits_fit_vercel() -> None:
    s = get_settings()
    assert s.max_body_bytes == 1024 * 1024
    assert s.document_max_bytes <= 4 * 1024 * 1024


def test_security_headers_on_every_response(make_client: Callable[..., TestClient]) -> None:
    c = make_client()
    for res in (c.get("/health"), c.get("/auth/me"), c.get("/nope")):
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert res.headers["referrer-policy"] == "no-referrer"
        assert "camera=()" in res.headers["permissions-policy"]
        assert "strict-transport-security" not in res.headers  # dev
    assert c.get("/auth/me").headers["cache-control"] == "no-store"
    assert c.get("/audit/verify").headers["cache-control"] == "no-store"
    assert "no-store" not in c.get("/health").headers.get("cache-control", "")


def test_hsts_only_in_prod(make_client: Callable[..., TestClient]) -> None:
    c = make_client(**PROD_ENV)
    hsts = c.get("/health").headers["strict-transport-security"]
    assert "max-age=" in hsts


@pytest.mark.parametrize("origins", ["*", "https://a.example,*", ""])
def test_prod_refuses_wildcard_or_empty_cors(
    make_client: Callable[..., TestClient], origins: str
) -> None:
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        make_client(**{**PROD_ENV, "ALLOWED_ORIGINS": origins})


def test_wildcard_cors_is_not_a_startup_error_outside_prod(
    make_client: Callable[..., TestClient],
) -> None:
    make_client(ALLOWED_ORIGINS="*")


def test_a_spoofed_internal_peer_name_is_still_limited(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client("testclient", RATE_LIMIT_GLOBAL_PER_MINUTE="1")
    spoof = {"X-Forwarded-For": "8.8.8.8"}
    assert c.get("/auth/me").status_code != 429
    assert c.get("/auth/me").status_code != 429  # the real in-process client is exempt
    assert c.get("/auth/me", headers=spoof).status_code != 429
    assert c.get("/auth/me", headers=spoof).status_code == 429
