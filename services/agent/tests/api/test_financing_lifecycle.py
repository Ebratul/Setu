"""Apply → simulated approval → cash flow + alerts. Mutates its own seeded database."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import CashflowItem, FinancingApplication
from app.db.session import batch_session
from tests.api.conftest import login

pytestmark = pytest.mark.db

MAIN = "SETU-2026-0001"
M2 = "2026-11-07"


def shortfall_on(client: TestClient, on: str) -> dict | None:
    rows = client.get("/alerts").json()["alerts"]
    return next((a for a in rows if a["type"] == "SHORTFALL" and a["due_on"] == on), None)


def test_ineligible_option_is_rejected(client: TestClient) -> None:
    login(client, "rahima@demo.setu")
    body = {"deal_id": MAIN, "option_id": "import-loan-meghna", "amount": "1560.00"}
    res = client.post("/financing/applications", json=body)
    assert res.status_code == 400 and "not eligible" in res.json()["detail"]


def test_apply_approve_resolves_shortfall(client: TestClient) -> None:
    login(client, "rahima@demo.setu")
    pick = client.post("/financing/match", json={"deal_id": MAIN}).json()["top_pick"]
    assert shortfall_on(client, M2)["status"] == "OPEN"
    body = {"deal_id": MAIN, "option_id": pick["code"], "amount": "1560.00"}
    app = client.post("/financing/applications", json=body).json()
    assert app["status"] == "SUBMITTED" and app["reference"].startswith("FA-2026-")
    assert app["simulated"] is True and app["start_on"] == M2
    again = client.post("/financing/applications", json=body).json()
    assert again["id"] == app["id"]  # idempotent while active

    with batch_session() as s:
        before = s.scalar(select(func.count()).select_from(CashflowItem))
    res = client.post(f"/financing/applications/{app['id']}/simulate-approval").json()
    assert res["application"]["status"] == "APPROVED"
    assert res["alerts"]["resolved"] >= 1
    with batch_session() as s:
        after = s.scalar(select(func.count()).select_from(CashflowItem))
        keys = s.scalars(
            select(CashflowItem.key).where(CashflowItem.key.like(f"fin:{app['reference']}:%"))
        ).all()
    assert after == before + 2 and sorted(keys) == [
        f"fin:{app['reference']}:in",
        f"fin:{app['reference']}:repay",
    ]
    assert shortfall_on(client, M2)["status"] == "RESOLVED"
    fc = client.get("/cashflow/forecast").json()
    assert next(d for d in fc["daily"] if d["on"] == M2)["closing"] == "0.00"

    again = client.post(f"/financing/applications/{app['id']}/simulate-approval").json()
    assert again["application"]["status"] == "APPROVED"
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(CashflowItem)) == after
    apps = client.get("/financing/applications").json()["applications"]
    assert [a["status"] for a in apps] == ["APPROVED"]


def test_other_buyer_cannot_touch_application(client: TestClient) -> None:
    with batch_session() as s:
        app_id = s.scalars(select(FinancingApplication.id)).first()
    login(client, "karim@demo.setu")
    assert client.post(f"/financing/applications/{app_id}/simulate-approval").status_code == 404
    assert (
        client.post(f"/financing/applications/{uuid.uuid4()}/simulate-approval").status_code == 404
    )
    login(client, "judge@demo.setu")
    assert client.post(f"/financing/applications/{app_id}/simulate-approval").status_code == 403


def test_guards_on_amounts_and_reposts(client: TestClient) -> None:
    login(client, "rahima@demo.setu")
    body = {"deal_id": MAIN, "option_id": "supplier-credit-huaxin", "amount": "1560.00"}
    assert client.post("/financing/applications", json=body).status_code == 200
    changed = client.post("/financing/applications", json={**body, "amount": "1700.00"})
    assert changed.status_code == 409
    zero = {"option_id": "escrow-order-loan-setu-partner", "amount": "0", "deal_id": MAIN}
    assert client.post("/financing/impact", json=zero).status_code == 400
    sched = client.get(
        "/financing/options/import-loan-meghna/schedule", params={"amount": "0", "deal_id": MAIN}
    )
    assert sched.status_code == 400


def test_approval_rechecks_at_execution(client: TestClient) -> None:
    from sqlalchemy import update

    from app.db.models import FinancingOption

    login(client, "rahima@demo.setu")
    body = {
        "deal_id": MAIN,
        "option_id": "escrow-order-loan-setu-partner",
        "amount": "5200.00",
        "mode": "order",
    }
    app = client.post("/financing/applications", json=body).json()
    assert app["status"] == "SUBMITTED"
    with batch_session() as s:
        s.execute(
            update(FinancingOption)
            .where(FinancingOption.code == "escrow-order-loan-setu-partner")
            .values(active=False)
        )
    try:
        res = client.post(f"/financing/applications/{app['id']}/simulate-approval")
        assert res.status_code == 409 and "rejected" in res.json()["detail"]
        again = client.post(f"/financing/applications/{app['id']}/simulate-approval")
        assert again.status_code == 409 and "REJECTED" in again.json()["detail"]
    finally:
        with batch_session() as s:
            s.execute(
                update(FinancingOption)
                .where(FinancingOption.code == "escrow-order-loan-setu-partner")
                .values(active=True)
            )
    with batch_session() as s:
        keys = s.scalars(
            select(CashflowItem.key).where(CashflowItem.key.like(f"fin:{app['reference']}:%"))
        ).all()
    assert keys == []
