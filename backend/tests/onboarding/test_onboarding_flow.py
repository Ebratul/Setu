import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.demo import COOKIE_NAME, make_token
from app.config import get_settings
from app.db.enums import AccountStatus, KybStatus, OnboardingStatus, Role, UserStatus
from app.db.models import BankAccount, OnboardingReview, Party, PartyMember, User
from app.db.session import batch_session
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    audit,
    bearer,
    body,
    make_admin,
    onboard,
    review_id_for,
    uniq,
)

pytestmark = pytest.mark.db


def test_happy_path_pending_then_approved(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    user, out = onboard(client, fake)
    assert out["status"] == "PENDING" and out["account_status"] == "PENDING"
    assert out["role"] == "BUYER"
    assert client.get("/auth/me", headers=user).json()["code"] == "ACCOUNT_PENDING"
    for path in ("/deals", "/approvals", "/analysis/orders"):
        res = client.get(path, headers=user)
        assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_PENDING", path
    st = client.get("/onboarding/status", headers=user).json()
    assert st["status"] == "PENDING" and st["party_name"] and st["submitted_at"]

    rid = review_id_for(client, admin, "user-")
    pending = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    item = next(i for i in pending if i["id"] == rid)
    assert item["bank_account"]["account_masked"].startswith("****")
    assert item["recommendation"] == "AUTO_CLEAR" and item["party"]["kyb_status"] == "PENDING"
    assert client.get(f"/admin/onboarding/{rid}", headers=admin).json()["id"] == rid

    res = client.post(f"/admin/onboarding/{rid}/approve", headers=admin)
    assert res.status_code == 200 and res.json()["status"] == "APPROVED"
    assert client.get("/auth/me", headers=user).status_code == 200
    assert client.get("/deals", headers=user).status_code == 200
    st = client.get("/onboarding/status", headers=user).json()
    assert st["status"] == "APPROVED" and st["decided_at"]
    with batch_session() as s:
        party = s.get(Party, item["party"]["id"])
        assert party is not None
        assert party.kyb_status == KybStatus.VERIFIED and party.onboarded_at is not None
        acct = s.scalars(select(BankAccount).where(BankAccount.party_id == party.id)).one()
        assert acct.status == AccountStatus.ACTIVE
        member = s.scalars(select(PartyMember).where(PartyMember.party_id == party.id)).one()
        assert member.member_role.value == "OWNER"


def test_reject_path(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    user, _ = onboard(client, fake)
    rid = review_id_for(client, admin, "user-")
    assert (
        client.post(
            f"/admin/onboarding/{rid}/reject", json={"reason": "short"}, headers=admin
        ).status_code
        == 422
    )
    assert client.post(f"/admin/onboarding/{rid}/reject", json={}, headers=admin).status_code == 422
    res = client.post(
        f"/admin/onboarding/{rid}/reject",
        json={"reason": "Licence cannot be verified"},
        headers=admin,
    )
    assert res.status_code == 200 and res.json()["status"] == "REJECTED"
    assert client.get("/auth/me", headers=user).json()["code"] == "ACCOUNT_SUSPENDED"
    st = client.get("/onboarding/status", headers=user).json()
    assert st["status"] == "REJECTED" and st["reason"] == "Licence cannot be verified"
    with batch_session() as s:
        party = s.get(Party, res.json()["party"]["id"])
        assert party is not None and party.kyb_status == KybStatus.FAILED


def test_decisions_are_not_repeatable(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    onboard(client, fake)
    rid = review_id_for(client, admin, "user-")
    assert client.post(f"/admin/onboarding/{rid}/approve", headers=admin).status_code == 200
    for path, kw in (("approve", {}), ("reject", {"json": {"reason": "second thoughts here"}})):
        res = client.post(f"/admin/onboarding/{rid}/{path}", headers=admin, **kw)
        assert res.status_code == 409 and res.json()["code"] == "ONBOARDING_DECIDED"


def test_audit_rows_exist_and_carry_no_pii(client: TestClient, fake: FakeNeon) -> None:
    admin_id, admin = admin_headers(fake)
    payload = body()
    u = uniq()
    headers = bearer(fake.token(sub=f"sub-{u}", email=f"aud-{u}@example.com"))
    res = client.post("/onboarding", json=payload, headers=headers)
    assert res.status_code == 201
    rid = review_id_for(client, admin, f"aud-{u}")
    client.post(f"/admin/onboarding/{rid}/approve", headers=admin)
    sub = [r for r in audit("onboarding.submitted") if r.payload.get("review_id") == rid]
    dec = [r for r in audit("onboarding.approved") if r.payload.get("review_id") == rid]
    assert len(sub) == 1 and len(dec) == 1
    assert dec[0].actor_id == str(admin_id) and sub[0].actor_id != str(admin_id)
    blob = str([r.payload for r in sub + dec])
    for secret in (
        payload["legal_name"],
        payload["bank_account"]["account_number"],
        payload["bank_account"]["holder_name"],
        payload["license_no"],
        payload["tax_id"],
        f"aud-{u}",
    ):
        assert secret not in blob


@pytest.mark.parametrize("role", ["ADMIN", "JUDGE", "admin", "BUYER ", ""])
def test_role_cannot_be_self_chosen(client: TestClient, fake: FakeNeon, role: str) -> None:
    u = uniq()
    headers = bearer(fake.token(sub=f"sub-{u}", email=f"r-{u}@example.com"))
    res = client.post("/onboarding", json=body(account_type=role), headers=headers)
    if role.strip() == "BUYER":  # surrounding spaces are not accepted either: strict literal
        assert res.status_code in (201, 422)
    else:
        assert res.status_code == 422
    for extra in ("role", "status", "party_id", "is_demo"):
        res = client.post("/onboarding", json=body(**{extra: "ADMIN"}), headers=headers)
        assert res.status_code == 422
    with batch_session() as s:
        assert s.scalars(select(User).where(User.auth_subject == f"sub-{u}")).first() is None or (
            s.scalars(select(User.role).where(User.auth_subject == f"sub-{u}")).one() == Role.BUYER
        )


def test_supplier_gets_supplier_role(client: TestClient, fake: FakeNeon) -> None:
    b = body(account_type="SUPPLIER", country="CN", city="Ningbo", tax_id="91330201MA2ABC1234")
    b["bank_account"].update(bank_country="CN", currency="CNY")
    _, out = onboard(client, fake, **{k: v for k, v in b.items()})
    assert out["role"] == "SUPPLIER"


@pytest.mark.parametrize(
    "patch",
    [
        {"country": "bd1"},
        {"country": "B"},
        {"tax_id": "12345"},
        {"tax_id": "12345678901234"},
        {"tax_id": "12345abc9"},
        {"license_no": ""},
        {"license_no": "ab"},
        {"legal_name": "x"},
        {"language": "fr"},
        {"display_name": ""},
        {"bank_account": {"account_number": "SIM-12345678"}},
        {"bank_account": {"account_number": "12345"}},
        {"bank_account": {"account_number": "A" * 35}},
        {"bank_account": {"account_number": "1234 5678 90"}},
        {"bank_account": {"currency": "EUR"}},
        {"bank_account": {"account_type": "SAVINGS"}},
        {"bank_account": {"bank_country": "Bangladesh"}},
        {"bank_account": {"extra": "x"}},
    ],
)
def test_validation_failures_are_422(client: TestClient, fake: FakeNeon, patch: dict) -> None:
    b = body()
    if "bank_account" in patch:
        b["bank_account"].update(patch.pop("bank_account"))
    b.update(patch)
    u = uniq()
    res = client.post(
        "/onboarding", json=b, headers=bearer(fake.token(sub=f"v-{u}", email=f"v-{u}@example.com"))
    )
    assert res.status_code == 422, res.text


def test_missing_bank_account_is_422(client: TestClient, fake: FakeNeon) -> None:
    b = body()
    del b["bank_account"]
    u = uniq()
    headers = bearer(fake.token(sub=f"m-{u}", email=f"m-{u}@example.com"))
    assert client.post("/onboarding", json=b, headers=headers).status_code == 422


def test_country_outside_allow_list_is_refused(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    u = uniq()
    headers = bearer(fake.token(sub=f"c-{u}", email=f"c-{u}@example.com"))
    res = client.post("/onboarding", json=body(country="US", tax_id="123456789"), headers=headers)
    assert res.status_code == 409 and res.json()["code"] == "COUNTRY_NOT_SUPPORTED"
    monkeypatch.setenv("ONBOARDING_COUNTRIES", "BD,CN,US")
    get_settings.cache_clear()
    res = client.post("/onboarding", json=body(country="US", tax_id="123456789"), headers=headers)
    assert res.status_code == 201


def test_non_bd_buyer_needs_no_digit_tin(client: TestClient, fake: FakeNeon) -> None:
    b = body(country="CN", tax_id="91330201MA2ABC1234")
    b["bank_account"].update(bank_country="CN", currency="CNY")
    _, out = onboard(client, fake, **b)
    assert out["status"] == "PENDING"


def test_unauthenticated_and_unverified(client: TestClient, fake: FakeNeon) -> None:
    assert client.post("/onboarding", json=body()).status_code == 401
    assert client.get("/onboarding/status").status_code == 401
    t = fake.token(sub="uv", email="uv@example.com", emailVerified=False)
    res = client.post("/onboarding", json=body(), headers=bearer(t))
    assert res.status_code == 403 and res.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_demo_cookie_cannot_onboard(client: TestClient, fake: FakeNeon) -> None:
    client.cookies.set(COOKIE_NAME, make_token(__import__("uuid").uuid4()))
    assert client.post("/onboarding", json=body()).status_code == 401


def test_status_of_unknown_identity_is_404(client: TestClient, fake: FakeNeon) -> None:
    t = fake.token(sub="nobody", email="nobody@example.com")
    res = client.get("/onboarding/status", headers=bearer(t))
    assert res.status_code == 404 and res.json()["code"] == "NOT_ONBOARDED"


def test_duplicate_sub_email_and_licence(client: TestClient, fake: FakeNeon) -> None:
    u = uniq()
    b = body()
    headers = bearer(fake.token(sub=f"d-{u}", email=f"d-{u}@example.com"))
    assert client.post("/onboarding", json=b, headers=headers).status_code == 201
    res = client.post("/onboarding", json=body(), headers=headers)  # same sub
    assert res.status_code == 409 and res.json()["code"] == "ONBOARDING_EXISTS"
    other_sub = bearer(fake.token(sub=f"d2-{u}", email=f"D-{u}@example.com"))  # same email
    res = client.post("/onboarding", json=body(), headers=other_sub)
    assert res.status_code == 409 and res.json()["code"] == "EMAIL_IN_USE"
    fresh = bearer(fake.token(sub=f"d3-{u}", email=f"d3-{u}@example.com"))
    dup = body(license_no=b["license_no"].lower())  # same licence, other case
    res = client.post("/onboarding", json=dup, headers=fresh)
    assert res.status_code == 409 and res.json()["code"] == "LICENSE_EXISTS"
    # the same licence number for the other kind of party is allowed
    sup = body(account_type="SUPPLIER", license_no=b["license_no"])
    assert client.post("/onboarding", json=sup, headers=fresh).status_code == 201


def test_demo_email_cannot_be_taken(client: TestClient, fake: FakeNeon) -> None:
    t = bearer(fake.token(sub="evil", email="rahima@demo.setu"))
    res = client.post("/onboarding", json=body(), headers=t)
    assert res.status_code == 409 and res.json()["code"] == "EMAIL_IN_USE"


def test_sanctions_hit_blocks_auto_approve(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ONBOARDING_AUTO_APPROVE", "true")
    get_settings.cache_clear()
    b = body(legal_name="Zhongtai Meridian Trading Co., Ltd.")
    b["bank_account"]["holder_name"] = "Zhongtai Meridian Trading Co., Ltd."
    headers, out = onboard(client, fake, **b)
    assert out["status"] == "PENDING"
    assert all(c["code"] != "SANCTIONS_SCREEN" for c in out["checks"])  # no tipping off
    assert "score" not in out
    _, admin = admin_headers(fake)
    items = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    item = next(i for i in items if i["party"]["legal_name"].startswith("Zhongtai"))
    assert item["recommendation"] == "BLOCK" and item["score"] == 0
    assert client.get("/auth/me", headers=headers).json()["code"] == "ACCOUNT_PENDING"
    assert any(
        r.payload.get("party_id") == item["party"]["id"] for r in audit("onboarding.blocked")
    )


def test_auto_approve_for_clean_submission(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ONBOARDING_AUTO_APPROVE", "true")
    get_settings.cache_clear()
    headers, out = onboard(client, fake)
    assert out["status"] == "APPROVED" and out["account_status"] == "ACTIVE"
    assert client.get("/auth/me", headers=headers).status_code == 200
    rows = [r for r in audit("onboarding.approved") if r.payload.get("auto") is True]
    assert (rows and rows[-1].actor_id is None) or rows[-1].actor.value == "system"


def test_needs_review_is_not_auto_approved(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ONBOARDING_AUTO_APPROVE", "true")
    get_settings.cache_clear()
    b = body()
    b["bank_account"]["holder_name"] = "Somebody Else Entirely"
    _, out = onboard(client, fake, **b)
    assert out["status"] == "PENDING"


def test_admin_cannot_decide_own_review(client: TestClient, fake: FakeNeon) -> None:
    u = uniq()
    email, sub = f"selfie-{u}@example.com", f"sub-selfie-{u}"
    headers = bearer(fake.token(sub=sub, email=email))
    assert client.post("/onboarding", json=body(), headers=headers).status_code == 201
    with batch_session() as s:  # make this applicant an active ADMIN (worst case)
        user = s.scalars(select(User).where(User.auth_subject == sub)).one()
        user.role, user.status = Role.ADMIN, UserStatus.ACTIVE
        rid = str(
            s.scalars(select(OnboardingReview.id).where(OnboardingReview.user_id == user.id)).one()
        )
    for path, kw in (("approve", {}), ("reject", {"json": {"reason": "a long enough reason"}})):
        res = client.post(f"/admin/onboarding/{rid}/{path}", headers=headers, **kw)
        assert res.status_code == 403 and res.json()["code"] == "SELF_DECISION"
    with batch_session() as s:
        assert s.get(OnboardingReview, rid).status == OnboardingStatus.PENDING  # type: ignore[union-attr]


def test_only_admins_reach_the_queue(client: TestClient, fake: FakeNeon) -> None:
    buyer, _ = onboard(client, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, "user-")
    client.post(f"/admin/onboarding/{rid}/approve", headers=admin)
    paths = [("get", "/admin/onboarding"), ("get", f"/admin/onboarding/{rid}")]
    posts = [f"/admin/onboarding/{rid}/approve", f"/admin/onboarding/{rid}/reject"]
    for method, path in paths:
        assert client.request(method, path, headers=buyer).status_code == 403
        assert client.request(method, path).status_code == 401
    for path in posts:
        assert (
            client.post(path, headers=buyer, json={"reason": "nope nope nope"}).status_code == 403
        )


def test_judge_cannot_reach_the_queue_even_in_demo(seeded_db: str) -> None:
    from fastapi.testclient import TestClient as TC

    from app.main import create_app

    get_settings.cache_clear()
    c = TC(create_app())
    with batch_session() as s:
        judge = s.scalars(select(User).where(User.role == Role.JUDGE)).first()
        assert judge is not None
        email = judge.email
    assert c.post("/auth/demo-login", json={"email": email}).status_code == 200
    assert c.get("/admin/onboarding").status_code == 403
    assert (
        c.post(
            "/admin/onboarding/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12 + "/approve"
        ).status_code
        == 403
    )
    assert c.post("/onboarding", json=body()).status_code == 404  # demo mode: no onboarding


def test_unknown_review_is_404(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    rid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/admin/onboarding/{rid}", headers=admin).status_code == 404
    assert client.post(f"/admin/onboarding/{rid}/approve", headers=admin).status_code == 404


def test_cli_creates_admin_and_refuses_in_demo(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.admin_cli import create_admin

    email = f"cli-{uniq()}@example.com"
    uid = create_admin(email, "Cli Admin")
    with batch_session() as s:
        row = s.get(User, uid)
        assert row is not None
        assert row.role == Role.ADMIN and row.status == UserStatus.ACTIVE and not row.is_demo
        assert row.party_id is None
    t = bearer(fake.token(sub=f"cli-{uniq()}", email=email))
    assert client.get("/auth/me", headers=t).json()["role"] == "ADMIN"
    with pytest.raises(SystemExit):
        create_admin(email, "Dup")
    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    with pytest.raises(SystemExit):
        create_admin(f"demo-{uniq()}@example.com", "No")
    assert create_admin(f"force-{uniq()}@example.com", "Yes", force=True)
    make_admin()
