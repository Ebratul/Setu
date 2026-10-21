"""Admin review: masked detail, reveal-with-reason, the four decisions, notifications, access."""

import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.enums import AccountStatus, KybStatus, Role, UserStatus
from app.db.models import BankAccount, OnboardingReview, Party, User, VerificationDocument
from app.db.session import batch_session
from app.security import crypto
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    audit,
    bearer,
    buyer_business,
    identity,
    must,
    onboard,
    review_id_for,
    totp_stepup,
    upload,
)

pytestmark = pytest.mark.db


def pending(client: TestClient, fake: FakeNeon, role: str = "BUYER", **kw: Any):
    headers, state = onboard(client, fake, role, **kw)
    _, admin = admin_headers(fake)
    return headers, state, admin, review_id_for(client, admin, state["email"])


def user_row(email: str) -> User:
    with batch_session() as s:
        u = s.scalars(select(User).where(User.email == email)).one()
        s.expunge(u)
        return u


def test_list_and_detail_are_masked_and_filterable(client: TestClient, fake: FakeNeon) -> None:
    biz = buyer_business(trade_license_no="TL-ABCD-5566", tin="111122223333")
    _, state, admin, rid = pending(client, fake, business=biz)
    _, sup, _, srid = pending(client, fake, "SUPPLIER")
    detail = must(client.get(f"/admin/onboarding/{rid}", headers=admin))
    assert detail["role"] == "BUYER" and detail["status"] == "PENDING"
    assert detail["account_status"] == "PENDING_VERIFICATION" and detail["revision"] == 1
    assert detail["business"]["trade_license_no_masked"] == "****5566"
    assert "TL-ABCD-5566" not in str(detail) and "111122223333" not in str(detail)
    assert detail["contact"]["mobile_masked"].startswith("01") and len(detail["documents"]) == 2
    buyers = client.get("/admin/onboarding?role=BUYER", headers=admin).json()["items"]
    suppliers = client.get("/admin/onboarding?role=SUPPLIER", headers=admin).json()["items"]
    assert rid in {i["id"] for i in buyers} and rid not in {i["id"] for i in suppliers}
    assert srid in {i["id"] for i in suppliers}
    pend = client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
    assert {rid, srid} <= {i["id"] for i in pend}
    del state, sup


def test_reveal_needs_a_reason_returns_one_value_and_audits_without_it(
    client: TestClient, fake: FakeNeon
) -> None:
    biz = buyer_business(trade_license_no="TL-REVEAL-77", tin="999988887777")
    _, _, admin, rid = pending(client, fake, business=biz)
    url = f"/admin/onboarding/{rid}/reveal"
    assert client.post(url, json={"field": "tin"}, headers=admin).status_code == 422
    short = client.post(url, json={"field": "tin", "reason": "short"}, headers=admin)
    assert short.status_code == 422
    bad = client.post(url, json={"field": "password", "reason": "checking the form"}, headers=admin)
    assert bad.status_code == 422
    out = must(
        client.post(
            url, json={"field": "tin", "reason": "Matching against NBR record"}, headers=admin
        )
    )
    assert out == {"field": "tin", "value": "999988887777"}
    lic = must(
        client.post(
            url,
            json={"field": "trade_license_no", "reason": "Cross-check with city corp"},
            headers=admin,
        )
    )
    assert lic["value"] == "TL-REVEAL-77"
    mobile = must(
        client.post(url, json={"field": "mobile", "reason": "Call back to confirm"}, headers=admin)
    )
    assert re.fullmatch(r"\+8801[3-9]\d{8}", mobile["value"])
    nothing = client.post(
        url, json={"field": "uscc", "reason": "no such field for a buyer"}, headers=admin
    )
    assert nothing.status_code == 404
    rows = audit("onboarding.reveal")
    mine = [r for r in rows if r.payload.get("review_id") == rid]
    assert {r.payload["field"] for r in mine} == {"tin", "trade_license_no", "mobile"}
    assert all("reason" in r.payload for r in mine)
    blob = str([r.payload for r in mine])
    assert "999988887777" not in blob and "TL-REVEAL-77" not in blob and mobile["value"] not in blob


