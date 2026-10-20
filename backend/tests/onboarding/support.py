"""Helpers that drive the multi-step onboarding through the real API (Neon test tokens)."""

import random
import re
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.enums import Language, Role, UserStatus
from app.db.models import AuditLog, User
from app.db.session import batch_session
from app.domain.onboarding_validation import USCC_ALPHABET, uscc_check_char
from app.security import crypto, totp
from app.services import sms
from tests.auth.support import FakeNeon

PDF = b"%PDF-1.4\n%setu test document\n"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def uniq() -> str:
    return uuid.uuid4().hex[:10]


def pdf(tag: str | None = None) -> bytes:
    return PDF + (tag or uniq()).encode() + b"\n%%EOF\n"


def new_uscc() -> str:
    first = "".join(random.choice(USCC_ALPHABET) for _ in range(17))
    return first + (uscc_check_char(first) or "0")


def buyer_business(**over: Any) -> dict[str, Any]:
    u = uniq()
    out: dict[str, Any] = {
        "legal_name": f"Padma Textile Imports {u} Ltd",
        "trade_name": "Padma Textiles",
        "trade_license_no": f"TL-{u.upper()}",
        "license_authority": "Dhaka South City Corporation",
        "license_expiry": (date.today() + timedelta(days=400)).isoformat(),
        "irc_no": f"IRC-{u.upper()}",
        "tin": "123456789012",
        "address": {
            "division": "Dhaka",
            "district": "Dhaka",
            "upazila": "Motijheel",
            "street": "12 Dilkusha Road",
        },
        "business_type": "TRADER",
        "main_import_goods": "Cotton fabric",
        "monthly_import_volume": "2M_10M_BDT",
    }
    out.update(over)
    return out


def supplier_business(**over: Any) -> dict[str, Any]:
    u = uniq()
    name = f"Ningbo Brightline {u} Co., Ltd"
    out: dict[str, Any] = {
        "legal_name_en": name,
        "legal_name_zh": "宁波明线有限公司",
        "uscc": new_uscc(),
        "address": {"province": "Zhejiang", "city": "Ningbo", "district": "Yinzhou"},
        "business_scope": "Textile fabrics export",
        "export_experience_years": 8,
        "bank": {
            "bank_name": "Bank of Ningbo",
            "holder_name": name,
            "account_no": f"62220{random.randint(10**9, 10**10 - 1)}",
            "currency": "CNY",
            "swift": "NBBKCN2N",
        },
    }
    out.update(over)
    return out


RECOVERY: dict[str, list[str]] = {}  # admin user id -> unused recovery codes (step-up tokens)


def totp_stepup(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    """Headers plus an `X-Stepup` token earned with the next recovery code of a made admin."""
    uid = client.get("/auth/me", headers=headers).json()["id"]
    code = RECOVERY[uid].pop(0)
    res = client.post("/auth/stepup/verify", json={"code": code}, headers=headers)
    assert res.status_code == 200, res.text
    return {**headers, "X-Stepup": res.json()["token"]}


def make_admin(
    email: str | None = None, sub: str | None = None, status: UserStatus = UserStatus.ACTIVE
) -> tuple[uuid.UUID, str, str]:
    u = uniq()
    email, sub = email or f"admin-{u}@example.com", sub or f"sub-admin-{u}"
    uid = uuid.uuid4()
    codes = totp.new_recovery_codes()
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
                mfa_enabled=True,
                mfa_secret_encrypted=crypto.encrypt_text(totp.new_secret()),
                mfa_recovery_hashes=[
                    crypto.blind_index(f"recovery:{uid}", totp.normalise_recovery(c)) for c in codes
                ],
            )
        )
    RECOVERY[str(uid)] = codes
    return uid, email, sub


def admin_headers(fake: FakeNeon) -> tuple[uuid.UUID, dict[str, str]]:
    uid, email, sub = make_admin()
    return uid, bearer(fake.token(sub=sub, email=email))


