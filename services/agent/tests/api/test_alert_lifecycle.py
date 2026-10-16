"""Alert engine lifecycle: auto-resolve, reopen, user resolve. Mutates its own seeded database."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.enums import CashflowKind, FlowDirection
from app.db.models import CashflowItem, Party
from app.db.session import batch_session
from tests.api.conftest import login

pytestmark = pytest.mark.db

GRANT_KEY = "test:rahima:grant"


def shortfalls(client: TestClient) -> list[dict]:
    return [a for a in client.get("/alerts").json()["alerts"] if a["type"] == "SHORTFALL"]


def add_grant(amount: str, direction: FlowDirection = FlowDirection.IN) -> None:
    with batch_session() as s:
        rahima = s.scalars(select(Party).where(Party.code == "rahima-knitwear")).one()
        s.add(
            CashflowItem(
                id=uuid.uuid4(),
                key=GRANT_KEY,
                party_id=rahima.id,
                on_date=date(2026, 11, 1),
                kind=CashflowKind.OTHER,
                direction=direction,
                amount=Decimal(amount),
                currency="USD",
                description="Test grant",
                is_projected=True,
            )
        )


def drop_grant() -> None:
    with batch_session() as s:
        s.execute(delete(CashflowItem).where(CashflowItem.key == GRANT_KEY))


def test_auto_resolve_then_reopen(client: TestClient) -> None:
    login(client, "rahima@demo.setu")
    [sf] = shortfalls(client)
    assert sf["status"] == "OPEN"

    add_grant("10000.00")  # covers the whole horizon
    res = client.post("/alerts/recompute").json()
    assert res["resolved"] >= 1
    [sf_after] = shortfalls(client)
    assert sf_after["status"] == "RESOLVED" and sf_after["facts"]["resolved_by"] == "engine"

    drop_grant()
    res = client.post("/alerts/recompute").json()
    assert res["reopened"] == 1
    [again] = shortfalls(client)
    assert again["id"] == sf["id"] and again["status"] == "OPEN"


def test_acknowledge_and_user_resolve_stick(client: TestClient) -> None:
    login(client, "rahima@demo.setu")
    [sf] = shortfalls(client)
    ack = client.post(f"/alerts/{sf['id']}/acknowledge").json()
    assert ack["status"] == "ACKNOWLEDGED"
    client.post("/alerts/recompute")
    assert shortfalls(client)[0]["status"] == "ACKNOWLEDGED"
    done = client.post(f"/alerts/{sf['id']}/resolve").json()
    assert done["status"] == "RESOLVED" and done["facts"]["resolved_by"] == "user"
    res = client.post("/alerts/recompute").json()
    assert res["reopened"] == 0
    assert shortfalls(client)[0]["status"] == "RESOLVED"
    assert client.post(f"/alerts/{uuid.uuid4()}/resolve").status_code == 404


def test_resolved_shortfall_reopens_when_it_grows(client: TestClient) -> None:
    """A 500.00 outflow on 2026-11-01 keeps the first shortfall on 2026-11-07 but grows it from
    1,560.00 to 2,060.00, so a user-resolved alert must reopen."""
    login(client, "rahima@demo.setu")
    [sf] = shortfalls(client)
    client.post(f"/alerts/{sf['id']}/resolve")
    add_grant("500.00", FlowDirection.OUT)
    try:
        res = client.post("/alerts/recompute").json()
        assert res["reopened"] == 1
        [again] = shortfalls(client)
        assert again["id"] == sf["id"]
        assert again["status"] == "OPEN" and again["amount"] == "2060.00"
    finally:
        drop_grant()


def test_long_party_code_key_is_hashed() -> None:
    from datetime import date as d

    from app.domain.alerts import key

    k = key("x" * 64, "deadline", "SETU-2026-0001:m2", d(2026, 11, 7))
    assert len(k) <= 80 and k.startswith("alert:deadline:")
    assert k == key("x" * 64, "deadline", "SETU-2026-0001:m2", d(2026, 11, 7))