def test_approve_activates_everything_and_notifies(
    client: TestClient, fake: FakeNeon, mail_box
) -> None:
    headers, state, admin, rid = pending(client, fake, "SUPPLIER")
    out = must(client.post(f"/admin/onboarding/{rid}/approve", headers=admin))
    assert out["status"] == "APPROVED" and out["decision"] == "APPROVED"
    assert out["account_status"] == "ACTIVE" and out["party"]["kyb_status"] == "VERIFIED"
    assert out["bank_account"]["status"] == "ACTIVE" and out["decided_by"]
    assert {d["status"] for d in out["documents"]} == {"VERIFIED"}
    u = user_row(state["email"])
    with batch_session() as s:
        party = s.get(Party, u.party_id)
        assert party is not None and party.dedupe_key and len(party.dedupe_key.strip()) == 64
        assert party.kyb_status == KybStatus.VERIFIED and party.onboarded_at
        acct = s.scalars(select(BankAccount).where(BankAccount.party_id == party.id)).one()
        assert acct.status == AccountStatus.ACTIVE and acct.verified
    feed = must(client.get("/notifications", headers=headers))
    assert any(i["kind"] == "ONBOARDING" for i in feed["items"]) and feed["unread"] >= 1
    assert [m.to for m in mail_box.sent] == [state["email"]]
    rows = [r for r in audit("onboarding.decision") if r.payload.get("review_id") == rid]
    assert len(rows) == 1 and rows[0].payload["decision"] == "APPROVED" and rows[0].tier == 2
    again = client.post(f"/admin/onboarding/{rid}/approve", headers=admin)
    assert again.status_code == 409 and again.json()["code"] == "ONBOARDING_DECIDED"


def test_request_changes_then_resubmit(client: TestClient, fake: FakeNeon) -> None:
    headers, state, admin, rid = pending(client, fake)
    items = {
        "items": [
            {"target": "tin", "note": "TIN does not match the certificate"},
            {"target": "IRC", "note": "The IRC scan is unreadable"},
        ]
    }
    assert (
        client.post(
            f"/admin/onboarding/{rid}/request-changes", json={"items": []}, headers=admin
        ).status_code
        == 422
    )
    out = must(client.post(f"/admin/onboarding/{rid}/request-changes", json=items, headers=admin))
    assert out["status"] == "CHANGES_REQUESTED" and out["account_status"] == "PENDING_PROFILE"
    me = must(client.get("/onboarding/me", headers=headers))
    assert me["decision"] == "CHANGES_REQUESTED" and me["account_status"] == "PENDING_PROFILE"
    assert {c["target"] for c in me["change_requests"]} == {"tin", "IRC"}
    irc = next(d for d in me["documents"] if d["type"] == "IRC")
    assert irc["status"] == "REJECTED" and irc["reviewer_notes"] == "The IRC scan is unreadable"
    # the applicant fixes it and sends it again
    must(
        client.put("/onboarding/business", json=buyer_business(tin="123456789012"), headers=headers)
    )
    assert client.delete(f"/onboarding/documents/{irc['id']}", headers=headers).status_code == 204
    upload(client, headers, "IRC")
    final = must(client.post("/onboarding/submit", headers=headers))
    assert final["account_status"] == "PENDING_VERIFICATION" and final["change_requests"] == []
    assert final["decision"] is None
    with batch_session() as s:
        n = len(
            list(
                s.scalars(
                    select(OnboardingReview).where(
                        OnboardingReview.user_id == user_row(state["email"]).id
                    )
                )
            )
        )
        assert n == 2
    rid2 = [
        i["id"]
        for i in client.get("/admin/onboarding?status=PENDING", headers=admin).json()["items"]
        if i["user_email"] == state["email"]
    ]
    assert len(rid2) == 1 and rid2[0] != rid
    assert client.get(f"/admin/onboarding/{rid2[0]}", headers=admin).json()["revision"] == 2
    party_ids = {user_row(state["email"]).party_id}
    assert len(party_ids) == 1  # same business row, not a second one


