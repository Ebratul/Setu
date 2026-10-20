import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.enums import MemberRole
from app.db.models import PartyMember, User
from app.db.session import batch_session
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    approved,
    audit,
    bearer,
    onboard,
    review_id_for,
    supplier_body,
    uniq,
)

pytestmark = pytest.mark.db


def invite(
    client: TestClient, headers: dict[str, str], party: str, role: str = "FINANCE", email: str = ""
):
    email = email or f"inv-{uniq()}@example.com"
    res = client.post(
        f"/parties/{party}/members",
        json={"email": email, "display_name": "Invited Person", "member_role": role},
        headers=headers,
    )
    return email, res


def sign_in(fake: FakeNeon, email: str) -> dict[str, str]:
    return bearer(fake.token(sub=f"sub-{uniq()}", email=email))


def test_owner_lists_and_invites_and_invitee_links_on_first_sign_in(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    listing = client.get(f"/parties/{party}/members", headers=owner).json()
    assert [m["member_role"] for m in listing["items"]] == ["OWNER"]
    email, res = invite(client, owner, party, "FINANCE")
    assert res.status_code == 201, res.text
    assert res.json()["member_role"] == "FINANCE" and res.json()["signed_in_once"] is False
    member = sign_in(fake, email)
    me = client.get("/auth/me", headers=member).json()
    assert me["party_id"] == party and me["role"] == "BUYER"
    assert client.get("/deals", headers=member).status_code == 200
    listing = client.get(f"/parties/{party}/members", headers=owner).json()["items"]
    assert {m["member_role"] for m in listing} == {"OWNER", "FINANCE"}
    assert next(m for m in listing if m["email"] == email)["signed_in_once"] is True
    assert client.get(f"/parties/{party}/members", headers=member).status_code == 403
    assert invite(client, member, party)[1].status_code == 403


def test_invited_account_needs_a_verified_email_to_link(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    email, _ = invite(client, owner, party)
    t = fake.token(sub=f"sub-{uniq()}", email=email, emailVerified=False)
    assert client.get("/auth/me", headers=bearer(t)).json()["code"] == "EMAIL_NOT_VERIFIED"


def test_invite_supplier_party_gets_supplier_role(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin, **supplier_body())
    email, res = invite(client, owner, party, "VIEWER")
    assert res.status_code == 201
    assert client.get("/auth/me", headers=sign_in(fake, email)).json()["role"] == "SUPPLIER"


def test_viewer_reads_but_cannot_write(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    v_email, _ = invite(client, owner, party, "VIEWER")
    f_email, _ = invite(client, owner, party, "FINANCE")
    viewer, finance = sign_in(fake, v_email), sign_in(fake, f_email)
    assert client.get("/deals", headers=viewer).status_code == 200
    supplier = str(uuid.uuid4())
    res = client.post("/kyb/verify/" + supplier, headers=viewer)
    assert res.status_code == 403 and res.json()["code"] == "VIEWER_READ_ONLY"
    assert client.post("/kyb/verify/" + supplier, headers=finance).status_code != 403
    deal = {
        "supplier_id": supplier,
        "title": "Goods",
        "quantity": "10",
        "unit": "pcs",
        "unit_price": "5",
        "port_of_loading": "Ningbo",
        "port_of_discharge": "Chattogram",
    }
    res = client.post("/deals", json=deal, headers=viewer)
    assert res.status_code == 403 and res.json()["code"] == "VIEWER_READ_ONLY"
    res = client.post("/deals", json=deal, headers=finance)
    assert res.status_code == 404  # passes the role gate, supplier unknown
    ref = str(uuid.uuid4())
    for path in (f"/deals/{ref}/milestones/propose", f"/deals/{ref}/escrow/fund"):
        res = client.post(path, json={}, headers=viewer)
        assert res.status_code == 403 and res.json()["code"] == "VIEWER_READ_ONLY"


def test_cross_party_members_are_off_limits(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    a, party_a = approved(client, fake, admin)
    b, party_b = approved(client, fake, admin)
    assert client.get(f"/parties/{party_b}/members", headers=a).status_code == 403
    assert invite(client, a, party_b)[1].status_code == 403
    victim = client.get(f"/parties/{party_b}/members", headers=b).json()["items"][0]["user_id"]
    res = client.delete(f"/parties/{party_b}/members/{victim}", headers=a)
    assert res.status_code == 403
    assert client.get(f"/parties/{party_a}/members", headers=b).status_code == 403
    # nothing was added to B
    assert len(client.get(f"/parties/{party_b}/members", headers=b).json()["items"]) == 1


def test_member_cannot_be_removed_through_another_party(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    a, party_a = approved(client, fake, admin)
    b, party_b = approved(client, fake, admin)
    uid = client.get(f"/parties/{party_a}/members", headers=a).json()["items"][0]["user_id"]
    assert client.delete(f"/parties/{party_b}/members/{uid}", headers=b).status_code == 404
    assert client.get("/auth/me", headers=a).status_code == 200


def test_last_owner_cannot_be_removed(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    me = client.get("/auth/me", headers=owner).json()["id"]
    res = client.delete(f"/parties/{party}/members/{me}", headers=owner)
    assert res.status_code == 409 and res.json()["code"] == "LAST_OWNER"
    assert client.delete(f"/parties/{party}/members/{me}", headers=admin).status_code == 409
    # with a second owner the first can leave, and then has no access at all
    email, _ = invite(client, owner, party, "OWNER")
    second = sign_in(fake, email)
    assert client.get("/auth/me", headers=second).status_code == 200
    assert client.delete(f"/parties/{party}/members/{me}", headers=second).status_code == 204
    res = client.get("/auth/me", headers=owner)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_SUSPENDED"
    last = client.get("/auth/me", headers=second).json()["id"]
    assert client.delete(f"/parties/{party}/members/{last}", headers=second).status_code == 409


def test_remove_member_audit_and_unknown(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    email, res = invite(client, owner, party, "VIEWER")
    uid = res.json()["user_id"]
    assert client.delete(f"/parties/{party}/members/{uid}", headers=owner).status_code == 204
    assert client.delete(f"/parties/{party}/members/{uid}", headers=owner).status_code == 404
    with batch_session() as s:
        assert s.scalars(select(PartyMember).where(PartyMember.user_id == uid)).first() is None
        row = s.get(User, uid)
        assert row is not None and row.party_id is None
    inv = [r for r in audit("member.invited") if r.payload.get("user_id") == uid]
    rem = [r for r in audit("member.removed") if r.payload.get("user_id") == uid]
    assert len(inv) == 1 and len(rem) == 1
    assert email not in str(inv[0].payload) + str(rem[0].payload)


def test_invite_validation_and_conflicts(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    email, res = invite(client, owner, party)
    assert res.status_code == 201
    assert invite(client, owner, party, email=email.upper())[1].status_code == 409
    assert invite(client, owner, party, email="rahima@demo.setu")[1].status_code == 409
    bad = client.post(
        f"/parties/{party}/members",
        json={"email": "x@y.zz", "display_name": "Zed Zed", "member_role": "ADMIN"},
        headers=owner,
    )
    assert bad.status_code == 422
    extra = client.post(
        f"/parties/{party}/members",
        json={
            "email": "x@y.zz",
            "display_name": "Zed Zed",
            "member_role": "VIEWER",
            "party_id": party,
        },
        headers=owner,
    )
    assert extra.status_code == 422


def test_admin_manages_any_party_but_not_before_verification(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    owner, party = approved(client, fake, admin)
    _email, res = invite(client, admin, party, "FINANCE")
    assert res.status_code == 201
    assert client.get(f"/parties/{party}/members", headers=admin).status_code == 200
    _, out = onboard(client, fake)  # still PENDING
    rid = review_id_for(client, admin, "user-")
    pending_party = client.get(f"/admin/onboarding/{rid}", headers=admin).json()["party"]["id"]
    res = invite(client, admin, pending_party)[1]
    assert res.status_code == 409 and res.json()["code"] == "PARTY_NOT_VERIFIED"
    del out, owner


def test_party_without_member_row_counts_as_owner_in_demo(
    seeded_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.main import create_app

    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    c = TestClient(create_app())
    users = c.get("/auth/demo-users").json()["users"]
    buyer = next(u for u in users if u["role"] == "BUYER")
    assert c.post("/auth/demo-login", json={"email": buyer["email"]}).status_code == 200
    items = c.get(f"/parties/{buyer['party_id']}/members").json()["items"]
    assert buyer["email"] in {m["email"] for m in items}
    assert {m["member_role"] for m in items} == {"OWNER"}
    other = next(u for u in users if u["role"] == "SUPPLIER")
    assert c.get(f"/parties/{other['party_id']}/members").status_code == 403
    assert MemberRole.OWNER.value == "OWNER"
