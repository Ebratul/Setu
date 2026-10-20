"""Email-code step-up: the code, the token, the limits, and the endpoints it gates."""

import re
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.auth import neon
from app.config import get_settings
from app.db.enums import MemberRole
from app.db.models import AuditLog, StepupChallenge, User
from app.db.session import batch_session
from app.main import create_app
from app.services import mail, stepup
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.auth.support import BASE_URL, FakeNeon
from tests.onboarding.support import (
    approved,
    bearer,
    onboard,
    uniq,
)

pytestmark = pytest.mark.db
CODE_RE = re.compile(r"Your Setu code is (\d{6})")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, seeded_db: str) -> Iterator[FakeNeon]:  # noqa: F811
    f = FakeNeon()
    monkeypatch.setenv("AUTH_MODE", "neon")
    monkeypatch.setenv("NEON_AUTH_BASE_URL", BASE_URL)
    monkeypatch.delenv("STEPUP_REQUIRED", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(neon, "_cache", f.cache())
    yield f
    get_settings.cache_clear()


@pytest.fixture
def client(fake: FakeNeon) -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def box() -> Iterator[mail.OutboxSender]:
    b = mail.OutboxSender()
    mail.set_sender(b)
    yield b
    mail.set_sender(None)


def code_of(m: mail.Mail) -> str:
    found = CODE_RE.search(m.text)
    assert found
    return found.group(1)


def wrong_for(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def audit(action: str, decision: str, actor: uuid.UUID) -> int:
    with batch_session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == action,
                    AuditLog.decision == decision,
                    AuditLog.actor_id == str(actor),
                )
            )
            or 0
        )


def an_admin(fake: FakeNeon) -> tuple[uuid.UUID, dict[str, str], str]:
    """(id, headers, email)"""
    from tests.onboarding.support import make_admin

    uid, email, sub = make_admin()
    return uid, bearer(fake.token(sub=sub, email=email)), email


def with_token(
    client: TestClient, headers: dict[str, str], box: mail.OutboxSender
) -> dict[str, str]:
    assert client.post("/auth/stepup/start", headers=headers).status_code == 200
    res = client.post("/auth/stepup/verify", json={"code": code_of(box.sent[-1])}, headers=headers)
    assert res.status_code == 200, res.text
    return {**headers, "X-Stepup": res.json()["token"]}


# --- start / verify ----------------------------------------------------------------------------


