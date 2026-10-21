"""DEMO_MODE gating next to Neon auth, /auth/config, /account, rate limits."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.demo import COOKIE_NAME, make_token
from app.config import get_settings
from app.db.models import AuditLog, User
from app.db.session import batch_session
from app.main import create_app
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    audit,
    bearer,
    identity,
    must,
    onboard,
    pdf,
    review_id_for,
)

pytestmark = pytest.mark.db


def demo_id(email: str = "rahima@demo.setu"):
    with batch_session() as s:
        return s.scalars(select(User.id).where(User.email == email)).one()


# --- demo cookie / config ----------------------------------------------------------------------


def test_config_reports_flags(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # DEMO_MODE=true alone gives no demo login next to Neon sign-in
    assert client.get("/auth/config").json() == {
        "mode": "neon",
        "demo_enabled": False,
        "google_enabled": True,
    }
    monkeypatch.setenv("DEMO_COOKIE_IN_NEON", "true")
    get_settings.cache_clear()
    assert TestClient(create_app()).get("/auth/config").json()["demo_enabled"] is True
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GOOGLE_SIGNIN_ENABLED", "false")
    get_settings.cache_clear()
    c = TestClient(create_app())
    assert c.get("/auth/config").json() == {
        "mode": "neon",
        "demo_enabled": False,
        "google_enabled": False,
    }


def test_demo_cookie_works_next_to_neon_only_in_demo_mode_and_bearer_wins(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_COOKIE_IN_NEON", "true")  # explicit staging opt-in
    get_settings.cache_clear()
    client = TestClient(create_app())
    uid = demo_id()
    assert client.get("/auth/demo-users").status_code == 200
    assert client.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 200
    me = must(client.get("/auth/me"))
    assert me["email"] == "rahima@demo.setu" and me["account_status"] == "ACTIVE"
    # a bearer token always wins over the cookie, even a bad one (no silent fallback)
    stranger = bearer(fake.token(sub="nobody", email="nobody@example.com"))
    res = client.get("/auth/me", headers=stranger)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_NOT_ONBOARDED"
    res = client.get("/auth/me", headers=bearer("junk"))
    assert res.status_code == 401 and res.json()["code"] == "TOKEN_INVALID"
    # a hand-made cookie for a non-demo user is never believed
    _, admin = admin_headers(fake)
    admin_id = must(client.get("/auth/me", headers=admin))["id"]
    c2 = TestClient(create_app())
    c2.cookies.set(COOKIE_NAME, make_token(__import__("uuid").UUID(admin_id)))
    assert c2.get("/auth/me").status_code == 401
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    off = TestClient(create_app())
    off.cookies.set(COOKIE_NAME, make_token(uid))
    assert off.get("/auth/me").status_code == 401
    assert off.get("/auth/demo-users").status_code == 404
    assert off.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 404
    assert off.post("/demo/sandbox").status_code == 404
    assert off.get("/auth/me", headers=admin).status_code == 200  # real sign-in unaffected


def test_demo_auth_mode_without_demo_mode_has_no_way_in(
    seeded_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    c = TestClient(create_app())
    assert c.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 404
    c.cookies.set(COOKIE_NAME, make_token(demo_id()))
    assert c.get("/auth/me").status_code == 401


# --- account -----------------------------------------------------------------------------------


def test_account_profile_patch_export_and_delete(client: TestClient, fake: FakeNeon) -> None:
    h, state = onboard(client, fake)
    acct = must(client.get("/account", headers=h))
    assert acct["email"] == state["email"] and acct["role"] == "BUYER"
    assert acct["account_status"] == "PENDING_VERIFICATION" and acct["auth_provider"] == "neon"
    assert acct["terms_version"] == get_settings().terms_version and acct["mfa_enabled"] is False
    assert acct["mobile_masked"].startswith("01") and "*" in acct["mobile_masked"]
    patched = must(
        client.patch("/account", json={"language": "bn", "full_name": "Nusrat J."}, headers=h)
    )
    assert patched["language"] == "bn" and patched["display_name"] == "Nusrat J."
    assert client.patch("/account", json={"role": "ADMIN"}, headers=h).status_code == 422
    assert client.patch("/account", json={"full_name": "x"}, headers=h).status_code == 422
    export = must(client.get("/account/export", headers=h))
    assert export["account"]["email"] == state["email"] and "onboarding" in export
    assert "onboarding.submitted" in export["activity"]["audit_actions"]
    assert audit("account.export")
    gone = must(client.post("/account/delete-request", headers=h))
    assert gone["status"] == "SUSPENDED"
    assert client.get("/account", headers=h).status_code == 403  # suspended now
    with batch_session() as s:
        row = s.scalars(select(User).where(User.email == state["email"])).one()
        assert row.deleted_at is not None and row.status.value == "SUSPENDED"
    assert audit("account.delete_requested")
    assert client.get("/onboarding/me", headers=h).status_code == 403


def test_session_revoked_is_recorded(client: TestClient, fake: FakeNeon) -> None:
    h, state = onboard(client, fake)
    assert (
        client.post("/auth/session/revoked", json={"scope": "others"}, headers=h).status_code == 204
    )
    assert (
        client.post("/auth/session/revoked", json={"scope": "nope"}, headers=h).status_code == 422
    )
    with batch_session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == "auth.session_revoked")))
    assert rows and rows[-1].payload == {"scope": "others"}
    del state


def test_login_and_logout_are_audited_for_pending_users_too(
    client: TestClient, fake: FakeNeon
) -> None:
    h, state = onboard(client, fake)
    assert client.post("/auth/session", headers=h).status_code == 200
    assert client.post("/auth/logout", headers=h).status_code == 204
    uid = str(must(client.get("/auth/me", headers=h))["id"])
    with batch_session() as s:
        actions = {r.action for r in s.scalars(select(AuditLog).where(AuditLog.actor_id == uid))}
    assert {"auth.login", "auth.logout"} <= actions
    del state


def test_denied_judge_code_attempt_is_audited_for_existing_accounts(
    client: TestClient, fake: FakeNeon
) -> None:
    h, state = onboard(client, fake)
    res = client.post("/onboarding/role", json={"role": "JUDGE", "invite_code": "guess"}, headers=h)
    assert res.status_code == 403
    assert any(r.payload.get("reason") == "invalid_invite_code" for r in audit("auth.login_denied"))
    del state


# --- rate limits -------------------------------------------------------------------------------


def test_invite_code_guessing_is_limited_per_ip(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "*")
    monkeypatch.setenv("RATE_LIMIT_ROLE_PER_10MIN", "4")
    get_settings.cache_clear()
    codes = []
    for i in range(6):  # a new identity every time: only the address is being counted
        h, _, _ = identity(fake)
        res = client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": f"guess-{i}"},
            headers={**h, "X-Forwarded-For": "203.0.113.9"},
        )
        codes.append(res.status_code)
    assert codes == [403, 403, 403, 403, 429, 429]
    h2, _, _ = identity(fake)
    other = client.post(
        "/onboarding/role",
        json={"role": "JUDGE", "invite_code": "guess"},
        headers={**h2, "X-Forwarded-For": "203.0.113.77"},
    )
    assert other.status_code == 403  # another address has its own budget


def test_uploads_and_submits_are_limited_per_user(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_ONBOARDING_UPLOAD_PER_HOUR", "3")
    monkeypatch.setenv("RATE_LIMIT_SUBMIT_PER_HOUR", "2")
    get_settings.cache_clear()
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    statuses = []
    for _ in range(5):
        res = client.post(
            "/onboarding/documents",
            data={"type": "OTHER"},
            files={"file": ("a.pdf", pdf(), "application/pdf")},
            headers=h,
        )
        statuses.append(res.status_code)
    assert statuses == [201, 201, 201, 429, 429]
    assert [client.post("/onboarding/submit", headers=h).status_code for _ in range(3)] == [
        422,
        422,
        429,
    ]


def test_reveal_is_limited(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_REVEAL_PER_HOUR", "2")
    get_settings.cache_clear()
    _, state = onboard(client, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, state["email"])
    body = {"field": "tin", "reason": "Matching against NBR record"}
    codes = [
        client.post(f"/admin/onboarding/{rid}/reveal", json=body, headers=admin).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]
