# ruff: noqa: F811  (fixtures imported from the API test conftest are used as arguments)
"""The five buyer and five supplier onboarding sets, walked through the real API with the committed
files: every step is accepted and the automatic checks all pass (AUTO_CLEAR)."""

import mimetypes
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from synthetic.form_samples.build import OUT
from synthetic.form_samples.people import BUYERS, SUPPLIERS
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.auth.support import FakeNeon
from tests.onboarding.conftest import client, fake, sms_box  # noqa: F401  (fixtures)
from tests.onboarding.support import admin_headers, bearer, consent, must
from tests.synthetic.test_form_samples import (
    buyer_business,
    col,
    contact,
    supplier_business,
)

pytestmark = pytest.mark.db


def walk(
    client: TestClient, fake: FakeNeon, role: str, n: int, folder: str, business: dict[str, Any]
) -> dict[str, Any]:
    key = "buyer" if role == "BUYER" else "supplier"
    people = (BUYERS if role == "BUYER" else SUPPLIERS)[n]
    h = bearer(fake.token(sub=f"sub-sample-{key}-{n}", email=people.email))
    must(client.post("/onboarding/role", json={"role": role}, headers=h))
    must(client.put("/onboarding/contact", json=contact(col(f"ob-contact-{key}", n)), headers=h))
    sent = must(client.post("/onboarding/phone/send", headers=h))
    must(client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h))
    must(client.put("/onboarding/business", json=business, headers=h))
    slots = (
        {
            "1_trade_licence.pdf": "TRADE_LICENSE",
            "2_import_registration_certificate_irc.pdf": "IRC",
            "3_tin_certificate.pdf": "TIN_CERT",
            "4_other_supporting_document.pdf": "OTHER",
        }
        if role == "BUYER"
        else {
            "1_business_licence.pdf": "BUSINESS_LICENSE",
            "2_bank_proof.pdf": "BANK_PROOF",
            "3_other_supporting_document.pdf": "OTHER",
        }
    )
    for name, doc_type in slots.items():
        path = OUT / "onboarding" / folder / name
        res = client.post(
            "/onboarding/documents",
            data={"type": doc_type},
            files={"file": (name, path.read_bytes(), "application/pdf")},
            headers=h,
        )
        must(res, 201)
    consent(client, h)
    state = must(client.post("/onboarding/submit", headers=h))
    assert state["account_status"] == "PENDING_VERIFICATION"
    return {"headers": h, "state": state}


def assert_clean(client: TestClient, admin: dict[str, str], email: str) -> None:
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    item = next(i for i in items if i["user_email"] == email)
    bad = [(c["code"], c["status"]) for c in item["checks"] if c["status"] != "PASS"]
    assert not bad and item["recommendation"] == "AUTO_CLEAR", bad


@pytest.mark.parametrize("n", range(5))
def test_buyer_set_onboards_cleanly(client: TestClient, fake: FakeNeon, n: int) -> None:
    _, admin = admin_headers(fake)
    walk(client, fake, "BUYER", n, f"buyer-{n + 1}", buyer_business(col("ob-business-buyer", n)))
    assert_clean(client, admin, BUYERS[n].email)


@pytest.mark.parametrize("n", range(5))
def test_supplier_set_onboards_cleanly(client: TestClient, fake: FakeNeon, n: int) -> None:
    _, admin = admin_headers(fake)
    walk(
        client,
        fake,
        "SUPPLIER",
        n,
        f"supplier-{n + 1}",
        supplier_business(col("ob-business-supplier", n)),
    )
    assert_clean(client, admin, SUPPLIERS[n].email)


@pytest.mark.parametrize(
    "name",
    ["buyer-1/trade_licence_photo.jpg", "supplier-1/business_licence_photo.png"],
)
def test_the_picture_versions_are_accepted_uploads(
    client: TestClient, fake: FakeNeon, name: str
) -> None:
    role = "BUYER" if name.startswith("buyer") else "SUPPLIER"
    h = bearer(fake.token(sub=f"sub-pic-{role}", email=f"pic-{role.lower()}@example.com"))
    must(client.post("/onboarding/role", json={"role": role}, headers=h))
    path = OUT / "onboarding" / name
    res = client.post(
        "/onboarding/documents",
        data={"type": "TRADE_LICENSE" if role == "BUYER" else "BUSINESS_LICENSE"},
        files={"file": (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0])},
        headers=h,
    )
    doc = must(res, 201)
    assert re.search(r"image/(jpeg|png)", doc["mime"])