def test_reject_blocks_the_account_and_needs_a_reason(client: TestClient, fake: FakeNeon) -> None:
    headers, _, admin, rid = pending(client, fake)
    assert client.post(f"/admin/onboarding/{rid}/reject", json={}, headers=admin).status_code == 422
    assert (
        client.post(
            f"/admin/onboarding/{rid}/reject", json={"reason": "no"}, headers=admin
        ).status_code
        == 422
    )
    out = must(
        client.post(
            f"/admin/onboarding/{rid}/reject",
            json={"reason": "Licence is not valid"},
            headers=admin,
        )
    )
    assert out["status"] == "REJECTED" and out["account_status"] == "REJECTED"
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_REJECTED"
    me = must(client.get("/onboarding/me", headers=headers))  # the status page can still say why
    assert me["account_status"] == "REJECTED" and me["decision"] == "REJECTED"


def test_suspend_an_active_account(client: TestClient, fake: FakeNeon) -> None:
    headers, state, admin, rid = pending(client, fake)
    must(client.post(f"/admin/onboarding/{rid}/approve", headers=admin))
    assert (
        client.post(f"/admin/onboarding/{rid}/suspend", json={}, headers=admin).status_code == 422
    )
    out = must(
        client.post(
            f"/admin/onboarding/{rid}/suspend",
            json={"reason": "Chargeback investigation"},
            headers=admin,
        )
    )
    assert out["account_status"] == "SUSPENDED" and out["decision"] == "SUSPENDED"
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 403 and res.json()["code"] == "ACCOUNT_SUSPENDED"
    assert user_row(state["email"]).status == UserStatus.SUSPENDED
    again = client.post(
        f"/admin/onboarding/{rid}/suspend",
        json={"reason": "Chargeback investigation"},
        headers=admin,
    )
    assert again.status_code == 409


def test_nobody_decides_their_own_account(client: TestClient, fake: FakeNeon) -> None:
    headers, state, _, rid = pending(client, fake)
    with batch_session() as s:  # worst case: the applicant is somehow an active, 2FA admin
        row = s.scalars(select(User).where(User.email == state["email"])).one()
        row.role, row.status, row.mfa_enabled = Role.ADMIN, UserStatus.ACTIVE, True
        row.mfa_secret_encrypted = crypto.encrypt_text("x")
    calls = [
        ("approve", None),
        ("reject", {"reason": "a long enough reason"}),
        ("suspend", {"reason": "a long enough reason"}),
        ("request-changes", {"items": [{"target": "tin", "note": "fix it please"}]}),
        ("reveal", {"field": "mobile", "reason": "a long enough reason"}),
    ]
    for verb, body in calls:
        res = client.post(f"/admin/onboarding/{rid}/{verb}", json=body, headers=headers)
        assert res.status_code == 403 and res.json()["code"] == "SELF_DECISION", verb
    with batch_session() as s:
        assert s.get(OnboardingReview, rid).status.value == "PENDING"  # type: ignore[union-attr]


