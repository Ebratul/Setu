"""Judge sandboxes: isolation, lifecycle, routing, limits."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.db import tenancy
from app.db.models import AuditLog, Deal, DemoSandbox
from app.db.session import batch_session, get_batch_engine
from app.demo import sandbox
from seed.verify import run_checks
from tests.demo.conftest import SCHEMAS_SQL, new_client

pytestmark = pytest.mark.db


def schemas() -> set[str]:
    with get_batch_engine().connect() as c:
        return {r[0] for r in c.execute(SCHEMAS_SQL)}


def count(schema: str | None, table: str) -> int:
    with tenancy.use_schema(schema), batch_session() as db:
        return int(db.scalar(text(f"SELECT count(*) FROM {table}")) or 0)


def test_schema_names_are_validated() -> None:
    for bad in ("public", 'sbx_x"; drop schema public; --', "sbx_ZZZ", "sbx_0123456789abc", ""):
        with pytest.raises(ValueError), tenancy.use_schema(bad):
            pass
    with tenancy.use_schema("sbx_0123456789ab"):
        assert tenancy.current_schema() == "sbx_0123456789ab"
    assert tenancy.current_schema() is None


def test_lock_keys_differ_per_schema() -> None:
    base = tenancy.lock_key(5_400_001)
    with tenancy.use_schema("sbx_aaaaaaaaaaaa"):
        a = tenancy.lock_key(5_400_001)
    with tenancy.use_schema("sbx_bbbbbbbbbbbb"):
        b = tenancy.lock_key(5_400_001)
    assert len({base, a, b}) == 3


def test_a_sandbox_is_a_private_full_copy_of_the_demo() -> None:
    row = sandbox.create_sandbox()
    try:
        assert row.schema_name in schemas()
        with tenancy.use_schema(row.schema_name), batch_session() as db:
            assert db.scalar(select(Deal.reference).where(Deal.reference == "SETU-2026-0001"))
            assert db.scalar(text("show search_path")).startswith(row.schema_name)
            checks = run_checks(db, profile="demo")
        assert [c.name for c in checks if not c.ok] == []
        assert count(row.schema_name, "deals") == 8
        assert count(row.schema_name, "audit_log") >= 35
        # shared tables are not copied
        with get_batch_engine().connect() as c:
            copied = {
                r[0]
                for r in c.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema=:s"),
                    {"s": row.schema_name},
                )
            }
        assert not copied & {"kb_chunks", "llm_cache", "demo_sandboxes"}
        assert "deals" in copied and "audit_log" in copied
    finally:
        sandbox.delete_sandbox(row.id)
    assert row.schema_name not in schemas()


def test_writes_in_one_sandbox_are_invisible_to_another_and_to_public() -> None:
    a, b = sandbox.create_sandbox(), sandbox.create_sandbox()
    try:
        with tenancy.use_schema(a.schema_name), batch_session() as db:
            db.execute(text("DELETE FROM alerts"))
            db.execute(text("UPDATE parties SET cash_balance = 1 WHERE code = 'rahima-knitwear'"))
        assert count(a.schema_name, "alerts") == 0
        assert count(b.schema_name, "alerts") > 0
        with tenancy.use_schema(b.schema_name), batch_session() as db:
            cash = db.scalar(text("SELECT cash_balance FROM parties WHERE code='rahima-knitwear'"))
        assert cash == 6000
        assert count(None, "deals") == 0  # public (test db) was never seeded
    finally:
        sandbox.delete_sandbox(a.id)
        sandbox.delete_sandbox(b.id)


def test_the_audit_log_of_a_sandbox_stays_append_only() -> None:
    row = sandbox.create_sandbox()
    try:
        with (
            tenancy.use_schema(row.schema_name),
            batch_session() as db,
            pytest.raises(Exception, match="append-only"),
        ):
            db.execute(text("UPDATE audit_log SET action = 'X' WHERE seq = 1"))
    finally:
        sandbox.delete_sandbox(row.id)


def test_reset_rebuilds_only_that_sandbox_and_logs_it() -> None:
    a, b = sandbox.create_sandbox(), sandbox.create_sandbox()
    try:
        with tenancy.use_schema(a.schema_name), batch_session() as db:
            db.execute(text("DELETE FROM alerts"))
        with tenancy.use_schema(b.schema_name), batch_session() as db:
            db.execute(text("DELETE FROM alerts"))
        with tenancy.use_schema(a.schema_name), batch_session() as db:
            head = db.execute(
                select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
            ).one()
        fresh = sandbox.reset_sandbox(a.id)
        assert fresh.schema_name != a.schema_name  # built beside the old one, then swapped in
        assert a.schema_name not in schemas()
        assert sandbox.lookup(a.id).schema == fresh.schema_name
        assert count(fresh.schema_name, "alerts") > 0  # restored
        assert count(b.schema_name, "alerts") == 0  # untouched
        with tenancy.use_schema(fresh.schema_name), batch_session() as db:
            last = db.scalar(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1))
            checks = run_checks(db, profile="demo")
        assert last is not None and last.action == "DEMO_RESET"
        assert last.payload["previous_head_seq"] == head[0]
        assert last.payload["previous_head_hash"] == head[1]
        assert [c.name for c in checks if not c.ok] == []
        with sandbox.registry() as db:
            assert sandbox.get_row(db, a.id).resets == 1
    finally:
        sandbox.delete_sandbox(a.id)
        sandbox.delete_sandbox(b.id)


def test_a_missing_schema_is_gone_never_the_shared_tables() -> None:
    row = sandbox.create_sandbox()
    try:
        sandbox._drop_schema(row.schema_name)  # the row still says ACTIVE
        with (
            pytest.raises(tenancy.SchemaMissing),
            tenancy.use_schema(row.schema_name),
            batch_session() as db,
        ):
            db.execute(text("SELECT 1"))
    finally:
        sandbox.delete_sandbox(row.id)


def test_a_foreign_cookie_before_ours_does_not_switch_routing_off(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/demo/sandbox", json={})
    token = client.cookies.get("setu_sandbox")
    client.cookies.clear()
    ok = client.get("/demo/run", headers={"cookie": f'prefs={{"a": 1}}; setu_sandbox={token}'})
    assert ok.status_code == 200
    bad = client.get("/demo/run", headers={"cookie": 'prefs={"a": 1}; setu_sandbox=garbage'})
    assert bad.status_code == 410 and bad.json()["code"] == "SANDBOX_EXPIRED"
    assert client.get("/deals", headers={"cookie": "setu_sandbox="}).status_code == 410


def test_the_seeded_chat_thread_has_a_checkpoint_per_sandbox() -> None:
    from app.agent.persistence import checkpoint_key

    with tenancy.use_schema("sbx_aaaaaaaaaaaa"):
        a = checkpoint_key("T")
    with tenancy.use_schema("sbx_bbbbbbbbbbbb"):
        b = checkpoint_key("T")
    assert a == "sbx_aaaaaaaaaaaa:T" and b == "sbx_bbbbbbbbbbbb:T" and checkpoint_key("T") == "T"


def test_a_reset_does_not_give_the_live_ai_budget_back(client) -> None:  # type: ignore[no-untyped-def]
    sid = uuid.UUID(client.post("/demo/sandbox", json={}).json()["id"])
    sandbox.set_live_ai(sid, True)
    assert sandbox.spend_live_call(sid)
    client.post("/demo/run/reset")
    with sandbox.registry() as db:
        row = db.get(DemoSandbox, sid)
        assert row.llm_calls == 1 and row.live_ai is False


def test_cookie_tokens_are_signed() -> None:
    sid = uuid.uuid4()
    token = sandbox.make_token(sid)
    assert sandbox.parse_token(token) == sid
    assert sandbox.parse_token(token[:-2] + "00") is None
    assert sandbox.parse_token(f"{uuid.uuid4()}.{token.split('.')[1]}") is None
    assert sandbox.parse_token("garbage") is None


def test_an_expired_sandbox_is_gone_and_its_schema_is_dropped(client) -> None:  # type: ignore[no-untyped-def]
    r = client.post("/demo/sandbox", json={})
    assert r.status_code == 200
    sid = uuid.UUID(r.json()["id"])
    with sandbox.registry() as db:
        row = db.get(DemoSandbox, sid)
        schema = row.schema_name
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    sandbox.invalidate(sid)
    gone = client.get("/demo/run")
    assert gone.status_code == 410 and gone.json()["code"] == "SANDBOX_EXPIRED"
    # the shared data is never served in its place
    assert client.get("/deals").status_code == 410
    assert sandbox.cleanup_expired() >= 1
    assert schema not in schemas()
    # a stale cookie can still ask for a new sandbox
    again = client.post("/demo/sandbox", json={})
    assert again.status_code == 200 and again.json()["id"] != str(sid)


def test_sandbox_endpoints_need_a_sandbox(app) -> None:  # type: ignore[no-untyped-def]
    c = new_client(app)
    for method, path in (
        ("get", "/demo/run"),
        ("get", "/demo/sandbox"),
        ("post", "/demo/run/reset"),
    ):
        r = getattr(c, method)(path)
        assert r.status_code == 404 and r.json()["code"] == "SANDBOX_REQUIRED"
    assert c.get("/demo/steps").status_code == 200  # public


def test_capacity_limit(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    client.post("/demo/sandbox", json={})
    monkeypatch.setenv("SANDBOX_MAX_ACTIVE", "1")
    get_settings.cache_clear()
    other = new_client(client.app)
    r = other.post("/demo/sandbox", json={})
    assert r.status_code == 503 and r.json()["code"] == "SANDBOX_CAPACITY"


def test_requests_are_rate_limited_per_sandbox(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    client.post("/demo/sandbox", json={})
    client.post("/auth/demo-login", json={"email": "rahima@demo.setu"})
    monkeypatch.setenv("SANDBOX_CHAT_PER_MINUTE", "2")
    get_settings.cache_clear()
    codes = [
        client.post("/chat", json={"message": "hello", "language": "en"}).status_code
        for _ in range(4)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2:] == [429, 429]
    limited = client.post("/chat", json={"message": "hello", "language": "en"})
    assert limited.json()["code"] == "SANDBOX_RATE_LIMIT" and "retry-after" in limited.headers
    # another sandbox has its own budget
    other = new_client(client.app)
    other.post("/demo/sandbox", json={})
    other.post("/auth/demo-login", json={"email": "rahima@demo.setu"})
    assert other.post("/chat", json={"message": "hello", "language": "en"}).status_code == 200
    other.delete("/demo/sandbox")


def test_resume_returns_the_same_sandbox_and_fresh_replaces_it(client) -> None:  # type: ignore[no-untyped-def]
    first = client.post("/demo/sandbox", json={}).json()
    again = client.post("/demo/sandbox", json={}).json()
    assert first["id"] == again["id"]
    fresh = client.post("/demo/sandbox", json={"fresh": True}).json()
    assert fresh["id"] != first["id"]
    with sandbox.registry() as db:
        assert db.get(DemoSandbox, uuid.UUID(first["id"])).status == "DELETED"


def test_live_ai_needs_a_key_and_a_budget(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    monkeypatch.setenv("OPENROUTER_API_KEY", "")  # a developer's .env must not leak into tests
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    client.post("/demo/sandbox", json={})
    assert client.get("/demo/sandbox").json()["replay"] is True
    assert client.get("/demo/sandbox").json()["live_ai_available"] is False
    r = client.post("/demo/sandbox/live-ai", json={"enabled": True})
    assert r.status_code == 403 and r.json()["code"] == "LIVE_AI_UNAVAILABLE"
    assert client.post("/demo/sandbox/live-ai", json={"enabled": False}).status_code == 200


def test_live_budget_is_spent_then_falls_back_to_replay(client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    sb = client.post("/demo/sandbox", json={}).json()
    sid = uuid.UUID(sb["id"])
    monkeypatch.setenv("SANDBOX_LIVE_AI_BUDGET", "2")
    get_settings.cache_clear()
    sandbox.set_live_ai(sid, True)
    assert sandbox.spend_live_call(sid) is True
    assert sandbox.spend_live_call(sid) is True  # second call uses the last unit and switches off
    with sandbox.registry() as db:
        row = db.get(DemoSandbox, sid)
        assert row.live_ai is False and row.llm_calls == 2
    assert sandbox.spend_live_call(sid) is False


def test_skip_cooling_off_is_demo_only_and_audited(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/demo/sandbox", json={})
    client.post("/auth/demo-login", json={"email": "rahima@demo.setu"})
    assert client.post("/demo/sandbox/skip-cooling-off").json()["skipped"] == 0
    sim = client.post("/demo/simulate/supplier-account-change")
    assert sim.status_code == 200 and sim.json()["tier"] == 3
    assert client.post("/demo/sandbox/skip-cooling-off").json()["skipped"] == 1
    sid = uuid.UUID(client.get("/demo/sandbox").json()["id"])
    info = sandbox.lookup(sid)
    with tenancy.use_schema(info.schema), batch_session() as db:
        actions = db.scalars(select(AuditLog.action)).all()
    assert "DEMO_COOLING_OFF_SKIPPED" in actions


def test_one_caller_cannot_fill_every_sandbox(app, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    monkeypatch.setenv("SANDBOX_CREATES_PER_HOUR_PER_IP", "2")
    get_settings.cache_clear()
    c = new_client(app)
    headers = {"x-forwarded-for": f"203.0.113.{uuid.uuid4().int % 250}"}
    first = c.post("/demo/sandbox", json={"fresh": True}, headers=headers)
    second = c.post("/demo/sandbox", json={"fresh": True}, headers=headers)
    third = c.post("/demo/sandbox", json={"fresh": True}, headers=headers)
    assert (first.status_code, second.status_code) == (200, 200)
    assert third.status_code == 429 and third.json()["code"] == "SANDBOX_RATE_LIMIT"
    other = c.post(
        "/demo/sandbox", json={"fresh": True}, headers={"x-forwarded-for": "198.51.100.77"}
    )
    assert other.status_code == 200  # another address is unaffected
    c.delete("/demo/sandbox")


def test_chat_in_a_sandbox_stays_in_it_and_is_forgotten_with_it(client) -> None:  # type: ignore[no-untyped-def]
    """A chat turn (also streamed) writes only to the sandbox, and dropping it purges the
    LangGraph checkpoints kept in the shared schema."""
    client.post("/demo/sandbox", json={})
    client.post("/auth/demo-login", json={"email": "rahima@demo.setu"})
    sid = uuid.UUID(client.get("/demo/sandbox").json()["id"])
    schema = sandbox.lookup(sid).schema
    out = client.post("/chat", json={"message": "how does escrow work?", "language": "en"}).json()
    thread = out["thread_id"]
    with client.stream(
        "POST", "/chat/stream", json={"message": "and tiers?", "language": "en"}
    ) as resp:
        body = "".join(resp.iter_text())
    assert "event: final" in body
    assert count(schema, "chat_threads") == 3  # the seeded one and these two
    assert count(None, "chat_threads") == 0
    with get_batch_engine().connect() as c:
        kept = c.scalar(
            text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"),
            {"t": f"{schema}:{thread}"},
        )
    assert kept and kept > 0
    sandbox.delete_sandbox(sid)
    with get_batch_engine().connect() as c:
        left = c.scalar(
            text("SELECT count(*) FROM checkpoints WHERE thread_id LIKE :p"), {"p": f"{schema}:%"}
        )
    assert left == 0


def test_the_cleanup_endpoint_needs_the_cron_secret(app, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    c = new_client(app)
    assert c.post("/demo/cleanup").status_code == 403  # no secret configured: closed
    monkeypatch.setenv("CRON_SECRET", "s3cret-for-tests")
    get_settings.cache_clear()
    assert c.post("/demo/cleanup").status_code == 403
    bad = c.post("/demo/cleanup", headers={"authorization": "Bearer nope"})
    assert bad.status_code == 403
    ok = c.post("/demo/cleanup", headers={"authorization": "Bearer s3cret-for-tests"})
    assert ok.status_code == 200 and "dropped" in ok.json()
