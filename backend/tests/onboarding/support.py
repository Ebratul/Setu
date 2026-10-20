import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import Language, Role, UserStatus
from app.db.models import AuditLog, User
from app.db.session import batch_session
from tests.auth.support import FakeNeon


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def uniq() -> str:
    return uuid.uuid4().hex[:10]


def body(**over: Any) -> dict[str, Any]:
    """A clean Bangladesh buyer submission (auto-clear when the names agree)."""
    u = uniq()
    out: dict[str, Any] = {
        "account_type": "BUYER",
        "display_name": "Nusrat Jahan",
        "legal_name": f"Padma Textile Imports {u} Ltd",
        "license_no": f"TL-{u}",
        "tax_id": "123456789012",
        "city": "Dhaka",
        "country": "BD",
        "language": "en",
        "bank_account": {
            "bank_name": "Sample Bank",
            "bank_country": "BD",
            "account_number": f"90{u}12",
            "holder_name": f"Padma Textile Imports {u} Ltd",
            "currency": "BDT",
            "account_type": "CORPORATE",
        },
    }
    out.update(over)
    return out


def make_admin(
    email: str | None = None, sub: str | None = None, status: UserStatus = UserStatus.ACTIVE
) -> tuple[uuid.UUID, str, str]:
    u = uniq()
    email, sub = email or f"admin-{u}@example.com", sub or f"sub-admin-{u}"
    uid = uuid.uuid4()
    with batch_session() as s:
        s.add(
            User(
                id=uid,
                email=email,
                display_name="Ops Admin",
                role=Role.ADMIN,
                language=Language.EN,
                is_demo=False,
                status=status,
                auth_subject=sub,
            )
        )
    return uid, email, sub


def onboard(
    client: TestClient, fake: FakeNeon, **over: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    """Sign up a fresh identity; returns (auth headers, response json)."""
    u = uniq()
    email, sub = f"user-{u}@example.com", f"sub-{u}"
    headers = bearer(fake.token(sub=sub, email=email))
    res = client.post("/onboarding", json=body(**over), headers=headers)
    assert res.status_code == 201, res.text
    return headers, res.json()


def review_id_for(client: TestClient, admin: dict[str, str], email_part: str) -> str:
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    return next(i["id"] for i in items if email_part in i["user_email"])


def admin_headers(fake: FakeNeon) -> tuple[uuid.UUID, dict[str, str]]:
    uid, email, sub = make_admin()
    return uid, bearer(fake.token(sub=sub, email=email))


def audit(action: str) -> list[AuditLog]:
    with batch_session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == action)))
        s.expunge_all()
        return rows


def approved(
    client: TestClient, fake: FakeNeon, admin: dict[str, str], **over: Any
) -> tuple[dict[str, str], str]:
    """Onboard and approve; returns (headers, party_id)."""
    headers, _ = onboard(client, fake, **over)
    pending = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    mine = client.get("/onboarding/status", headers=headers).json()["party_name"]
    item = next(i for i in pending if i["party"]["legal_name"] == mine)
    res = client.post(f"/admin/onboarding/{item['id']}/approve", headers=admin)
    assert res.status_code == 200, res.text
    return headers, item["party"]["id"]


def supplier_body(**over: Any) -> dict[str, Any]:
    b = body(account_type="SUPPLIER", country="CN", city="Ningbo", tax_id="91330201MA2ABC1234")
    b["bank_account"].update(bank_country="CN", currency="CNY")
    b.update(over)
    return b
