"""A JUDGE can read, and can create / reset / end ITS OWN sandbox; nothing global or foreign."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import DemoSandbox
from app.demo import sandbox
from tests.demo.conftest import new_client
from tests.demo.test_sandbox import count

pytestmark = pytest.mark.db

JUDGE = "judge@demo.setu"


def judge_in_sandbox(app) -> tuple[TestClient, dict]:  # type: ignore[no-untyped-def]
    c = new_client(app)
    sb = c.post("/demo/sandbox", json={})
    assert sb.status_code == 200, sb.text
    assert c.post("/auth/demo-login", json={"email": JUDGE}).status_code == 200
    return c, sb.json()


def test_judge_reads_and_resets_only_their_own_sandbox(app) -> None:  # type: ignore[no-untyped-def]
    a, a_info = judge_in_sandbox(app)
    b, b_info = judge_in_sandbox(app)
    assert a_info["id"] != b_info["id"]
    assert a.get("/auth/me").json()["role"] == "JUDGE"
    assert a.get("/deals").status_code == 200  # reads
    b_schema = sandbox.lookup(uuid.UUID(b_info["id"])).schema
    shared_deals = count(None, "deals")

    assert a.post("/demo/run/reset").status_code == 200
    assert sandbox.lookup(uuid.UUID(a_info["id"])) is not None  # still A's sandbox, rebuilt
    assert sandbox.lookup(uuid.UUID(b_info["id"])).schema == b_schema  # B untouched
    assert b.get("/demo/run").status_code == 200
    assert count(None, "deals") == shared_deals
    a.delete("/demo/sandbox")
    b.delete("/demo/sandbox")


def test_without_a_sandbox_a_judge_cannot_reset_or_end_anything(app) -> None:  # type: ignore[no-untyped-def]
    owner, info = judge_in_sandbox(app)
    stranger = new_client(app)  # a judge with no sandbox cookie: would otherwise hit shared data
    stranger.post("/auth/demo-login", json={"email": JUDGE})
    reset = stranger.post("/demo/run/reset")
    assert reset.status_code == 404 and reset.json()["code"] == "SANDBOX_REQUIRED"
    for path, body in (
        ("/demo/run/goto", {"step": 1}),
        ("/demo/sandbox/skip-cooling-off", None),
        ("/demo/sandbox/live-ai", {"enabled": False}),
    ):
        assert stranger.post(path, json=body).status_code == 404, path
    assert stranger.delete("/demo/sandbox").status_code == 204  # drops nothing of anyone's
    with sandbox.registry() as db:
        assert db.get(DemoSandbox, uuid.UUID(info["id"])).status == "ACTIVE"
    owner.delete("/demo/sandbox")


def test_a_forged_or_unknown_cookie_does_not_reach_another_sandbox(app) -> None:  # type: ignore[no-untyped-def]
    victim, info = judge_in_sandbox(app)
    token = victim.cookies.get("setu_sandbox")
    attacker = new_client(app)
    forged = token[:-2] + ("00" if not token.endswith("00") else "11")
    res = attacker.get("/demo/run", headers={"cookie": f"setu_sandbox={forged}"})
    assert res.status_code == 410
    unknown = sandbox.make_token(uuid.uuid4())  # validly signed, but no such sandbox
    res = attacker.post("/demo/run/reset", headers={"cookie": f"setu_sandbox={unknown}"})
    assert res.status_code == 410
    with sandbox.registry() as db:
        assert db.get(DemoSandbox, uuid.UUID(info["id"])).status == "ACTIVE"
    victim.delete("/demo/sandbox")


def test_a_judge_cannot_run_admin_destructive_endpoints(app) -> None:  # type: ignore[no-untyped-def]
    c, _ = judge_in_sandbox(app)
    assert c.post("/demo/cleanup").status_code == 403  # needs the cron secret
    assert c.post("/demo/cleanup", headers={"Authorization": "Bearer guess"}).status_code == 403
    assert c.post(f"/security/injection/events/{uuid.uuid4()}/resolve").status_code == 403
    assert c.post(f"/approvals/{uuid.uuid4()}/approve", json={}).status_code in (403, 404)
    c.delete("/demo/sandbox")


def test_the_cleanup_endpoint_is_off_without_a_cron_secret(app, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    monkeypatch.setenv("CRON_SECRET", "")
    get_settings.cache_clear()
    c = new_client(app)
    assert c.post("/demo/cleanup", headers={"Authorization": "Bearer "}).status_code == 403
