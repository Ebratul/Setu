from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import session
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    session.get_settings.cache_clear()
    yield TestClient(create_app())
    session.get_settings.cache_clear()


def test_health_reports_db_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "ping", lambda: True)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "setu-agent", "db": "ok", "version": "0.1.0"}


def test_health_survives_db_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session, "ping", lambda: False)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["db"] == "unavailable"


def test_ping_never_raises_on_unreachable_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://setu:setu@127.0.0.1:1/setu")
    session.get_settings.cache_clear()
    session.get_engine.cache_clear()
    try:
        assert session.ping() is False
    finally:
        session.get_settings.cache_clear()
        session.get_engine.cache_clear()


def test_cors_allows_only_configured_origin(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    blocked = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers
