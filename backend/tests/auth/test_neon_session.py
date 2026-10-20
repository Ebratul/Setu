import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import neon
from app.auth.demo import COOKIE_NAME, make_token
from app.config import get_settings
from app.db.enums import Language, Role, UserStatus
from app.db.models import AuditLog, User
from app.db.session import batch_session
from app.main import create_app
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.auth.support import BASE_URL, FakeNeon

pytestmark = pytest.mark.db


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, seeded_db: str) -> Iterator[FakeNeon]:  # noqa: F811
    f = FakeNeon()
    monkeypatch.setenv("AUTH_MODE", "neon")
    monkeypatch.setenv("NEON_AUTH_BASE_URL", BASE_URL)
    monkeypatch.setenv("DEMO_MODE", "false")  # demo-next-to-neon is covered in tests/onboarding
    get_settings.cache_clear()
    monkeypatch.setattr(neon, "_cache", f.cache())
    yield f
    get_settings.cache_clear()


@pytest.fixture
def client(fake: FakeNeon) -> TestClient:
    return TestClient(create_app())


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def add_user(email: str, status: UserStatus = UserStatus.ACTIVE, **kw: object) -> uuid.UUID:
    uid = uuid.uuid4()
    with batch_session() as s:
        s.add(
            User(
                id=uid,
                email=email,
                display_name="Real User",
                role=Role.BUYER,
                language=Language.EN,
                is_demo=False,
                status=status,
                **kw,
            )
        )
    return uid


def user_row(uid: uuid.UUID) -> User:
    with batch_session() as s:
        row = s.get(User, uid)
        assert row is not None
        s.expunge(row)
        return row


def audit_rows(action: str, actor_id: str | None = None) -> list[AuditLog]:
    with batch_session() as s:
        q = select(AuditLog).where(AuditLog.action == action)
        if actor_id:
            q = q.where(AuditLog.actor_id == actor_id)
        rows = list(s.scalars(q))
        s.expunge_all()
        return rows


def test_config_reports_neon_mode_and_demo_login_is_gone(client: TestClient) -> None:
    assert client.get("/auth/config").json() == {
        "mode": "neon",
        "demo_enabled": False,
        "google_enabled": True,
    }
    assert client.get("/auth/demo-users").status_code == 404
    assert client.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 404


def test_no_token_and_bad_token_are_401_with_codes(client: TestClient, fake: FakeNeon) -> None:
    res = client.get("/auth/me")
    assert res.status_code == 401 and res.json()["code"] == "UNAUTHENTICATED"
    res = client.get("/auth/me", headers=bearer("not.a.jwt"))
    assert res.status_code == 401 and res.json()["code"] == "TOKEN_INVALID"
    expired = fake.token(exp=1)
    assert client.get("/auth/me", headers=bearer(expired)).status_code == 401


def test_demo_cookie_does_not_authenticate_in_neon_mode(client: TestClient) -> None:
    with batch_session() as s:
        uid = s.scalars(select(User.id).where(User.email == "rahima@demo.setu")).one()
    client.cookies.set(COOKIE_NAME, make_token(uid))
    assert client.get("/auth/me").status_code == 401
    assert client.get("/analysis/orders").status_code == 401


def test_verified_identity_without_account_is_not_onboarded(
    client: TestClient, fake: FakeNeon
) -> None:
    token = fake.token(sub="stranger", email="stranger@example.com")
    res = client.post("/auth/session", headers=bearer(token))
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_NOT_ONBOARDED"
    assert client.get("/auth/me", headers=bearer(token)).status_code == 403
    assert audit_rows("auth.login", "anonymous") == []  # no local actor, nothing to attribute


def test_unverified_email_is_refused(client: TestClient, fake: FakeNeon) -> None:
    add_user("unverified@example.com")
    token = fake.token(sub="unv", email="unverified@example.com", emailVerified=False)
    res = client.post("/auth/session", headers=bearer(token))
    assert res.status_code == 403 and res.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_first_sign_in_links_pre_created_account_and_audits(
    client: TestClient, fake: FakeNeon
) -> None:
    uid = add_user("invited@example.com")
    token = fake.token(sub="neon-invited", email="Invited@Example.com")
    res = client.post("/auth/session", headers=bearer(token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["email"] == "invited@example.com" and body["role"] == "BUYER"
    row = user_row(uid)
    assert row.auth_subject == "neon-invited" and row.last_login_at is not None
    ok = audit_rows("auth.login", str(uid))
    assert len(ok) == 1 and ok[0].decision == "ok"
    link = audit_rows("auth.link", str(uid))
    assert len(link) == 1 and "subject_sha256" in link[0].payload
    assert "neon-invited" not in str(link[0].payload)
    assert client.get("/auth/me", headers=bearer(token)).json()["id"] == str(uid)


def test_account_is_pinned_to_the_first_neon_subject(client: TestClient, fake: FakeNeon) -> None:
    add_user("pinned@example.com")
    first = fake.token(sub="neon-real", email="pinned@example.com")
    assert client.post("/auth/session", headers=bearer(first)).status_code == 200
    second = fake.token(sub="neon-attacker", email="pinned@example.com")
    res = client.get("/auth/me", headers=bearer(second))
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_NOT_ONBOARDED"


def test_demo_accounts_can_never_be_claimed_by_email(client: TestClient, fake: FakeNeon) -> None:
    token = fake.token(sub="claimer", email="rahima@demo.setu")
    res = client.get("/auth/me", headers=bearer(token))
    assert res.status_code == 403
    with batch_session() as s:
        subject = s.scalars(select(User.auth_subject).where(User.email == "rahima@demo.setu")).one()
    assert subject is None


@pytest.mark.parametrize(
    ("status", "code"),
    [(UserStatus.REJECTED, "ACCOUNT_REJECTED"), (UserStatus.SUSPENDED, "ACCOUNT_SUSPENDED")],
)
def test_rejected_and_suspended_accounts_are_403(
    client: TestClient, fake: FakeNeon, status: UserStatus, code: str
) -> None:
    uid = add_user(f"{status.value.lower()}@example.com", status, auth_subject=f"sub-{status}")
    token = fake.token(sub=f"sub-{status}", email=f"{status.value.lower()}@example.com")
    for path in ("/auth/me", "/analysis/orders"):
        res = client.get(path, headers=bearer(token))
        assert res.status_code == 403 and res.json()["code"] == code
    res = client.post("/auth/session", headers=bearer(token))
    assert res.status_code == 403
    assert user_row(uid).last_login_at is None
    assert any(r.decision == "denied" for r in audit_rows("auth.login", str(uid)))


def test_suspension_takes_effect_on_the_next_request(client: TestClient, fake: FakeNeon) -> None:
    uid = add_user("later@example.com", auth_subject="sub-later")
    token = fake.token(sub="sub-later", email="later@example.com")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 200
    with batch_session() as s:
        row = s.get(User, uid)
        assert row is not None
        row.status = UserStatus.SUSPENDED
    assert client.get("/auth/me", headers=bearer(token)).status_code == 403


def test_actor_in_audit_is_the_local_user_id(client: TestClient, fake: FakeNeon) -> None:
    uid = add_user("actor@example.com", auth_subject="sub-actor")
    token = fake.token(sub="sub-actor", email="actor@example.com")
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
    rows = audit_rows("auth.logout", str(uid))
    assert len(rows) == 1 and rows[0].actor_id == str(uid)


def test_logout_without_a_valid_token_is_still_204_and_writes_nothing(
    client: TestClient,
) -> None:
    before = len(audit_rows("auth.logout"))
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout", headers=bearer("junk")).status_code == 204
    assert len(audit_rows("auth.logout")) == before


def test_garbage_token_on_session_writes_no_audit_row(client: TestClient) -> None:
    before = len(audit_rows("auth.login"))
    assert client.post("/auth/session", headers=bearer("junk")).status_code == 401
    assert len(audit_rows("auth.login")) == before


def test_jwks_outage_is_503_not_open(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake.fail = True
    monkeypatch.setattr(neon, "_cache", fake.cache())
    res = client.get("/auth/me", headers=bearer(fake.token()))
    assert res.status_code == 503


def test_demo_mode_keeps_working_and_rejects_bearer_tokens(
    monkeypatch: pytest.MonkeyPatch,
    seeded_db: str,  # noqa: F811
) -> None:
    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    c = TestClient(create_app())
    assert c.get("/auth/config").json() == {
        "mode": "demo",
        "demo_enabled": True,
        "google_enabled": False,
    }
    assert c.post("/auth/demo-login", json={"email": "rahima@demo.setu"}).status_code == 200
    assert c.get("/auth/me").status_code == 200
    assert c.post("/auth/session").status_code == 404
    other = TestClient(create_app())
    assert other.get("/auth/me", headers=bearer(FakeNeon().token())).status_code == 401


def test_bind_actor_reaches_sync_endpoints_that_do_not_pass_actor_id(
    fake: FakeNeon,
) -> None:
    from typing import Annotated

    from fastapi import Depends
    from sqlalchemy.orm import Session

    from app.audit.writer import write_audit
    from app.auth.deps import CurrentUser, current_user
    from app.db.session import get_db

    uid = add_user("implicit@example.com", auth_subject="sub-implicit")
    app = create_app()

    def probe(
        db: Annotated[Session, Depends(get_db)],
        _user: Annotated[CurrentUser, Depends(current_user)],
    ) -> dict[str, int]:
        seq = write_audit(db, actor="user", action="auth.probe", tier=0, params={}, result="ok")
        db.commit()
        return {"seq": seq}

    app.add_api_route("/_probe", probe, methods=["GET"])
    token = fake.token(sub="sub-implicit", email="implicit@example.com")
    res = TestClient(app).get("/_probe", headers=bearer(token))
    assert res.status_code == 200, res.text
    assert [r.actor_id for r in audit_rows("auth.probe")] == [str(uid)]
    assert TestClient(app).get("/_probe").status_code == 401


def test_linking_through_any_route_is_audited_and_case_insensitive(
    client: TestClient, fake: FakeNeon
) -> None:
    uid = add_user("Mixed.Case@Example.com")
    token = fake.token(sub="sub-mixed", email="mixed.case@example.com")
    assert client.get("/auth/me", headers=bearer(token)).status_code == 200  # not /auth/session
    assert len(audit_rows("auth.link", str(uid))) == 1
    assert client.get("/auth/me", headers=bearer(token)).status_code == 200
    assert len(audit_rows("auth.link", str(uid))) == 1


def test_repeated_session_and_logout_calls_do_not_grow_the_chain(
    client: TestClient, fake: FakeNeon
) -> None:
    uid = add_user("flood@example.com", auth_subject="sub-flood")
    token = fake.token(sub="sub-flood", email="flood@example.com")
    for _ in range(5):
        assert client.post("/auth/session", headers=bearer(token)).status_code == 200
        assert client.post("/auth/logout", headers=bearer(token)).status_code == 204
    assert len(audit_rows("auth.login", str(uid))) == 1
    assert len(audit_rows("auth.logout", str(uid))) == 1


def test_rejected_denials_are_deduplicated(client: TestClient, fake: FakeNeon) -> None:
    uid = add_user("pend2@example.com", UserStatus.REJECTED, auth_subject="sub-pend2")
    token = fake.token(sub="sub-pend2", email="pend2@example.com")
    for _ in range(4):
        assert client.post("/auth/session", headers=bearer(token)).status_code == 403
    assert len(audit_rows("auth.login", str(uid))) == 1


def test_new_real_accounts_default_to_pending_profile_and_demo_accounts_to_active(
    fake: FakeNeon,
) -> None:
    uid = uuid.uuid4()
    with batch_session() as s:
        s.add(
            User(
                id=uid,
                email="dflt@example.com",
                display_name="D",
                role=Role.BUYER,
                language=Language.EN,
                is_demo=False,
            )
        )
        s.add(
            User(
                id=uuid.uuid4(),
                email="dflt-demo@example.com",
                display_name="D",
                role=Role.BUYER,
                language=Language.EN,
            )
        )
    assert user_row(uid).status == UserStatus.PENDING_PROFILE
    with batch_session() as s:
        demo = s.scalars(select(User).where(User.email == "dflt-demo@example.com")).one()
        assert demo.status == UserStatus.ACTIVE


def test_demo_surface_is_absent_in_neon_mode(client: TestClient) -> None:
    for method, path in (("post", "/demo/sandbox"), ("get", "/demo/preflight")):
        assert getattr(client, method)(path).status_code == 404


def test_demo_cookie_never_sets_the_audit_actor_in_neon_mode(
    client: TestClient, fake: FakeNeon
) -> None:
    with batch_session() as s:
        demo_id = s.scalars(select(User.id).where(User.email == "rahima@demo.setu")).one()
    client.cookies.set(COOKIE_NAME, make_token(demo_id))
    add_user("real2@example.com", UserStatus.REJECTED, auth_subject="sub-real2")
    token = fake.token(sub="sub-real2", email="real2@example.com")
    client.post("/auth/session", headers=bearer(token))
    assert audit_rows("auth.login", str(demo_id)) == []


def test_health_does_not_need_the_database_in_neon_mode(
    monkeypatch: pytest.MonkeyPatch, fake: FakeNeon
) -> None:
    from app.db import session as db_session

    monkeypatch.setattr(db_session, "get_engine", lambda: None)
    res = TestClient(create_app()).get("/health")
    assert res.status_code == 200
