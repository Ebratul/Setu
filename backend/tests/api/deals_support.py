"""Shared helpers for the FR-5 deal/escrow tests (real Postgres, seeded demo, TestClient)."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.deps import CurrentUser, to_current
from app.db.models import Party, User
from app.db.session import batch_session
from app.main import create_app
from tests.api.conftest import login

RAHIMA, KARIM = "rahima@demo.setu", "karim@demo.setu"
HUAXIN_USER, ADMIN, JUDGE = "huaxin@demo.setu", "admin@demo.setu", "judge@demo.setu"
HUAXIN, BRIGHTLINE, HUAMENG = "shaoxing-huaxin", "ningbo-brightline", "guangzhou-huameng"


def as_user(email: str) -> TestClient:
    return login(TestClient(create_app()), email)


def party_id(code: str) -> str:
    with batch_session() as s:
        return str(s.scalars(select(Party.id).where(Party.code == code)).one())


def current_user_of(email: str) -> CurrentUser:
    with batch_session() as s:
        return to_current(s.scalars(select(User).where(User.email == email)).one())


def give_cash(code: str, amount: str = "1000000.00") -> None:
    with batch_session() as s:
        s.execute(update(Party).where(Party.code == code).values(cash_balance=Decimal(amount)))


def payload(supplier: str, qty: str = "8000", price: str = "1.20", **extra: Any) -> dict[str, Any]:
    return {
        "supplier_id": supplier,
        "title": "Dyed cotton jersey fabric",
        "hs_code": "6006.22",
        "quantity": qty,
        "unit": "m",
        "unit_price": price,
        "incoterm": "FOB",
        "port_of_loading": "Ningbo",
        "port_of_discharge": "Chittagong",
        "costs": [
            {"kind": "FREIGHT", "amount": "600.00"},
            {"kind": "BANK_CHARGES", "amount": "150.00"},
        ],
        **extra,
    }


def create(buyer: TestClient, supplier_code: str = HUAXIN, **kw: Any) -> dict[str, Any]:
    res = buyer.post("/deals", json=payload(party_id(supplier_code), **kw))
    assert res.status_code == 201, res.text
    return res.json()


def propose(buyer: TestClient, deal_id: str, **body: Any) -> dict[str, Any]:
    res = buyer.post(f"/deals/{deal_id}/milestones/propose", json=body or {})
    assert res.status_code == 200, res.text
    return res.json()


def confirmed(buyer: TestClient, supplier: TestClient | None, deal_id: str) -> dict[str, Any]:
    """Confirm for both sides (an admin stands in for suppliers without a demo user)."""
    assert buyer.post(f"/deals/{deal_id}/milestones/confirm", json={}).status_code == 200
    if supplier is not None:
        res = supplier.post(f"/deals/{deal_id}/milestones/confirm", json={})
    else:
        res = as_user(ADMIN).post(
            f"/deals/{deal_id}/milestones/confirm", json={"party_role": "SUPPLIER"}
        )
    assert res.status_code == 200, res.text
    return res.json()


def fund(buyer: TestClient, deal_id: str, amount: str | None = None) -> dict[str, Any]:
    res = buyer.post(
        f"/deals/{deal_id}/escrow/fund", json={} if amount is None else {"amount": amount}
    )
    assert res.status_code == 200, res.text
    return res.json()


def verify_evidence(client: TestClient, milestone_id: str, status: str = "VERIFIED") -> None:
    res = client.post(f"/milestones/{milestone_id}/evidence", json={"status": status})
    assert res.status_code == 200, res.text


def release(
    buyer: TestClient, milestone_id: str, key: str | None = None
) -> tuple[int, dict[str, Any]]:
    res = buyer.post(
        f"/milestones/{milestone_id}/release", json={"idempotency_key": key or uuid.uuid4().hex}
    )
    return res.status_code, res.json()


def funded_deal(
    buyer: TestClient, supplier_code: str = HUAXIN, amount: str | None = None, **kw: Any
) -> dict[str, Any]:
    """CONFIRMED + first tranche deposited (M1 READY)."""
    supplier = as_user(HUAXIN_USER) if supplier_code == HUAXIN else None
    deal = create(buyer, supplier_code, **kw)
    propose(buyer, deal["id"])
    confirmed(buyer, supplier, deal["id"])
    return fund(buyer, deal["id"], amount)
