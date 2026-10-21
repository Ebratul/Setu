"""Security-review fixes: demo login next to Neon, legacy MFA flags, TOTP-only admin decisions,
pending admins, KYB gate, party freeze, SMS provider, invite limits, startup refusals."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.requests import Request

from app.api import ratelimit
from app.auth.demo import COOKIE_NAME, make_token
from app.config import get_settings
from app.db.enums import KybStatus, Language, Role, UserStatus
from app.db.models import Party, User
from app.db.session import batch_session
from app.main import create_app
from app.security import crypto, totp
from app.services import sms
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    bearer,
    buyer_business,
    consent,
    identity,
    must,
    onboard,
    review_id_for,
    supplier_business,
    totp_stepup,
)

pytestmark = pytest.mark.db


def demo_admin_cookie(client: TestClient) -> None:
    with batch_session() as s:
        uid = s.scalars(select(User.id).where(User.email == "admin@demo.setu")).one()
    client.cookies.set(COOKIE_NAME, make_token(uid))


# --- 1. demo login never opens a real deployment -------------------------------------------------


def test_demo_mode_alone_gives_no_demo_login_or_cookie_with_neon(
    client: TestClient, fake: FakeNeon
) -> None:
    assert client.post("/auth/demo-login", json={"email": "admin@demo.setu"}).status_code == 404
    assert client.get("/auth/demo-users").status_code == 404
    assert client.post("/demo/sandbox").status_code == 404
    _, state = onboard(client, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, state["email"])
    doc = state["documents"][0]["id"]
    demo_admin_cookie(client)  # a hand-made, correctly signed cookie of the seeded demo admin
    calls = [
        ("get", "/admin/onboarding", None),
        ("get", f"/admin/onboarding/{rid}", None),
        (
            "post",
            f"/admin/onboarding/{rid}/reveal",
            {"field": "mobile", "reason": "curiosity here"},
        ),
        ("post", f"/admin/onboarding/{rid}/approve", None),
        ("get", f"/onboarding/documents/{doc}/url", None),
        ("get", "/deals", None),
        ("post", f"/deals/{uuid.uuid4()}/refund", {"reason": "dispute raised"}),
    ]
    for method, path, body in calls:
        res = client.request(method, path, json=body)
        assert res.status_code == 401, (path, res.status_code)


def test_even_with_the_staging_flag_the_demo_admin_is_not_mfa_exempt_in_neon(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_COOKIE_IN_NEON", "true")
    get_settings.cache_clear()
    c = TestClient(create_app())
    _, state = onboard(c, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(c, admin, state["email"])
    doc = state["documents"][0]["id"]
    assert c.post("/auth/demo-login", json={"email": "admin@demo.setu"}).status_code == 200
    assert c.get("/auth/me").json()["role"] == "ADMIN"  # the demo session itself works
    for method, path, body in (
        ("get", "/admin/onboarding", None),
        (
            "post",
            f"/admin/onboarding/{rid}/reveal",
            {"field": "mobile", "reason": "curiosity here"},
        ),
        ("get", "/deals", None),
    ):
        res = c.request(method, path, json=body)
        assert res.status_code == 403 and res.json()["code"] == "MFA_REQUIRED", path
    assert c.get(f"/onboarding/documents/{doc}/url").status_code == 404


def test_prod_refuses_the_demo_cookie_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import check_prod_settings
    from tests.test_prod_guard import GOOD

    for k, v in {**GOOD, "DEMO_COOKIE_IN_NEON": "true"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="DEMO_COOKIE_IN_NEON"):
        check_prod_settings(get_settings())
    assert get_settings().demo_login_enabled is False


# --- 2. legacy mfa flag ------------------------------------------------------------------------


def legacy_admin(fake: FakeNeon) -> dict[str, str]:
    uid, email, sub = uuid.uuid4(), f"legacy-{uuid.uuid4().hex[:8]}@example.com", uuid.uuid4().hex
    with batch_session() as s:  # what the pre-P30 email step-up left behind: flag, no secret
        s.add(
            User(
                id=uid,
                email=email,
                display_name="Legacy",
                role=Role.ADMIN,
                language=Language.EN,
                is_demo=False,
                status=UserStatus.ACTIVE,
                auth_subject=sub,
                mfa_enabled=True,
            )
        )
    return bearer(fake.token(sub=sub, email=email))


def test_a_legacy_mfa_flag_without_a_secret_is_not_two_factor(
    client: TestClient, fake: FakeNeon
) -> None:
    h = legacy_admin(fake)
    assert must(client.get("/auth/me", headers=h))["mfa_enabled"] is False
    res = client.get("/admin/onboarding", headers=h)
    assert res.status_code == 403 and res.json()["code"] == "MFA_REQUIRED"
    assert must(client.get("/account", headers=h))["mfa_enabled"] is False
    setup = client.post("/auth/mfa/totp/setup", headers=h)  # no 409 MFA_ALREADY_ENABLED
    assert setup.status_code == 200, setup.text
    code = totp.code_at(setup.json()["secret"], totp.current_step())
    must(client.post("/auth/mfa/totp/enable", json={"code": code}, headers=h))
    assert client.get("/admin/onboarding", headers=h).status_code == 200


# --- 4. a pending admin has no admin powers ------------------------------------------------------


def test_pending_admin_cannot_read_other_parties_or_run_kyb(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL_ALLOWLIST", "future-admin@example.com")
    get_settings.cache_clear()
    _, sup = onboard(client, fake, "SUPPLIER")
    party = _party_of(sup["email"])
    h, _, _ = identity(fake, email="future-admin@example.com")
    assert (
        must(client.post("/onboarding/role", json={"role": "ADMIN"}, headers=h))["account_status"]
        == "PENDING_PROFILE"
    )
    for method, path, body in (
        ("get", "/deals", None),
        ("get", "/analysis/orders", None),
        ("get", "/notifications", None),
        ("get", f"/kyb/{party}", None),
        ("post", f"/kyb/verify/{party}", None),
        ("get", "/admin/onboarding", None),
        ("post", "/alerts/recompute", None),
    ):
        res = client.request(method, path, json=body, headers=h)
        assert res.status_code == 403 and res.json()["code"] == "MFA_REQUIRED", (path, res.text)
    assert client.get("/auth/me", headers=h).status_code == 200  # the setup routes stay reachable
    assert client.get("/onboarding/me", headers=h).status_code == 200


def _party_of(email: str) -> uuid.UUID:
    with batch_session() as s:
        pid = s.scalars(select(User.party_id).where(User.email == email)).one()
        assert pid is not None
        return pid


# --- 5. /kyb/verify ------------------------------------------------------------------------------


def test_kyb_verify_refuses_unreviewed_rejected_and_suspended_suppliers(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    _, pending = onboard(client, fake, "SUPPLIER")
    party = _party_of(pending["email"])
    res = client.post(f"/kyb/verify/{party}", headers=admin)
    assert res.status_code == 409 and res.json()["code"] == "SUPPLIER_NOT_APPROVED"
    rid = review_id_for(client, admin, pending["email"])
    must(client.post(f"/admin/onboarding/{rid}/approve", headers=admin))
    assert client.post(f"/kyb/verify/{party}", headers=admin).status_code == 200
    must(
        client.post(
            f"/admin/onboarding/{rid}/suspend", json={"reason": "Chargeback inquiry"}, headers=admin
        )
    )
    again = client.post(f"/kyb/verify/{party}", headers=admin)
    assert again.status_code == 409 and again.json()["code"] == "SUPPLIER_NOT_APPROVED"
    with batch_session() as s:
        assert s.get(Party, party).kyb_status == KybStatus.FAILED  # type: ignore[union-attr]


def test_kyb_verify_needs_a_verified_caller(client: TestClient, fake: FakeNeon) -> None:
    h, _ = onboard(client, fake)
    res = client.post(f"/kyb/verify/{uuid.uuid4()}", headers=h)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_NOT_VERIFIED"


# --- 6. suspension freezes the business ----------------------------------------------------------


def test_suspending_the_owner_freezes_the_other_members(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, state = onboard(client, fake)
    rid = review_id_for(client, admin, state["email"])
    must(client.post(f"/admin/onboarding/{rid}/approve", headers=admin))
    party = _party_of(state["email"])
    email = f"colleague-{uuid.uuid4().hex[:8]}@example.com"
    must(
        client.post(
            f"/parties/{party}/members",
            json={"email": email, "display_name": "Colleague", "member_role": "FINANCE"},
            headers=owner,
        ),
        201,
    )
    member = bearer(fake.token(sub=f"sub-{uuid.uuid4().hex}", email=email))
    assert must(client.get("/auth/me", headers=member))["account_status"] == "ACTIVE"
    body = {
        "supplier_id": str(uuid.uuid4()),
        "title": "x",
        "quantity": "1",
        "unit": "m",
        "unit_price": "1",
    }
    assert client.post("/deals", json=body, headers=member).status_code != 403
    must(
        client.post(
            f"/admin/onboarding/{rid}/suspend", json={"reason": "Chargeback inquiry"}, headers=admin
        )
    )
    for who in (owner, member):
        assert client.get("/auth/me", headers=who).status_code == 403
        res = client.post("/deals", json=body, headers=who)
        assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_SUSPENDED"
    with batch_session() as s:
        statuses = {
            u.email: u.status for u in s.scalars(select(User).where(User.party_id == party))
        }
    assert set(statuses.values()) == {UserStatus.SUSPENDED}


def test_a_failed_party_blocks_money_even_for_an_active_member(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    owner, state = onboard(client, fake)
    must(
        client.post(
            f"/admin/onboarding/{review_id_for(client, admin, state['email'])}/approve",
            headers=admin,
        )
    )
    with batch_session() as s:
        s.get(Party, _party_of(state["email"])).kyb_status = KybStatus.FAILED  # type: ignore[union-attr]
    body = {
        "supplier_id": str(uuid.uuid4()),
        "title": "x",
        "quantity": "1",
        "unit": "m",
        "unit_price": "1",
    }
    res = client.post("/deals", json=body, headers=owner)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_SUSPENDED"
    assert client.get("/deals", headers=owner).status_code == 200  # reads stay


def test_rejecting_a_business_suspends_its_other_members(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    owner, state = onboard(client, fake)
    rid = review_id_for(client, admin, state["email"])
    party = _party_of(state["email"])
    uid = uuid.uuid4()
    with batch_session() as s:  # a teammate attached to the business
        s.add(
            User(
                id=uid,
                email=f"mate-{uid.hex[:8]}@example.com",
                display_name="Mate",
                role=Role.BUYER,
                language=Language.EN,
                party_id=party,
                is_demo=False,
                status=UserStatus.PENDING_VERIFICATION,
            )
        )
    must(
        client.post(
            f"/admin/onboarding/{rid}/reject",
            json={"reason": "Licence is not valid"},
            headers=admin,
        )
    )
    with batch_session() as s:
        assert s.get(User, uid).status == UserStatus.SUSPENDED  # type: ignore[union-attr]
    del owner


# --- 7. SMS provider -----------------------------------------------------------------------------


def test_prod_refuses_the_console_sms_provider_and_needs_the_webhook_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import check_prod_settings
    from tests.test_prod_guard import GOOD

    for bad in (
        {"SMS_PROVIDER": "console"},
        {"SMS_WEBHOOK_URL": "http://sms.example/send"},
        {"SMS_WEBHOOK_URL": ""},
        {"SMS_WEBHOOK_TOKEN": ""},
    ):
        for k, v in {**GOOD, **bad}.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        with pytest.raises(RuntimeError, match="SMS_"):
            check_prod_settings(get_settings())
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    check_prod_settings(get_settings())


def test_webhook_sms_posts_json_with_a_bearer_token_and_never_logs_the_text(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, object] = {}

    def fake_post(url: str, **kw: object) -> httpx.Response:
        seen.update(url=url, **kw)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("SMS_PROVIDER", "webhook")
    monkeypatch.setenv("SMS_WEBHOOK_URL", "https://sms.example/send")
    monkeypatch.setenv("SMS_WEBHOOK_TOKEN", "gateway-token")
    get_settings.cache_clear()
    sms.get_provider().send(sms.Sms(to="+8801712345678", text="code 123456"))
    assert seen["url"] == "https://sms.example/send"
    assert seen["headers"] == {"Authorization": "Bearer gateway-token"}
    assert seen["json"]["to"] == "+8801712345678" and "123456" in seen["json"]["text"]  # type: ignore[index]

    def boom(url: str, **kw: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(sms.SmsError):
        sms.get_provider().send(sms.Sms(to="+8801712345678", text="code 654321"))
    out = capfd.readouterr()
    assert "654321" not in out.out + out.err and "gateway-token" not in out.out + out.err


# --- 8. demo accounts ----------------------------------------------------------------------------


def test_demo_users_cannot_edit_or_delete_their_shared_account(
    seeded_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    c = TestClient(create_app())
    assert c.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 200
    assert c.get("/account").status_code == 200
    assert c.patch("/account", json={"language": "bn"}).status_code == 404
    assert c.post("/account/delete-request").status_code == 404
    with batch_session() as s:
        row = s.scalars(select(User).where(User.email == "rahima@demo.setu")).one()
        assert row.deleted_at is None and row.status == UserStatus.ACTIVE


# --- 9. invite code limits -----------------------------------------------------------------------


def test_invite_guessing_is_limited_per_identity_across_addresses(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "*")
    monkeypatch.setenv("RATE_LIMIT_ROLE_PER_10MIN", "3")
    get_settings.cache_clear()
    h, _, _ = identity(fake)
    codes = []
    for i in range(5):  # a different address each time: only the identity can be counted
        res = client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": f"guess-{i}"},
            headers={**h, "X-Forwarded-For": f"198.51.100.{i + 1}"},
        )
        codes.append(res.status_code)
    assert codes == [403, 403, 403, 429, 429]
    fresh, _, _ = identity(fake)  # another identity keeps its own budget
    res = client.post("/onboarding/role", json={"role": "JUDGE", "invite_code": "x"}, headers=fresh)
    assert res.status_code == 403
    rows = ratelimit and __import__("tests.onboarding.support", fromlist=["audit"]).audit(
        "auth.login_denied"
    )
    assert sum(1 for r in rows if str(r.actor_id).startswith("sub:")) >= 3
    assert all("guess" not in str(r.payload) for r in rows)


def test_a_forwarded_hop_cannot_borrow_the_test_client_exemption() -> None:
    def req(peer: str, xff: str) -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "query_string": b"",
            "client": (peer, 5),
            "headers": [(b"x-forwarded-for", xff.encode())],
        }
        return Request(scope)

    get_settings.cache_clear()
    import os

    os.environ["TRUSTED_PROXIES"] = "10.0.0.0/8"
    get_settings.cache_clear()
    try:
        assert ratelimit.ip_of(req("10.1.1.1", "testclient")) == "spoofed:testclient"
        assert ratelimit.ip_of(req("10.1.1.1", "203.0.113.5")) == "203.0.113.5"
        assert ratelimit.ip_of(req("testclient", "203.0.113.5")) == "testclient"
    finally:
        del os.environ["TRUSTED_PROXIES"]
        get_settings.cache_clear()


def test_short_invite_codes_stop_startup(monkeypatch: pytest.MonkeyPatch, seeded_db: str) -> None:
    monkeypatch.setenv("JUDGE_INVITE_CODES", "ok-code-1234567890,short")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JUDGE_INVITE_CODES"):
        create_app()


# --- 10./11. keys ----------------------------------------------------------------------------------


def test_neon_mode_refuses_to_start_without_a_field_key_except_in_tests(
    monkeypatch: pytest.MonkeyPatch, fake: FakeNeon
) -> None:
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
        create_app()
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    assert create_app() is not None


def test_each_purpose_gets_its_own_derived_key() -> None:
    keys = {f: crypto._index_key(f) for f in ("phone", "dedupe", "recovery", "phone-otp", "bank")}
    assert len(set(keys.values())) == 5 and all(len(k) == 32 for k in keys.values())
    assert crypto.blind_index("phone", "x") != crypto.blind_index("bank", "x")


# --- 12. replay ------------------------------------------------------------------------------------


def test_concurrent_requests_cannot_replay_one_totp_code(
    client: TestClient, fake: FakeNeon
) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    secret = must(client.post("/auth/mfa/totp/setup", headers=h))["secret"]
    must(
        client.post(
            "/auth/mfa/totp/enable",
            json={"code": totp.code_at(secret, totp.current_step())},
            headers=h,
        )
    )
    code = totp.code_at(secret, totp.current_step() + 1)  # an unused step inside the window

    def race(path: str, code: str) -> list[tuple[int, dict]]:
        def hit(_: int) -> tuple[int, dict]:
            res = TestClient(create_app()).post(path, json={"code": code}, headers=h)
            return res.status_code, res.json()

        with ThreadPoolExecutor(4) as pool:
            return sorted(pool.map(hit, range(4)), key=lambda r: r[0])

    regen = race("/auth/mfa/totp/recovery-codes/regenerate", code)
    assert [r[0] for r in regen] == [200, 400, 400, 400]  # one TOTP code, one use
    recovery = regen[0][1]["recovery_codes"][0]
    off = race("/auth/mfa/totp/disable", recovery)
    assert [r[0] for r in off] == [200, 400, 400, 400]  # and one recovery code, one use


# --- 13. judge switch --------------------------------------------------------------------------------


def test_switching_to_judge_before_any_details_activates_the_account(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JUDGE_INVITE_CODES", "judge-code-1234567890")
    get_settings.cache_clear()
    h, _, _ = identity(fake)
    assert (
        must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))["account_status"]
        == "PENDING_PROFILE"
    )
    state = must(
        client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": "judge-code-1234567890"},
            headers=h,
        )
    )
    assert state["role"] == "JUDGE" and state["account_status"] == "ACTIVE"
    assert client.get("/deals", headers=h).status_code == 200


_ = (buyer_business, consent, supplier_business, totp_stepup)


# --- second-pass review ----------------------------------------------------------------------------


def test_supplier_account_change_works_with_only_the_demo_admin_around(
    client: TestClient, fake: FakeNeon
) -> None:
    from tests.onboarding.support import approved
    from tests.onboarding.test_kyb_gate import deal_for

    _, admin = admin_headers(fake)
    buyer, _ = approved(client, fake, admin)
    supplier, sparty = approved(client, fake, admin, role="SUPPLIER")
    deal = must(client.post("/deals", json=deal_for(sparty), headers=buyer), 201)
    with batch_session() as s:  # leave the seeded (non-privileged in neon) admin as the first one
        real = [
            u.id
            for u in s.scalars(select(User).where(User.role == Role.ADMIN, User.is_demo.is_(False)))
        ]
        for u in s.scalars(select(User).where(User.id.in_(real))):
            u.role = Role.BUYER
    try:
        body = {
            "deal_id": deal["id"],
            "bank_name": "Bank of Ningbo",
            "bank_country": "CN",
            "account_number": "6222029999888877",
            "holder_name": "Someone Co., Ltd",
            "account_type": "CORPORATE",
            "currency": "CNY",
        }
        res = client.post("/supplier/accounts/change-request", json=body, headers=supplier)
        assert res.status_code == 202, res.text
        assert res.json()["account_status"] == "PENDING_CHANGE"
    finally:
        with batch_session() as s:
            for u in s.scalars(select(User).where(User.id.in_(real))):
                u.role = Role.ADMIN


def test_suspension_is_terminal_and_leaves_the_pending_queue(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    owner, state = onboard(client, fake)
    rid = review_id_for(client, admin, state["email"])
    out = must(
        client.post(
            f"/admin/onboarding/{rid}/suspend", json={"reason": "Fraud inquiry open"}, headers=admin
        )
    )
    assert out["status"] == "SUSPENDED" and out["account_status"] == "SUSPENDED"
    queue = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    assert rid not in {i["id"] for i in queue}
    for verb, body in (
        ("approve", None),
        ("request-changes", {"items": [{"target": "tin", "note": "fix it please"}]}),
        ("suspend", {"reason": "Fraud inquiry open"}),
    ):
        res = client.post(f"/admin/onboarding/{rid}/{verb}", json=body, headers=admin)
        assert res.status_code == 409, (verb, res.text)
    with batch_session() as s:
        row = s.scalars(select(User).where(User.email == state["email"])).one()
        assert row.status == UserStatus.SUSPENDED
        assert s.get(Party, row.party_id).kyb_status == KybStatus.FAILED  # type: ignore[union-attr]
    assert client.post("/onboarding/submit", headers=owner).status_code == 403  # no resubmitting


def test_email_stepup_token_is_refused_but_a_recovery_code_token_works_end_to_end(
    client: TestClient, fake: FakeNeon, mail_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    import re

    monkeypatch.setenv("STEPUP_REQUIRED", "true")
    get_settings.cache_clear()
    _, state = onboard(client, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, state["email"])
    must(client.post("/auth/stepup/start", headers=admin))
    code = re.search(r"Your Setu code is (\d{6})", mail_box.sent[-1].text).group(1)  # type: ignore[union-attr]
    email_token = must(client.post("/auth/stepup/verify", json={"code": code}, headers=admin))[
        "token"
    ]
    res = client.post(
        f"/admin/onboarding/{rid}/approve", headers={**admin, "X-Stepup": email_token}
    )
    assert res.status_code == 403 and res.json()["code"] == "STEPUP_TOTP_REQUIRED"
    ok = client.post(f"/admin/onboarding/{rid}/approve", headers=totp_stepup(client, admin))
    assert ok.status_code == 200 and ok.json()["account_status"] == "ACTIVE"


def test_ten_judge_sign_ups_from_one_address_do_not_lock_the_next_one_out(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRUSTED_PROXIES", "*")
    monkeypatch.setenv("JUDGE_INVITE_CODES", "judge-venue-code-123456")
    get_settings.cache_clear()
    venue = {"X-Forwarded-For": "192.0.2.50"}
    for _ in range(11):
        h, _, _ = identity(fake)
        state = must(
            client.post(
                "/onboarding/role",
                json={"role": "JUDGE", "invite_code": "judge-venue-code-123456"},
                headers={**h, **venue},
            )
        )
        assert state["account_status"] == "ACTIVE"
    h, _, _ = identity(fake)  # wrong codes from the same address are what get counted
    for _ in range(10):
        client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": "nope"},
            headers={**h, **venue},
        )
    h2, _, _ = identity(fake)
    res = client.post(
        "/onboarding/role",
        json={"role": "JUDGE", "invite_code": "judge-venue-code-123456"},
        headers={**h2, **venue},
    )
    assert res.status_code == 429


def test_wrong_totp_attempts_are_counted_in_the_audit_log_not_just_in_memory(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RATE_LIMIT_MFA_PER_10MIN", "3")
    get_settings.cache_clear()
    _, admin = admin_headers(fake)
    codes = []
    for _ in range(3):
        codes.append(
            client.post("/auth/stepup/verify", json={"code": "000000"}, headers=admin).status_code
        )
    ratelimit.reset_limits()  # another instance knows nothing of this process
    res = client.post("/auth/stepup/verify", json={"code": "000000"}, headers=admin)
    assert res.status_code == 429 and res.json()["code"] == "RATE_LIMITED"
    from tests.onboarding.support import audit

    assert len([r for r in audit("auth.mfa_failed")]) >= 3


def test_webhook_sms_must_be_https_outside_tests(
    monkeypatch: pytest.MonkeyPatch, seeded_db: str
) -> None:
    monkeypatch.setenv("SMS_PROVIDER", "webhook")
    monkeypatch.setenv("SMS_WEBHOOK_URL", "http://sms.example/send")
    monkeypatch.setenv("SMS_WEBHOOK_TOKEN", "t")
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="https"):
        create_app()
    with pytest.raises(sms.SmsError):
        sms.get_provider()


def test_demo_code_is_never_echoed_when_demo_is_off(
    client: TestClient, fake: FakeNeon, sms_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    must(
        client.put(
            "/onboarding/contact",
            json={"full_name": "Ana Bee", "designation": "MD", "mobile": "01712345678"},
            headers=h,
        )
    )
    assert must(client.post("/onboarding/phone/send", headers=h))["demo_code"] is None