def test_auto_approve_is_demo_only(
    client: TestClient, fake: FakeNeon, sms_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, state, admin, rid = pending(client, fake)
    out = must(client.post(f"/admin/onboarding/{rid}/auto-approve", headers=admin))
    assert out["account_status"] == "ACTIVE"
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    from app.main import create_app

    c2 = TestClient(create_app())
    _, _, admin2, rid2 = pending(c2, fake)
    res = c2.post(f"/admin/onboarding/{rid2}/auto-approve", headers=admin2)
    assert res.status_code == 404
    del state


def test_admin_needs_two_factor_judges_and_buyers_never_get_in(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer, _, admin, rid = pending(client, fake)
    with batch_session() as s:  # an admin without TOTP
        uid = uuid.uuid4()
        s.add(
            User(
                id=uid,
                email=f"nomfa-{uuid.uuid4().hex[:8]}@example.com",
                display_name="No Mfa",
                role=Role.ADMIN,
                language="en",
                is_demo=False,
                status=UserStatus.ACTIVE,
                auth_subject=f"sub-{uid}",
                mfa_enabled=False,
            )
        )
        email = s.get(User, uid).email  # type: ignore[union-attr]
    nomfa = bearer(fake.token(sub=f"sub-{uid}", email=email))
    for method, path in (
        ("get", "/admin/onboarding"),
        ("get", f"/admin/onboarding/{rid}"),
        ("post", f"/admin/onboarding/{rid}/approve"),
    ):
        res = client.request(method, path, headers=nomfa)
        assert res.status_code == 403 and res.json()["code"] == "MFA_REQUIRED", path
    monkeypatch.setenv("JUDGE_INVITE_CODES", "judge-open-sesame")
    get_settings.cache_clear()
    jh, _, _ = identity(fake)
    must(
        client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": "judge-open-sesame"},
            headers=jh,
        )
    )
    destructive = [
        ("get", "/admin/onboarding", None),
        ("post", f"/admin/onboarding/{rid}/approve", None),
        ("post", f"/admin/onboarding/{rid}/reject", {"reason": "should not be possible"}),
        ("post", f"/admin/onboarding/{rid}/suspend", {"reason": "should not be possible"}),
        (
            "post",
            f"/admin/onboarding/{rid}/request-changes",
            {"items": [{"target": "tin", "note": "nope nope"}]},
        ),
        (
            "post",
            f"/admin/onboarding/{rid}/reveal",
            {"field": "tin", "reason": "should not be possible"},
        ),
        ("post", f"/admin/onboarding/{rid}/auto-approve", None),
    ]
    for method, path, body in destructive:
        for who in (jh, buyer):
            res = client.request(method, path, json=body, headers=who)
            assert res.status_code == 403, (path, res.text)
        assert client.request(method, path, json=body).status_code == 401
    assert client.get(f"/admin/onboarding/{rid}", headers=admin).json()["status"] == "PENDING"


def test_decisions_need_a_fresh_totp_stepup_token_not_an_email_code(
    client: TestClient, fake: FakeNeon, mail_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEPUP_REQUIRED", "true")
    get_settings.cache_clear()
    _, _, admin, rid = pending(client, fake)
    res = client.post(f"/admin/onboarding/{rid}/approve", headers=admin)
    assert res.status_code == 403 and res.json()["code"] == "STEPUP_REQUIRED"
    assert (
        client.get(f"/admin/onboarding/{rid}", headers=admin).status_code == 200
    )  # reads are open
    # the mailbox alone is not enough for an admin decision, even with a perfectly valid token
    must(client.post("/auth/stepup/start", headers=admin))
    code = re.search(r"Your Setu code is (\d{6})", mail_box.sent[-1].text).group(1)  # type: ignore[union-attr]
    email_token = must(client.post("/auth/stepup/verify", json={"code": code}, headers=admin))[
        "token"
    ]
    for verb, body in (
        ("approve", None),
        ("reject", {"reason": "a long enough reason"}),
        ("suspend", {"reason": "a long enough reason"}),
        ("request-changes", {"items": [{"target": "tin", "note": "fix it please"}]}),
        ("auto-approve", None),
    ):
        res = client.post(
            f"/admin/onboarding/{rid}/{verb}", json=body, headers={**admin, "X-Stepup": email_token}
        )
        assert res.status_code == 403 and res.json()["code"] == "STEPUP_TOTP_REQUIRED", verb
    ok = client.post(f"/admin/onboarding/{rid}/approve", headers=totp_stepup(client, admin))
    assert ok.status_code == 200, ok.text


def test_unknown_review_is_404(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    rid = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/admin/onboarding/{rid}", headers=admin).status_code == 404
    assert client.post(f"/admin/onboarding/{rid}/approve", headers=admin).status_code == 404
    assert client.get("/admin/onboarding/not-a-uuid", headers=admin).status_code == 422


def test_documents_of_a_decision_stay_attached(client: TestClient, fake: FakeNeon) -> None:
    _, state, admin, rid = pending(client, fake)
    must(
        client.post(
            f"/admin/onboarding/{rid}/reject",
            json={"reason": "Licence is not valid"},
            headers=admin,
        )
    )
    with batch_session() as s:
        docs = list(
            s.scalars(
                select(VerificationDocument).where(
                    VerificationDocument.user_id == user_row(state["email"]).id
                )
            )
        )
        assert len(docs) == 2  # the file and its record stay for the audit trail
