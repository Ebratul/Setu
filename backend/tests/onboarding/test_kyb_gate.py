import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    approved,
    onboard,
    review_id_for,
    supplier_body,
)

pytestmark = pytest.mark.db

GATED = ("/deals", "/approvals", "/analysis/orders", "/analysis/suppliers", "/cashflow/forecast")
READABLE = ("/deals", "/approvals", "/notifications", "/auth/me")


def deal_for(supplier_id: str) -> dict[str, str]:
    return {
        "supplier_id": supplier_id,
        "title": "Cotton fabric",
        "quantity": "1000",
        "unit": "m",
        "unit_price": "2.50",
        "port_of_loading": "Ningbo",
        "port_of_discharge": "Chattogram",
    }


def test_pending_user_reads_but_cannot_start_money_actions(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, _ = onboard(client, fake)
    for path in READABLE:
        assert client.get(path, headers=headers).status_code == 200, path
    res = client.post(
        "/deals", json=deal_for("00000000-0000-0000-0000-000000000000"), headers=headers
    )
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_NOT_VERIFIED"


def test_rejected_user_stays_locked_out(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    headers, _ = onboard(client, fake)
    rid = review_id_for(client, admin, "user-")
    client.post(
        f"/admin/onboarding/{rid}/reject",
        json={"reason": "Documents are unreadable"},
        headers=admin,
    )
    for path in GATED:
        res = client.get(path, headers=headers)
        assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_REJECTED", path


def test_deal_needs_a_verified_supplier_in_neon_mode(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    buyer, _ = approved(client, fake, admin)
    _, _ = onboard(client, fake, **supplier_body())  # supplier still PENDING
    items = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    sup = next(i for i in items if i["party"]["kind"] == "SUPPLIER")
    res = client.post("/deals", json=deal_for(sup["party"]["id"]), headers=buyer)
    assert res.status_code == 400 and res.json()["code"] == "SUPPLIER_NOT_VERIFIED"
    client.post(f"/admin/onboarding/{sup['id']}/approve", headers=admin)
    res = client.post("/deals", json=deal_for(sup["party"]["id"]), headers=buyer)
    assert res.status_code == 201, res.text


def test_rejected_supplier_cannot_be_used(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    buyer, _ = approved(client, fake, admin)
    onboard(client, fake, **supplier_body())
    items = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    sup = next(i for i in items if i["party"]["kind"] == "SUPPLIER")
    client.post(
        f"/admin/onboarding/{sup['id']}/reject",
        json={"reason": "Licence is not valid"},
        headers=admin,
    )
    res = client.post("/deals", json=deal_for(sup["party"]["id"]), headers=buyer)
    assert res.status_code == 400 and res.json()["code"] == "SUPPLIER_NOT_VERIFIED"


def test_demo_mode_keeps_seeded_flows(seeded_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import create_app

    monkeypatch.setenv("AUTH_MODE", "demo")
    get_settings.cache_clear()
    c = TestClient(create_app())
    users = c.get("/auth/demo-users").json()["users"]
    buyer = next(u for u in users if u["email"] == "rahima@demo.setu")
    c.post("/auth/demo-login", json={"email": buyer["email"]})
    suppliers = c.get("/suppliers").json()
    assert suppliers  # seeded suppliers (incl. non-VERIFIED ones) stay usable in demo mode
