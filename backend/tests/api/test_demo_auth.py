import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.demo import COOKIE_NAME, MAX_AGE_SECONDS, make_token, parse_token
from tests.api.conftest import login

UID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_token_round_trip_and_tamper() -> None:
    token = make_token(UID, now=1000)
    assert parse_token(token, now=1000) == UID
    uid, issued, sig = token.split(".")
    other = uuid.UUID(int=2)
    assert parse_token(f"{other}.{issued}.{sig}", now=1000) is None
    assert parse_token(f"{uid}.{issued}.{'0' * 64}", now=1000) is None
    assert parse_token("garbage", now=1000) is None


def test_token_expires() -> None:
    token = make_token(UID, now=1000)
    assert parse_token(token, now=1000 + MAX_AGE_SECONDS) == UID
    assert parse_token(token, now=1001 + MAX_AGE_SECONDS) is None
    assert parse_token(token, now=999) is None


@pytest.mark.db
def test_login_me_logout(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401
    me = login(client, "rahima@demo.setu").get("/auth/me").json()
    assert me["role"] == "BUYER" and me["party_name"] == "Rahima Knitwear"
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401


@pytest.mark.db
def test_forged_cookie_and_unknown_user_rejected(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, f"{uuid.uuid4()}.1.{'a' * 64}")
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/demo-login", json={"email": "nobody@x"}).status_code == 404
    users = client.get("/auth/demo-users").json()["users"]
    assert {u["email"] for u in users} >= {"rahima@demo.setu", "judge@demo.setu"}


@pytest.mark.parametrize("token", ["a.b.é", "a.b.", "a.b.c.d", "", "é"])
def test_malformed_tokens_never_raise(token: str) -> None:
    assert parse_token(token) is None


@pytest.mark.db
def test_non_ascii_cookie_is_401_problem_json(client: TestClient) -> None:
    raw = f"{COOKIE_NAME}=a.b.\u00e9".encode("latin-1")
    res = client.get("/analysis/orders", headers={"cookie": raw})  # type: ignore[dict-item]
    assert res.status_code == 401
    assert res.headers["content-type"].startswith("application/problem+json")


def test_prod_requires_real_secret_and_secure_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("DEMO_SESSION_SECRET", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DEMO_SESSION_SECRET"):
            create_app()
        monkeypatch.setenv("DEMO_SESSION_SECRET", "x" * 32)
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="DEMO_COOKIE_SECURE"):
            create_app()
        monkeypatch.setenv("DEMO_COOKIE_SECURE", "true")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="DEMO_MODE=false"):
            create_app()  # the clear-text demo OTP must not exist in prod
        monkeypatch.setenv("DEMO_MODE", "false")
        monkeypatch.setenv("COOLING_OFF_SECONDS", "30")
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="COOLING_OFF_SECONDS"):
            create_app()  # SR-9: at least 10 minutes in prod
        monkeypatch.setenv("COOLING_OFF_SECONDS", "600")
        get_settings.cache_clear()
        create_app()
    finally:
        get_settings.cache_clear()
