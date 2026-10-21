"""ACCOUNT_NOT_VERIFIED: every money action is refused for an account that is not ACTIVE, at the
router dependency and again in the service layer. Reads stay open."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import CurrentUser
from app.db.enums import Language, Role, UserStatus
from app.errors import Forbidden
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    approved,
    identity,
    must,
    onboard,
    pdf,
    review_id_for,
)

pytestmark = pytest.mark.db

ID = str(uuid.uuid4())
MONEY_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    (
        "post",
        "/deals",
        {"supplier_id": ID, "title": "x", "quantity": "1", "unit": "m", "unit_price": "1"},
    ),
    ("post", f"/deals/{ID}/milestones/propose", {"template": "30_60_10"}),
    ("post", f"/deals/{ID}/milestones/confirm", {"party_role": "BUYER"}),
    ("post", f"/deals/{ID}/escrow/fund", {}),
    ("post", f"/deals/{ID}/fx-lock", {}),
    ("post", f"/deals/{ID}/beneficiary", {"bank_account_id": ID}),
    ("post", f"/deals/{ID}/refund", {"reason": "dispute raised"}),
    ("post", f"/milestones/{ID}/release", {"idempotency_key": "k-1"}),
    ("post", f"/milestones/{ID}/refund", {"reason": "dispute raised"}),
    ("post", f"/milestones/{ID}/evidence", {"status": "VERIFIED"}),
    ("post", "/financing/applications", {"option_id": "x", "deal_id": ID}),
    ("post", f"/financing/applications/{ID}/simulate-approval", None),
    ("post", f"/approvals/{ID}/approve", {}),
    ("post", f"/approvals/{ID}/resend-otp", None),
    (
        "post",
        f"/parties/{ID}/members",
        {"email": "a@b.co", "display_name": "Ab", "member_role": "VIEWER"},
    ),
    ("delete", f"/parties/{ID}/members/{ID}", None),
    (
        "post",
        "/supplier/accounts/change-request",
        {"deal_id": ID, "account_number": "123456789", "bank_name": "B"},
    ),
]
READS = ("/deals", "/approvals", "/notifications", "/auth/me", "/account", "/onboarding/me")


def refused(res: Any) -> bool:
    return res.status_code == 403 and res.json().get("code") == "ACCOUNT_NOT_VERIFIED"


def call(client: TestClient, method: str, path: str, body: Any, headers: dict[str, str]) -> Any:
    return client.request(method, path, json=body, headers=headers)


def test_every_money_route_refuses_a_submitted_but_unverified_account(
    client: TestClient, fake: FakeNeon
) -> None:
    for role in ("BUYER", "SUPPLIER"):
        headers, state = onboard(client, fake, role)
        assert state["account_status"] == "PENDING_VERIFICATION"
        for method, path, body in MONEY_ROUTES:
            res = call(client, method, path, body, headers)
            assert refused(res), (role, method, path, res.status_code, res.text)
        reads = READS if role == "BUYER" else tuple(p for p in READS if p != "/approvals")
        for path in reads:
            assert client.get(path, headers=headers).status_code == 200, (role, path)


def test_every_money_route_refuses_an_applicant_still_filling_the_form(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=headers))
    for method, path, body in MONEY_ROUTES:
        res = call(client, method, path, body, headers)
        assert refused(res), (method, path, res.status_code, res.text)
    upload = client.post(
        f"/deals/{ID}/documents",
        data={"doc_type": "PROFORMA_INVOICE"},
        files={"file": ("a.pdf", pdf(), "application/pdf")},
        headers=headers,
    )
    assert refused(upload), upload.text


def test_document_upload_on_a_deal_is_gated(client: TestClient, fake: FakeNeon) -> None:
    headers, _ = onboard(client, fake)
    res = client.post(
        f"/deals/{ID}/documents",
        data={"doc_type": "PROFORMA_INVOICE"},
        files={"file": ("a.pdf", pdf(), "application/pdf")},
        headers=headers,
    )
    assert refused(res), res.text


def test_a_suspended_or_rejected_account_is_stopped_earlier(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, state = onboard(client, fake)
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, state["email"])
    must(
        client.post(
            f"/admin/onboarding/{rid}/reject",
            json={"reason": "Licence is not valid"},
            headers=admin,
        )
    )
    res = client.post("/deals", json=MONEY_ROUTES[0][2], headers=headers)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_REJECTED"


def test_a_verified_account_passes_the_gate(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    headers, _ = approved(client, fake, admin)
    for method, path, body in MONEY_ROUTES:
        res = call(client, method, path, body, headers)
        assert not refused(res), (method, path, res.status_code, res.text)
    assert client.get("/deals", headers=headers).status_code == 200


def money_services() -> list[tuple[str, Any]]:
    from app.services import (
        approvals,
        beneficiary,
        deals,
        escrow,
        financing,
        fx_lock,
        members,
        supplier_accounts,
    )
    from app.services.documents import upload

    return [
        ("create_deal", lambda u: deals.create_deal(None, u, None)),
        ("propose_milestones", lambda u: deals.propose_milestones(None, u, ID, None)),
        ("confirm_milestones", lambda u: deals.confirm_milestones(None, u, ID, None)),
        ("fund_escrow", lambda u: escrow.fund_escrow(None, u, ID)),
        ("release_tranche", lambda u: escrow.release_tranche(None, ID, u, "k")),
        ("refund", lambda u: escrow.refund(None, u, reason="x", deal_id=ID)),
        ("lock_fx", lambda u: fx_lock.lock_fx(None, u, ID)),
        ("change_beneficiary", lambda u: beneficiary.change_beneficiary(None, u, ID, ID)),
        ("financing.apply", lambda u: financing.apply(None, u, None)),
        ("simulate_approval", lambda u: financing.simulate_approval(None, u, ID)),
        ("approvals.approve", lambda u: approvals.approve(None, u, ID)),
        ("approvals.resend_otp", lambda u: approvals.resend_otp(None, u, ID)),
        ("members.invite", lambda u: members.invite(None, u, ID, None)),
        ("members.remove", lambda u: members.remove(None, u, ID, ID)),
        (
            "supplier_accounts.request_change",
            lambda u: supplier_accounts.request_change(None, u, None),
        ),
        ("upload.accept_upload", lambda u: upload.accept_upload(None, u, None, None, None, b"")),
    ]


@pytest.mark.parametrize(
    "status",
    [
        UserStatus.PENDING_PROFILE,
        UserStatus.PENDING_VERIFICATION,
        UserStatus.REJECTED,
        UserStatus.SUSPENDED,
    ],
)
def test_the_service_layer_refuses_on_its_own(status: UserStatus) -> None:
    user = CurrentUser(
        uuid.uuid4(),
        "x@example.com",
        "X",
        Role.BUYER,
        Language.EN.value,
        uuid.uuid4(),
        account_status=status,
    )
    for name, fn in money_services():
        with pytest.raises(Forbidden) as exc:
            fn(user)
        assert exc.value.code == "ACCOUNT_NOT_VERIFIED", name
