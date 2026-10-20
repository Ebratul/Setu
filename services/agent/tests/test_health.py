from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import health
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
    body = res.json()
    assert {k: body[k] for k in ("status", "service", "db", "version")} == {
        "status": "ok",
        "service": "setu-agent",
        "db": "ok",
        "version": "0.1.0",
    }
    for key in (
        "ready",
        "kb_indexed",
        "audit_key_loaded",
        "replay_fixtures_present",
        "demo_mode",
        "demo_replay",
    ):
        assert isinstance(body[key], bool)
    assert "git_sha" in body and "built_at" in body


def test_ready_needs_every_check(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, audit_key: None
) -> None:
    monkeypatch.setattr(session, "ping", lambda: True)
    monkeypatch.setattr(health, "_kb_indexed", lambda: True)
    monkeypatch.setattr(health, "_replay_fixtures_present", lambda: True)
    assert client.get("/health").json()["ready"] is True
    monkeypatch.setattr(health, "_kb_indexed", lambda: False)
    body = client.get("/health").json()
    assert body["ready"] is False and body["status"] == "ok" and body["kb_indexed"] is False
    monkeypatch.setattr(health, "_kb_indexed", lambda: True)
    monkeypatch.setattr(health, "_replay_fixtures_present", lambda: False)
    assert client.get("/health").json()["ready"] is False
    monkeypatch.setattr(health, "_replay_fixtures_present", lambda: True)
    monkeypatch.setattr(health, "_audit_key_loaded", lambda: False)
    assert client.get("/health").json()["ready"] is False


def test_health_exposes_build_identity_and_no_secrets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, audit_key: None
) -> None:
    from tests.conftest import TEST_AUDIT_KEY

    monkeypatch.setattr(session, "ping", lambda: False)
    monkeypatch.setenv("GIT_SHA", "0123456789abcdef")
    monkeypatch.setenv("BUILD_TIME", "2026-10-19T10:00:00Z")
    session.get_settings.cache_clear()
    health._git_sha.cache_clear()
    try:
        res = client.get("/health")
    finally:
        health._git_sha.cache_clear()
    body = res.json()
    assert body["git_sha"] == "0123456" and body["built_at"] == "2026-10-19T10:00:00Z"
    assert body["ready"] is False and body["db"] == "unavailable" and body["audit_key_loaded"]
    assert TEST_AUDIT_KEY not in res.text and "postgresql" not in res.text


def test_replay_fixtures_check_follows_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path))
    session.get_settings.cache_clear()
    assert health._replay_fixtures_present() is False
    (tmp_path / "manifest.json").write_text('{"fixtures": [{"key": "abc"}]}')
    assert health._replay_fixtures_present() is False  # listed but the file is missing
    (tmp_path / "llm").mkdir()
    (tmp_path / "llm" / "abc.json").write_text("{}")
    assert health._replay_fixtures_present() is True


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