def identity(fake: FakeNeon, **claims: Any) -> tuple[dict[str, str], str, str]:
    u = uniq()
    email, sub = claims.pop("email", f"user-{u}@example.com"), claims.pop("sub", f"sub-{u}")
    return bearer(fake.token(sub=sub, email=email, **claims)), email, sub


def must(res: Any, code: int = 200) -> dict[str, Any]:
    assert res.status_code == code, f"{res.status_code}: {res.text}"
    return res.json() if res.content else {}


def go_contact(client: TestClient, h: dict[str, str], mobile: str | None = None) -> dict[str, Any]:
    body = {
        "full_name": "Nusrat Jahan",
        "designation": "Managing Director",
        "mobile": mobile or f"+88017{random.randint(10**7, 10**8 - 1)}",
        "language": "en",
    }
    must(client.put("/onboarding/contact", json=body, headers=h))
    sent = must(client.post("/onboarding/phone/send", headers=h))
    code = sent["demo_code"]
    if code is None:  # DEMO_MODE=false: read it from the SMS outbox, as a phone would
        outbox: Any = sms.get_provider()
        code = re.search(r"(\d{6})", outbox.sent[-1].text).group(1)  # type: ignore[union-attr]
    return must(client.post("/onboarding/phone/verify", json={"code": code}, headers=h))


def upload(
    client: TestClient, h: dict[str, str], doc_type: str, data: bytes | None = None
) -> dict[str, Any]:
    res = client.post(
        "/onboarding/documents",
        data={"type": doc_type},
        files={"file": ("doc.pdf", data or pdf(), "application/pdf")},
        headers=h,
    )
    return must(res, 201)


def consent(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    state = must(client.get("/onboarding/me", headers=h))
    body = {
        "terms_version": state["terms_version"],
        "accept_terms": True,
        "accept_privacy": True,
        "consent_verification": True,
    }
    return must(client.put("/onboarding/consent", json=body, headers=h))


REQUIRED = {"BUYER": ("TRADE_LICENSE", "IRC"), "SUPPLIER": ("BUSINESS_LICENSE", "BANK_PROOF")}


def onboard(
    client: TestClient,
    fake: FakeNeon,
    role: str = "BUYER",
    *,
    business: dict[str, Any] | None = None,
    doc_bytes: bytes | None = None,
    submit: bool = True,
    headers: dict[str, str] | None = None,
    email: str | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Sign up a fresh identity and walk every step. Returns (auth headers, final state + email)."""
    if headers is None:
        headers, email, _ = identity(fake, **({"email": email} if email else {}))
    must(client.post("/onboarding/role", json={"role": role}, headers=headers))
    go_contact(client, headers)
    biz = business or (buyer_business() if role == "BUYER" else supplier_business())
    must(client.put("/onboarding/business", json=biz, headers=headers))
    for t in REQUIRED[role]:
        upload(client, headers, t, doc_bytes)
    consent(client, headers)
    state = (
        must(client.post("/onboarding/submit", headers=headers))
        if submit
        else must(client.get("/onboarding/me", headers=headers))
    )
    return headers, {**state, "email": email}


def supplier_body(**over: Any) -> dict[str, Any]:
    """Keyword arguments for `onboard(...)` / `approved(...)` that make a supplier."""
    return {"role": "SUPPLIER", **over}


def review_id_for(client: TestClient, admin: dict[str, str], email_part: str) -> str:
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    return next(i["id"] for i in items if email_part in i["user_email"])


def approved(
    client: TestClient, fake: FakeNeon, admin: dict[str, str], **kw: Any
) -> tuple[dict[str, str], str]:
    """Onboard and approve; returns (headers, party_id)."""
    headers, state = onboard(client, fake, **kw)
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    item = next(i for i in items if i["user_email"] == state["email"])
    must(client.post(f"/admin/onboarding/{item['id']}/approve", headers=admin))
    return headers, item["party"]["id"]


def audit(action: str) -> list[AuditLog]:
    with batch_session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == action)))
        s.expunge_all()
        return rows