def test_start_mails_a_code_to_the_users_verified_address_and_never_returns_it(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, h, email = an_admin(fake)
    res = client.post("/auth/stepup/start", headers=h)
    assert res.status_code == 200, res.text
    assert res.json() == {"sent": True, "expires_in_seconds": 300, "starts_left": 2}
    [m] = box.sent
    assert m.to == email
    code = code_of(m)
    assert code not in res.text and "<b>" + code + "</b>" in m.html
    assert "Never share" in m.text and "reject" in m.text.lower() and "আপনার" in m.text
    with batch_session() as s:
        row = s.scalars(select(StepupChallenge).order_by(StepupChallenge.created_at.desc())).first()
        assert row is not None and code not in row.code_hash  # HMAC at rest


def test_verify_returns_a_token_sets_mfa_and_the_code_is_single_use(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    uid, h, _ = an_admin(fake)
    client.post("/auth/stepup/start", headers=h)
    code = code_of(box.sent[0])
    res = client.post("/auth/stepup/verify", json={"code": code}, headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["expires_in_seconds"] == 600 and body["header"] == "X-Stepup"
    assert stepup.token_valid(body["token"], uid)
    with batch_session() as s:
        assert s.get(User, uid).mfa_enabled is True  # type: ignore[union-attr]
    assert audit("auth.stepup", "ok", uid) == 1
    again = client.post("/auth/stepup/verify", json={"code": code}, headers=h)
    assert again.status_code == 400 and again.json()["code"] == "STEPUP_NO_CODE"


def test_wrong_codes_cost_tries_then_lock_and_the_audit_row_is_deduplicated(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    uid, h, _ = an_admin(fake)
    client.post("/auth/stepup/start", headers=h)
    code = code_of(box.sent[0])
    bad = wrong_for(code)
    codes = [
        client.post("/auth/stepup/verify", json={"code": bad}, headers=h).json()["code"]
        for _ in range(3)
    ]
    assert codes == ["STEPUP_INVALID"] * 3
    locked = client.post("/auth/stepup/verify", json={"code": code}, headers=h)
    assert locked.status_code == 403 and locked.json()["code"] == "STEPUP_LOCKED"
    assert audit("auth.stepup", "failed", uid) == 1  # 4 failures, one chain entry
    client.post("/auth/stepup/start", headers=h)  # a new code works again
    ok = client.post("/auth/stepup/verify", json={"code": code_of(box.sent[-1])}, headers=h)
    assert ok.status_code == 200


def test_an_expired_code_is_refused(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    uid, h, _ = an_admin(fake)
    client.post("/auth/stepup/start", headers=h)
    with batch_session() as s:
        s.execute(
            update(StepupChallenge)
            .where(StepupChallenge.user_id == uid)
            .values(expires_at=StepupChallenge.created_at - timedelta(seconds=1))
        )
    res = client.post("/auth/stepup/verify", json={"code": code_of(box.sent[0])}, headers=h)
    assert res.status_code == 400 and res.json()["code"] == "STEPUP_NO_CODE"


def test_a_code_cannot_be_used_by_another_user(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, a, _ = an_admin(fake)
    _, b, _ = an_admin(fake)
    client.post("/auth/stepup/start", headers=a)
    res = client.post("/auth/stepup/verify", json={"code": code_of(box.sent[0])}, headers=b)
    assert res.status_code == 400 and res.json()["code"] == "STEPUP_NO_CODE"


def test_only_three_codes_per_fifteen_minutes(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, h, _ = an_admin(fake)
    statuses = [client.post("/auth/stepup/start", headers=h).status_code for _ in range(4)]
    assert statuses == [200, 200, 200, 429]
    res = client.post("/auth/stepup/start", headers=h)
    assert res.json()["code"] == "STEPUP_RATE_LIMIT" and len(box.sent) == 3


def test_a_mail_failure_is_a_503_that_leaves_no_challenge(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    uid, h, _ = an_admin(fake)
    box.fail = True
    res = client.post("/auth/stepup/start", headers=h)
    assert res.status_code == 503 and "could not send the code" in res.text
    with batch_session() as s:
        n = s.scalar(
            select(func.count()).select_from(StepupChallenge).where(StepupChallenge.user_id == uid)
        )
    assert n == 0


def test_bad_bodies_and_unauthenticated_calls(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, h, _ = an_admin(fake)
    for body in (
        {"code": "abc"},
        {"code": "12345"},
        {"code": "1234567"},
        {},
        {"code": "123456", "x": 1},
    ):
        assert client.post("/auth/stepup/verify", json=body, headers=h).status_code == 422
    assert client.post("/auth/stepup/start").status_code == 401
    assert client.post("/auth/stepup/verify", json={"code": "123456"}).status_code == 401


def test_stepup_endpoints_do_not_exist_in_demo_mode(
    monkeypatch: pytest.MonkeyPatch,
    seeded_db: str,  # noqa: F811
) -> None:
    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    c = TestClient(create_app())
    c.post("/auth/demo-login", json={"email": "rahima@demo.setu"})
    assert c.post("/auth/stepup/start").status_code == 404
    assert c.post("/auth/stepup/verify", json={"code": "123456"}).status_code == 404
    assert get_settings().stepup_enabled is False
    get_settings.cache_clear()


# --- the token -----------------------------------------------------------------------------------


def test_token_is_bound_to_the_user_expires_and_detects_tampering() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    token, ttl = stepup.make_token(a)
    assert ttl == 600
    assert stepup.token_valid(token, a) and not stepup.token_valid(token, b)
    assert not stepup.token_valid(token, a, now=int(time.time()) + 601)
    assert stepup.token_valid(token, a, now=int(time.time()) + 599)
    uid, expires, sig = token.split(".")
    assert not stepup.token_valid(f"{uid}.{int(expires) + 3600}.{sig}", a)
    assert not stepup.token_valid(f"{uid}.{expires}.{'A' * len(sig)}", a)
    assert not stepup.token_valid(None, a) and not stepup.token_valid("", a)
    assert not stepup.token_valid("a.b", a) and not stepup.token_valid("x" * 500, a)
    old, _ = stepup.make_token(a, now=int(time.time()) - 601)
    assert not stepup.token_valid(old, a)


def test_token_secret_is_the_otp_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    a = uuid.uuid4()
    monkeypatch.setenv("OTP_SECRET_SEED", "s1" * 20)
    get_settings.cache_clear()
    token, _ = stepup.make_token(a)
    monkeypatch.setenv("OTP_SECRET_SEED", "s2" * 20)
    get_settings.cache_clear()
    assert not stepup.token_valid(token, a)
    get_settings.cache_clear()


# --- gated endpoints ----------------------------------------------------------------------------


def pending_review(client: TestClient, fake: FakeNeon, admin: dict[str, str]) -> str:
    # ids are looked up through the admin list; STEPUP does not gate reads
    headers, _ = onboard(client, fake)
    mine = client.get("/onboarding/status", headers=headers).json()["party_name"]
    items = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    return next(i["id"] for i in items if i["party"]["legal_name"] == mine)


def test_admin_decisions_need_a_stepup_token_and_reads_do_not(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, admin, _ = an_admin(fake)
    _, other_admin, _ = an_admin(fake)
    rid = pending_review(client, fake, admin)
    assert client.get("/admin/onboarding", headers=admin).status_code == 200
    for verb, body in (("approve", None), ("reject", {"reason": "not a real business entity"})):
        res = client.post(f"/admin/onboarding/{rid}/{verb}", json=body, headers=admin)
        assert res.status_code == 403 and res.json()["code"] == "STEPUP_REQUIRED", verb
    junk = client.post(f"/admin/onboarding/{rid}/approve", headers={**admin, "X-Stepup": "junk"})
    assert junk.status_code == 403 and junk.json()["code"] == "STEPUP_REQUIRED"

    theirs = with_token(client, other_admin, box)  # a valid token, issued to someone else
    swapped = client.post(
        f"/admin/onboarding/{rid}/approve", headers={**admin, "X-Stepup": theirs["X-Stepup"]}
    )
    assert swapped.status_code == 403 and swapped.json()["code"] == "STEPUP_REQUIRED"

    expired, _ = stepup.make_token(
        uuid.UUID(client.get("/auth/me", headers=admin).json()["id"]), now=int(time.time()) - 700
    )
    late = client.post(f"/admin/onboarding/{rid}/approve", headers={**admin, "X-Stepup": expired})
    assert late.status_code == 403 and late.json()["code"] == "STEPUP_REQUIRED"

    ok = client.post(f"/admin/onboarding/{rid}/approve", headers=with_token(client, admin, box))
    assert ok.status_code == 200, ok.text


def test_reject_with_a_token_works(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, admin, _ = an_admin(fake)
    rid = pending_review(client, fake, admin)
    res = client.post(
        f"/admin/onboarding/{rid}/reject",
        json={"reason": "licence number does not exist"},
        headers=with_token(client, admin, box),
    )
    assert res.status_code == 200, res.text


def test_a_non_admin_gets_the_role_error_not_a_stepup_prompt(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, admin, _ = an_admin(fake)
    buyer, _ = onboard(client, fake)
    res = client.post(f"/admin/onboarding/{uuid.uuid4()}/approve", headers=buyer)
    assert res.status_code in (403,) and res.json().get("code") != "STEPUP_REQUIRED"
    pending = client.post(f"/admin/onboarding/{uuid.uuid4()}/approve", headers=admin)
    assert pending.json()["code"] == "STEPUP_REQUIRED"  # the admin does get the prompt


def test_member_invite_and_remove_need_stepup(
    client: TestClient, fake: FakeNeon, box: mail.OutboxSender
) -> None:
    _, admin, _ = an_admin(fake)
    with_admin = with_token(client, admin, box)
    owner, party = approved(client, fake, with_admin)  # approvals used a token
    email = f"inv-{uniq()}@example.com"
    payload = {
        "email": email,
        "display_name": "New Finance",
        "member_role": MemberRole.FINANCE.value,
    }
    res = client.post(f"/parties/{party}/members", json=payload, headers=owner)
    assert res.status_code == 403 and res.json()["code"] == "STEPUP_REQUIRED"
    owner_token = with_token(client, owner, box)
    ok = client.post(f"/parties/{party}/members", json=payload, headers=owner_token)
    assert ok.status_code == 201, ok.text
    uid = ok.json()["user_id"]
    assert client.get(f"/parties/{party}/members", headers=owner).status_code == 200
    gone = client.delete(f"/parties/{party}/members/{uid}", headers=owner)
    assert gone.status_code == 403 and gone.json()["code"] == "STEPUP_REQUIRED"
    assert client.delete(f"/parties/{party}/members/{uid}", headers=owner_token).status_code == 204


def test_stepup_required_false_opens_the_gate_outside_prod(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, fake: FakeNeon
) -> None:
    _, admin, _ = an_admin(fake)
    rid = pending_review(client, fake, admin)
    monkeypatch.setenv("STEPUP_REQUIRED", "false")
    get_settings.cache_clear()
    assert client.post(f"/admin/onboarding/{rid}/approve", headers=admin).status_code == 200
