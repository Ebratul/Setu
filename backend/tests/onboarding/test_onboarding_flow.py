"""The multi-step onboarding through the real API: roles, contact + phone code, business rules,
documents, consent, submit, status gating, encryption at rest, audit."""

import re
import time
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.keys import load_signing_key
from app.audit.verify import _db_lines, verify_lines
from app.config import get_settings
from app.db.enums import UserStatus
from app.db.models import (
    AuditLog,
    BankAccount,
    OnboardingProfile,
    PhoneVerification,
    User,
    VerificationDocument,
)
from app.db.session import batch_session
from app.security import crypto
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    audit,
    bearer,
    buyer_business,
    consent,
    go_contact,
    identity,
    must,
    new_uscc,
    onboard,
    pdf,
    review_id_for,
    supplier_business,
    upload,
)

pytestmark = pytest.mark.db


def user_of(email: str) -> User:
    with batch_session() as s:
        u = s.scalars(select(User).where(User.email == email)).one()
        s.expunge(u)
        return u


def profile_of(email: str) -> OnboardingProfile:
    with batch_session() as s:
        u = s.scalars(select(User).where(User.email == email)).one()
        p = s.scalars(select(OnboardingProfile).where(OnboardingProfile.user_id == u.id)).one()
        s.expunge(p)
        return p


def errors_of(res: Any) -> dict[str, str]:
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["code"] == "VALIDATION_FAILED"
    return {e["field"]: e["code"] for e in body["errors"]}


# --- happy path --------------------------------------------------------------------------------


def test_buyer_happy_path_pending_then_approved(client: TestClient, fake: FakeNeon) -> None:
    headers, state = onboard(client, fake)
    assert state["account_status"] == "PENDING_VERIFICATION" and state["role"] == "BUYER"
    assert [s["done"] for s in state["steps"]] == [True] * 6 and state["step"] == 6
    assert state["contact"]["phone_verified"] is True
    assert re.fullmatch(r"01\*+\d{2}", state["contact"]["mobile_masked"])
    assert state["submitted_at"] and state["decision"] is None
    me = must(client.get("/auth/me", headers=headers))  # pending users are admitted
    assert me["account_status"] == "PENDING_VERIFICATION" and me["mfa_enabled"] is False

    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, state["email"])
    must(client.post(f"/admin/onboarding/{rid}/approve", headers=admin))
    assert must(client.get("/onboarding/me", headers=headers))["account_status"] == "ACTIVE"
    assert must(client.get("/auth/me", headers=headers))["account_status"] == "ACTIVE"


def test_me_before_a_role_is_chosen(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    state = must(client.get("/onboarding/me", headers=h))
    assert state["account_status"] is None and state["role"] is None and state["step"] == 0
    assert state["demo_mode"] is True and state["terms_version"] == get_settings().terms_version
    assert client.get("/auth/me", headers=h).status_code == 403  # no account yet


def test_supplier_happy_path(client: TestClient, fake: FakeNeon) -> None:
    _, state = onboard(client, fake, "SUPPLIER")
    assert state["role"] == "SUPPLIER" and state["account_status"] == "PENDING_VERIFICATION"
    assert state["business"]["uscc_masked"].startswith("****")
    _, admin = admin_headers(fake)
    item = next(
        i
        for i in client.get("/admin/onboarding", headers=admin).json()["items"]
        if i["user_email"] == state["email"]
    )
    assert (
        item["party"]["kind"] == "SUPPLIER" and item["bank_account"]["status"] == "PENDING_CHANGE"
    )
    assert item["bank_account"]["account_masked"].startswith("****")


# --- roles -------------------------------------------------------------------------------------


def test_admin_cannot_be_self_chosen(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    res = client.post("/onboarding/role", json={"role": "ADMIN"}, headers=h)
    assert res.status_code == 403 and res.json()["code"] == "ROLE_NOT_ALLOWED"
    assert must(client.get("/onboarding/me", headers=h))["account_status"] is None


def test_allowlisted_email_is_forced_to_admin_case_insensitively(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL_ALLOWLIST", "Boss@Example.com, other@example.com")
    get_settings.cache_clear()
    h, email, _ = identity(fake, email="boss@example.com")
    state = must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    assert state["role"] == "ADMIN" and state["account_status"] == "PENDING_PROFILE"
    assert state["mfa"] == {"enabled": False, "required": True}
    assert user_of(email).status == UserStatus.PENDING_PROFILE


def test_judge_needs_the_invite_code_and_gets_no_party(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JUDGE_INVITE_CODES", "alpha-code-123456,beta-code-4567890")
    get_settings.cache_clear()
    h, email, _ = identity(fake)
    for code in (None, "", "alpha", "ALPHA-CODE-123456", "alpha-code-1234567"):
        res = client.post(
            "/onboarding/role", json={"role": "JUDGE", "invite_code": code}, headers=h
        )
        assert res.status_code == 403 and res.json()["code"] == "INVALID_INVITE_CODE", code
    assert must(client.get("/onboarding/me", headers=h))["account_status"] is None
    state = must(
        client.post(
            "/onboarding/role",
            json={"role": "JUDGE", "invite_code": "beta-code-4567890"},
            headers=h,
        )
    )
    assert state["role"] == "JUDGE" and state["account_status"] == "ACTIVE"
    assert user_of(email).party_id is None
    assert client.get("/admin/onboarding", headers=h).status_code == 403
    assert client.post("/financing/applications", json={}, headers=h).status_code == 403


def test_judge_with_no_codes_configured_is_always_refused(
    client: TestClient, fake: FakeNeon
) -> None:
    h, _, _ = identity(fake)
    res = client.post("/onboarding/role", json={"role": "JUDGE", "invite_code": ""}, headers=h)
    assert res.status_code == 403 and res.json()["code"] == "INVALID_INVITE_CODE"


def test_role_is_idempotent_then_locked_after_step_one(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    a = must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    b = must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    assert a == b
    swapped = must(client.post("/onboarding/role", json={"role": "SUPPLIER"}, headers=h))
    assert swapped["role"] == "SUPPLIER"  # nothing saved yet: still free to change
    go_contact(client, h)
    res = client.post("/onboarding/role", json={"role": "BUYER"}, headers=h)
    assert res.status_code == 409 and res.json()["code"] == "ROLE_LOCKED"


def test_second_neon_subject_with_the_same_email_is_refused(
    client: TestClient, fake: FakeNeon
) -> None:
    h, email, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    other = bearer(fake.token(sub="someone-else", email=email))
    res = client.post("/onboarding/role", json={"role": "BUYER"}, headers=other)
    assert res.status_code == 409 and res.json()["code"] == "EMAIL_IN_USE"


# --- identity and token trust ------------------------------------------------------------------


def test_forged_expired_and_wrong_audience_tokens_are_rejected(
    client: TestClient, fake: FakeNeon
) -> None:
    forged = FakeNeon().token()  # signed by a key Neon never published
    expired = fake.token(exp=int(time.time()) - 3600)
    wrong_aud = fake.token(aud="https://evil.example")
    wrong_iss = fake.token(iss="https://evil.example")
    unsigned = jwt.encode({"sub": "x", "email": "x@example.com"}, key="", algorithm="none")
    for token in (forged, expired, wrong_aud, wrong_iss, unsigned, "junk"):
        for method, path in (
            ("get", "/onboarding/me"),
            ("post", "/onboarding/role"),
            ("put", "/onboarding/contact"),
            ("post", "/onboarding/submit"),
        ):
            res = client.request(method, path, headers=bearer(token), json={"role": "BUYER"})
            assert res.status_code == 401, (path, res.text)
    assert client.get("/onboarding/me").status_code == 401


def test_unverified_email_cannot_start(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake, emailVerified=False)
    res = client.post("/onboarding/role", json={"role": "BUYER"}, headers=h)
    assert res.status_code == 403 and res.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_a_client_sent_user_id_is_never_read(client: TestClient, fake: FakeNeon) -> None:
    victim_h, victim = onboard(client, fake, submit=False)
    victim_user = user_of(victim["email"])
    h, email, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    spoof = {"X-User-Id": str(victim_user.id), "X-Forwarded-User": victim["email"]}
    state = must(client.get(f"/onboarding/me?user_id={victim_user.id}", headers={**h, **spoof}))
    assert state["contact"] is None  # still the caller's own (empty) state
    body = {"full_name": "Eve", "designation": "CEO", "mobile": "01712345678", "language": "en"}
    res = client.put(
        "/onboarding/contact", json={**body, "user_id": str(victim_user.id)}, headers=h
    )
    assert errors_of(res) == {"user_id": "not_allowed"}
    must(client.put("/onboarding/contact", json=body, headers={**h, **spoof}))
    assert profile_of(victim["email"]).data["contact"]["full_name"] == "Nusrat Jahan"
    assert profile_of(email).data["contact"]["full_name"] == "Eve"
    del victim_h


# --- contact and phone code --------------------------------------------------------------------


@pytest.mark.parametrize(
    "mobile",
    [
        "",
        "12345",
        "+8801212345678",
        "+8801712345",
        "+880171234567890",
        "0171234567a",
        "+8613800138000",
    ],
)
def test_bd_mobile_is_validated(client: TestClient, fake: FakeNeon, mobile: str) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    body = {"full_name": "Nusrat", "designation": "MD", "mobile": mobile, "language": "en"}
    res = client.put("/onboarding/contact", json=body, headers=h)
    assert res.status_code == 422
    assert res.json().get("code") == "INVALID_BD_MOBILE" or "mobile" in errors_of(res)


@pytest.mark.parametrize("mobile", ["+8613800138000", "0086 138 0013 8000"])
def test_supplier_may_use_a_foreign_mobile(client: TestClient, fake: FakeNeon, mobile: str) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "SUPPLIER"}, headers=h))
    body = {"full_name": "Wang Lei", "designation": "Sales", "mobile": mobile, "language": "zh"}
    assert client.put("/onboarding/contact", json=body, headers=h).status_code == 200


def test_supplier_mobile_must_still_be_e164(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "SUPPLIER"}, headers=h))
    body = {"full_name": "Wang Lei", "designation": "Sales", "mobile": "12345", "language": "zh"}
    assert client.put("/onboarding/contact", json=body, headers=h).status_code == 422


@pytest.mark.parametrize(
    "mobile", ["01712345678", "+8801712345678", "8801712345678", "+880 1712-345678", "01912345678"]
)
def test_bd_mobile_formats_are_normalised(client: TestClient, fake: FakeNeon, mobile: str) -> None:
    h, email, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    body = {"full_name": "Nusrat", "designation": "MD", "mobile": mobile, "language": "bn"}
    state = must(client.put("/onboarding/contact", json=body, headers=h))
    assert state["contact"]["phone_verified"] is False and state["contact"]["language"] == "bn"
    full = crypto.decrypt_json(profile_of(email).secure)["mobile"]
    assert re.fullmatch(r"\+8801[3-9]\d{8}", full)


def start_contact(client: TestClient, h: dict[str, str]) -> None:
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    body = {"full_name": "Nusrat", "designation": "MD", "mobile": "01712345678", "language": "en"}
    must(client.put("/onboarding/contact", json=body, headers=h))


def test_otp_is_sent_hashed_single_use_and_demo_code_matches_the_sms(
    client: TestClient, fake: FakeNeon, sms_box
) -> None:
    h, email, _ = identity(fake)
    start_contact(client, h)
    sent = must(client.post("/onboarding/phone/send", headers=h))
    assert sent["sent"] is True and sent["expires_in_seconds"] == 300 and sent["sends_left"] == 2
    [msg] = sms_box.sent
    assert sent["demo_code"] in msg.text and msg.to == "+8801712345678"
    with batch_session() as s:
        row = s.scalars(
            select(PhoneVerification).order_by(PhoneVerification.created_at.desc())
        ).first()
        assert row is not None and sent["demo_code"] not in row.code_hash
        assert row.phone_masked.startswith("01") and "712345" not in row.phone_masked
    state = must(
        client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h)
    )
    assert state["contact"]["phone_verified"] is True
    again = client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h)
    assert again.status_code == 400 and again.json()["code"] == "OTP_NOT_SENT"  # single use
    assert profile_of(email).step >= 2


def test_otp_demo_code_is_absent_when_demo_mode_is_off(
    client: TestClient, fake: FakeNeon, sms_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    h, _, _ = identity(fake)
    start_contact(client, h)
    res = client.post("/onboarding/phone/send", headers=h)
    sent = must(res)
    assert "demo_code" not in res.text.replace('"demo_code":null', "") and sent["demo_code"] is None
    code = re.search(r"(\d{6})", sms_box.sent[0].text).group(1)  # type: ignore[union-attr]
    assert code not in res.text
    must(client.post("/onboarding/phone/verify", json={"code": code}, headers=h))


def test_otp_locks_after_five_wrong_codes_even_for_the_right_one(
    client: TestClient, fake: FakeNeon, sms_box
) -> None:
    h, _, _ = identity(fake)
    start_contact(client, h)
    sent = must(client.post("/onboarding/phone/send", headers=h))
    wrong = "000000" if sent["demo_code"] != "000000" else "111111"
    for left in (4, 3, 2, 1):
        res = client.post("/onboarding/phone/verify", json={"code": wrong}, headers=h)
        assert res.status_code == 400 and res.json()["code"] == "OTP_INVALID"
        assert f"{left} tries left" in res.json()["detail"]
    res = client.post("/onboarding/phone/verify", json={"code": wrong}, headers=h)
    assert res.status_code == 423 and res.json()["code"] == "OTP_LOCKED"
    res = client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h)
    assert res.status_code == 423 and res.json()["code"] == "OTP_LOCKED"
    fresh = must(client.post("/onboarding/phone/send", headers=h))  # a new code unlocks
    must(client.post("/onboarding/phone/verify", json={"code": fresh["demo_code"]}, headers=h))
    assert len(audit("onboarding.phone_failed")) >= 5


def test_otp_expires_after_five_minutes(client: TestClient, fake: FakeNeon, sms_box) -> None:
    h, email, _ = identity(fake)
    start_contact(client, h)
    sent = must(client.post("/onboarding/phone/send", headers=h))
    with batch_session() as s:
        uid = s.scalars(select(User.id).where(User.email == email)).one()
        for row in s.scalars(select(PhoneVerification).where(PhoneVerification.user_id == uid)):
            row.expires_at = row.created_at.replace(year=2000)
    res = client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h)
    assert res.status_code == 410 and res.json()["code"] == "OTP_EXPIRED"


def test_otp_sends_are_limited_to_three_per_ten_minutes(
    client: TestClient, fake: FakeNeon, sms_box
) -> None:
    h, _, _ = identity(fake)
    start_contact(client, h)
    for left in (2, 1, 0):
        assert must(client.post("/onboarding/phone/send", headers=h))["sends_left"] == left
    res = client.post("/onboarding/phone/send", headers=h)
    assert res.status_code == 429 and res.json()["code"] == "OTP_RATE_LIMIT"
    assert len(sms_box.sent) == 3


def test_changing_the_mobile_drops_the_verification(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    state = go_contact(client, h, "01712345678")
    assert state["contact"]["phone_verified"] is True
    body = {"full_name": "Nusrat", "designation": "MD", "mobile": "01812345678", "language": "en"}
    assert (
        must(client.put("/onboarding/contact", json=body, headers=h))["contact"]["phone_verified"]
        is False
    )


def test_phone_send_needs_a_saved_mobile(client: TestClient, fake: FakeNeon) -> None:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    res = client.post("/onboarding/phone/send", headers=h)
    assert res.status_code == 409 and res.json()["code"] == "MOBILE_REQUIRED"


# --- business rules ----------------------------------------------------------------------------


def role_headers(client: TestClient, fake: FakeNeon, role: str) -> dict[str, str]:
    h, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": role}, headers=h))
    return h


def test_uscc_checksum_good_and_bad(client: TestClient, fake: FakeNeon) -> None:
    h = role_headers(client, fake, "SUPPLIER")
    good = new_uscc()
    assert must(client.put("/onboarding/business", json=supplier_business(uscc=good), headers=h))
    last = good[-1]
    bad_last = "0" if last != "0" else "1"
    bad = good[:-1] + bad_last
    errs = errors_of(
        client.put("/onboarding/business", json=supplier_business(uscc=bad), headers=h)
    )
    assert errs == {"uscc": "INVALID_USCC_CHECKSUM"}
    errs = errors_of(
        client.put("/onboarding/business", json=supplier_business(uscc="123"), headers=h)
    )
    assert errs == {"uscc": "INVALID_USCC_LENGTH"}
    illegal = "I" + good[1:]  # I is not in the USCC alphabet
    assert "uscc" in errors_of(
        client.put("/onboarding/business", json=supplier_business(uscc=illegal), headers=h)
    )
    spaced = " ".join([good[:6], good[6:12], good[12:]]).lower()
    assert must(client.put("/onboarding/business", json=supplier_business(uscc=spaced), headers=h))


def test_supplier_field_errors_are_per_field_with_codes(client: TestClient, fake: FakeNeon) -> None:
    h = role_headers(client, fake, "SUPPLIER")
    biz = supplier_business(legal_name_zh="Ningbo only latin")
    biz["bank"]["swift"] = "NOPE"
    biz["bank"]["account_no"] = "12"
    del biz["address"]["city"]
    errs = errors_of(client.put("/onboarding/business", json=biz, headers=h))
    assert errs == {
        "legal_name_zh": "NEEDS_CHINESE_NAME",
        "bank.swift": "INVALID_SWIFT",
        "bank.account_no": "INVALID_ACCOUNT_NO",
        "address.city": "required",
    }


def test_buyer_field_errors_and_configurable_regexes(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = role_headers(client, fake, "BUYER")
    biz = buyer_business(trade_license_no="!!", irc_no="x", tin="12ab", license_expiry="2020-01-01")
    errs = errors_of(client.put("/onboarding/business", json=biz, headers=h))
    assert errs == {
        "trade_license_no": "INVALID_TRADE_LICENSE",
        "irc_no": "INVALID_IRC",
        "tin": "INVALID_TIN",
        "license_expiry": "LICENSE_EXPIRED",
    }
    monkeypatch.setenv("BD_TIN_REGEX", r"^\d{10}$")
    monkeypatch.setenv("BD_TRADE_LICENSE_REGEX", r"^TRAD/\d{4}$")
    get_settings.cache_clear()
    errs = errors_of(
        client.put("/onboarding/business", json=buyer_business(tin="123456789012"), headers=h)
    )
    assert set(errs) == {"tin", "trade_license_no"}
    ok = buyer_business(tin="1234567890", trade_license_no="TRAD/2024")
    assert must(client.put("/onboarding/business", json=ok, headers=h))


def test_business_body_must_match_the_role_and_forbids_extras(
    client: TestClient, fake: FakeNeon
) -> None:
    buyer = role_headers(client, fake, "BUYER")
    res = client.put("/onboarding/business", json=supplier_business(), headers=buyer)
    assert res.status_code == 422
    assert errors_of(
        client.put(
            "/onboarding/business", json={**buyer_business(), "role": "ADMIN"}, headers=buyer
        )
    ) == {"role": "not_allowed"}
    mismatch = client.put("/onboarding/business", json=supplier_business(), headers=buyer)
    assert mismatch.status_code == 422


def test_submit_needs_every_step_and_names_the_missing_ones(
    client: TestClient, fake: FakeNeon
) -> None:
    h = role_headers(client, fake, "BUYER")
    res = client.post("/onboarding/submit", headers=h)
    assert res.status_code == 422 and res.json()["code"] == "STEP_INCOMPLETE"
    assert {e["field"] for e in res.json()["errors"]} == {
        "contact",
        "business",
        "documents",
        "security",
    }
    go_contact(client, h)
    must(client.put("/onboarding/business", json=buyer_business(), headers=h))
    upload(client, h, "TRADE_LICENSE")
    res = client.post("/onboarding/submit", headers=h)
    assert {e["field"] for e in res.json()["errors"]} == {"documents", "security"}


def test_consent_needs_the_current_terms_and_all_boxes(client: TestClient, fake: FakeNeon) -> None:
    h = role_headers(client, fake, "BUYER")
    ok = {
        "terms_version": get_settings().terms_version,
        "accept_terms": True,
        "accept_privacy": True,
        "consent_verification": True,
    }
    res = client.put("/onboarding/consent", json={**ok, "terms_version": "1999-01"}, headers=h)
    assert res.status_code == 409 and res.json()["code"] == "TERMS_VERSION_MISMATCH"
    for box in ("accept_terms", "accept_privacy", "consent_verification"):
        assert (
            client.put("/onboarding/consent", json={**ok, box: False}, headers=h).status_code == 422
        )
    state = must(client.put("/onboarding/consent", json=ok, headers=h))
    assert state["consent"]["terms_version"] == ok["terms_version"]


def test_nothing_can_change_after_submit(client: TestClient, fake: FakeNeon) -> None:
    h, state = onboard(client, fake)
    doc_id = state["documents"][0]["id"]
    body = {"full_name": "X Y", "designation": "MD", "mobile": "01712345678", "language": "en"}
    calls = [
        client.put("/onboarding/contact", json=body, headers=h),
        client.put("/onboarding/business", json=buyer_business(), headers=h),
        client.post("/onboarding/phone/send", headers=h),
        client.delete(f"/onboarding/documents/{doc_id}", headers=h),
        client.post("/onboarding/submit", headers=h),
        client.post(
            "/onboarding/documents",
            data={"type": "OTHER"},
            files={"file": ("a.pdf", pdf(), "application/pdf")},
            headers=h,
        ),
    ]
    for res in calls:
        assert res.status_code == 409 and res.json()["code"] == "PROFILE_LOCKED", res.text


# --- documents ---------------------------------------------------------------------------------


def test_document_upload_rules(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = role_headers(client, fake, "BUYER")

    def post(doc_type: str, data: bytes, name: str = "a.pdf") -> Any:
        return client.post(
            "/onboarding/documents",
            data={"type": doc_type},
            files={"file": (name, data, "application/pdf")},
            headers=h,
        )

    assert post("TRADE_LICENSE", b"MZ\x90\x00 not a pdf").status_code == 415  # magic bytes
    assert post("TRADE_LICENSE", b"<script>alert(1)</script>", "x.pdf").status_code == 415
    assert post("TRADE_LICENSE", b"").status_code == 400
    wrong = post("BANK_PROOF", pdf())  # supplier-only type
    assert wrong.status_code == 403 and wrong.json()["code"] == "DOC_TYPE_NOT_ALLOWED"
    assert post("NOPE", pdf()).status_code == 422
    monkeypatch.setenv("DOCUMENT_MAX_BYTES", "64")
    get_settings.cache_clear()
    big = post("TRADE_LICENSE", pdf() + b"x" * 200)
    assert big.status_code == 413 and big.json()["code"] == "FILE_TOO_LARGE"
    monkeypatch.setenv("DOCUMENT_MAX_BYTES", str(4 * 1024 * 1024))
    get_settings.cache_clear()
    png = post("IRC", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "../../etc/passwd")
    assert png.status_code == 201
    out = png.json()
    assert out["mime"] == "image/png" and out["original_name"] == "passwd.png"
    assert "/" not in out["original_name"] and out["status"] == "UPLOADED"


def test_same_file_twice_is_one_document_and_delete_works(
    client: TestClient, fake: FakeNeon
) -> None:
    h = role_headers(client, fake, "BUYER")
    data = pdf()
    a = upload(client, h, "TRADE_LICENSE", data)
    b = upload(client, h, "TRADE_LICENSE", data)
    assert a["id"] == b["id"]
    assert len(must(client.get("/onboarding/me", headers=h))["documents"]) == 1
    assert client.delete(f"/onboarding/documents/{a['id']}", headers=h).status_code == 204
    assert must(client.get("/onboarding/me", headers=h))["documents"] == []
    assert client.delete(f"/onboarding/documents/{a['id']}", headers=h).status_code == 404


def test_signed_url_is_private_short_lived_and_bound_to_the_viewer(
    client: TestClient, fake: FakeNeon
) -> None:
    owner, state = onboard(client, fake)
    other, _ = onboard(client, fake)
    _, admin = admin_headers(fake)
    doc = state["documents"][0]
    link = must(client.get(f"/onboarding/documents/{doc['id']}/url", headers=owner))
    assert link["url"].startswith(f"/onboarding/documents/{doc['id']}/file?token=")
    res = client.get(link["url"], headers=owner)
    assert res.status_code == 200 and res.content.startswith(b"%PDF-")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in res.headers["content-disposition"]
    assert res.headers["cache-control"] == "private, no-store"
    # a stranger can neither ask for a link nor use someone else's
    assert client.get(f"/onboarding/documents/{doc['id']}/url", headers=other).status_code == 404
    assert client.get(link["url"], headers=other).status_code in (403, 404)
    assert client.get(link["url"]).status_code == 401
    assert client.get(link["url"] + "tamper", headers=owner).status_code == 403
    # an admin may open it; the view is audited
    alink = must(client.get(f"/onboarding/documents/{doc['id']}/url", headers=admin))
    assert client.get(alink["url"], headers=admin).status_code == 200
    assert len(audit("onboarding.document_viewed")) >= 1


# --- secrets at rest and in responses ----------------------------------------------------------


def test_sensitive_values_are_encrypted_at_rest_and_masked_everywhere(
    client: TestClient, fake: FakeNeon
) -> None:
    biz = buyer_business(
        trade_license_no="TL-9876543210", irc_no="IRC-5555666677", tin="987654321098"
    )
    h, state = onboard(client, fake, business=biz)
    email = state["email"]
    prof = profile_of(email)
    raw_values = ["TL-9876543210", "IRC-5555666677", "987654321098", "9876543210"]
    mobile = crypto.decrypt_json(prof.secure)["mobile"]
    assert crypto.decrypt_json(prof.secure)["business"]["trade_license_no"] == "TL-9876543210"
    assert prof.secure is not None and b"TL-9876543210" not in bytes(prof.secure)
    blob = str(prof.data)
    for raw in [*raw_values, mobile, mobile[-10:]]:
        assert raw not in blob, raw
    assert state["business"]["trade_license_no_masked"] == "****3210"
    # no response (applicant or admin) carries a clear value
    _, admin = admin_headers(fake)
    rid = review_id_for(client, admin, email)
    texts = [
        client.get("/onboarding/me", headers=h).text,
        client.get(f"/admin/onboarding/{rid}", headers=admin).text,
        client.get("/admin/onboarding", headers=admin).text,
        client.get("/account", headers=h).text,
        client.get("/account/export", headers=h).text,
    ]
    for text in texts:
        for raw in [*raw_values, mobile, mobile[-10:]]:
            assert raw not in text, raw
    # the party row keeps only masked identifiers
    item = client.get(f"/admin/onboarding/{rid}", headers=admin).json()
    assert item["party"]["license_no"] == "****3210" and item["party"]["tax_id"] == "****1098"


def test_supplier_bank_account_is_encrypted_with_a_masked_display_value(
    client: TestClient, fake: FakeNeon
) -> None:
    biz = supplier_business()
    biz["bank"]["account_no"] = "6222021234567890"
    _, state = onboard(client, fake, "SUPPLIER", business=biz)
    with batch_session() as s:
        uid = s.scalars(select(User.id).where(User.email == state["email"])).one()
        party = s.scalars(select(User.party_id).where(User.id == uid)).one()
        acct = s.scalars(select(BankAccount).where(BankAccount.party_id == party)).one()
        assert acct.account_number == "****7890"  # what KYB, forensics and approvals display
        assert acct.account_number_encrypted and b"6222021234567890" not in bytes(
            acct.account_number_encrypted
        )
        assert crypto.decrypt_text(acct.account_number_encrypted) == "6222021234567890"
        assert acct.account_number_hmac == crypto.blind_index("bank", "6222021234567890")
        assert acct.holder_name == biz["bank"]["holder_name"]


# --- audit -------------------------------------------------------------------------------------


def test_every_step_is_audited_without_pii_and_the_chain_verifies(
    client: TestClient, fake: FakeNeon
) -> None:
    biz = buyer_business(
        trade_license_no="TL-1122334455", irc_no="IRC-1122334466", tin="555566667777"
    )
    _, state = onboard(client, fake, business=biz)
    uid = str(user_of(state["email"]).id)
    with batch_session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.actor_id == uid)))
        actions = {r.action for r in rows}
        payloads = " ".join(str(r.payload) for r in rows)
    assert {
        "onboarding.role_selected",
        "onboarding.profile_saved",
        "onboarding.phone_sent",
        "onboarding.phone_verified",
        "onboarding.document_uploaded",
        "onboarding.submitted",
    } <= actions
    for raw in ("TL-1122334455", "IRC-1122334466", "555566667777", "01712", "Nusrat"):
        assert raw not in payloads
    lines, anchor = _db_lines(None, None)
    report = verify_lines(lines, load_signing_key().public_key(), anchor_prev_hash=anchor)
    assert report.ok, report


def test_no_pii_or_codes_reach_the_logs(
    client: TestClient,
    fake: FakeNeon,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    biz = buyer_business(
        trade_license_no="TL-7777888899", irc_no="IRC-7777888800", tin="777788889999"
    )
    h, email, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    must(
        client.put(
            "/onboarding/contact",
            json={"full_name": "Zubair Rahman", "designation": "MD", "mobile": "01755443322"},
            headers=h,
        )
    )
    sent = must(client.post("/onboarding/phone/send", headers=h))
    must(client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h))
    must(client.put("/onboarding/business", json=biz, headers=h))
    upload(client, h, "TRADE_LICENSE")
    upload(client, h, "IRC")
    consent(client, h)
    must(client.post("/onboarding/submit", headers=h))
    out = capfd.readouterr()
    text = out.out + out.err + caplog.text
    for secret in (
        "TL-7777888899",
        "IRC-7777888800",
        "777788889999",
        "01755443322",
        "1755443322",
        sent["demo_code"] + "\n",
        f"code={sent['demo_code']}",
        email,
    ):
        assert secret not in text, secret


# --- duplicates, sanctions, hash reuse ---------------------------------------------------------


def checks_of(client: TestClient, admin: dict[str, str], email: str) -> dict[str, dict[str, str]]:
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    item = next(i for i in items if i["user_email"] == email)
    return {c["code"]: c for c in item["checks"]}


def test_duplicate_licence_is_flagged_never_merged(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    first_biz = buyer_business(trade_license_no="TL-DUP-0001")
    h1, s1 = onboard(client, fake, business=first_biz)
    r1 = review_id_for(client, admin, s1["email"])
    must(client.post(f"/admin/onboarding/{r1}/approve", headers=admin))
    again = buyer_business(trade_license_no="tl dup 0001", legal_name="Another Name Ltd")
    h2, s2 = onboard(client, fake, business=again)
    assert s2["account_status"] == "PENDING_VERIFICATION"  # accepted into review, not merged
    dup = checks_of(client, admin, s2["email"])["DUPLICATE_COMPANY"]
    assert dup["status"] == "FAIL" and "earlier party" in dup["detail"]
    mine = {c["code"]: c for c in s2["checks"]}["DUPLICATE_COMPANY"]  # what the applicant sees
    assert mine["detail"] == "needs manual review" and "earlier" not in str(s2["checks"])
    parties = {user_of(s1["email"]).party_id, user_of(s2["email"]).party_id}
    assert len(parties) == 2 and None not in parties
    r2 = review_id_for(client, admin, s2["email"])
    res = client.post(f"/admin/onboarding/{r2}/approve", headers=admin)
    assert res.status_code == 409 and res.json()["code"] == "DUPLICATE_COMPANY_APPROVED"
    assert (
        must(client.get("/onboarding/me", headers=h2))["account_status"] == "PENDING_VERIFICATION"
    )
    del h1


def test_duplicate_uscc_is_flagged_between_two_pending_suppliers(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    uscc = new_uscc()
    onboard(client, fake, "SUPPLIER", business=supplier_business(uscc=uscc))
    _, s2 = onboard(client, fake, "SUPPLIER", business=supplier_business(uscc=uscc))
    assert checks_of(client, admin, s2["email"])["DUPLICATE_COMPANY"]["status"] == "FAIL"
    _, s3 = onboard(client, fake, "SUPPLIER")
    assert checks_of(client, admin, s3["email"])["DUPLICATE_COMPANY"]["status"] == "PASS"


def test_clean_submission_passes_every_check_and_has_a_pass_summary(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    _, state = onboard(client, fake)
    items = client.get("/admin/onboarding", headers=admin).json()["items"]
    item = next(i for i in items if i["user_email"] == state["email"])
    assert item["risk_summary"] == "PASS" and item["recommendation"] == "AUTO_CLEAR"
    assert {c["code"] for c in item["checks"]} >= {
        "SANCTIONS_SCREEN",
        "DUPLICATE_COMPANY",
        "DOC_PRESENT",
        "DOC_HASH_REUSE",
        "PHONE_VERIFIED",
        "LICENSE_EXPIRY",
    }
    assert all(c["status"] == "PASS" for c in item["checks"])
    assert "SANCTIONS_SCREEN" not in {c["code"] for c in state["checks"]}  # hidden from applicant


def test_supplier_holder_name_mismatch_is_a_warning(client: TestClient, fake: FakeNeon) -> None:
    _, admin = admin_headers(fake)
    biz = supplier_business()
    biz["bank"]["holder_name"] = "Chen Wei Personal"
    _, state = onboard(client, fake, "SUPPLIER", business=biz)
    got = checks_of(client, admin, state["email"])
    assert got["KYB_HOLDER_NAME"]["status"] == "WARN"
    assert got["KYB_ACCOUNT_TYPE"]["status"] == "WARN"
    item = next(
        i
        for i in client.get("/admin/onboarding", headers=admin).json()["items"]
        if i["user_email"] == state["email"]
    )
    assert item["risk_summary"] == "WARN" and item["recommendation"] == "NEEDS_REVIEW"


def test_supplier_bank_country_outside_the_list_is_a_warning(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    biz = supplier_business()
    biz["bank"]["swift"] = "ABCDUS33XXX"
    _, state = onboard(client, fake, "SUPPLIER", business=biz)
    assert checks_of(client, admin, state["email"])["KYB_COUNTRY"]["status"] == "WARN"


def test_reusing_a_document_from_another_account_fails_the_hash_check(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    shared = pdf("same-bytes")
    onboard(client, fake, doc_bytes=shared)
    _, second = onboard(client, fake, doc_bytes=shared)
    got = checks_of(client, admin, second["email"])
    assert got["DOC_HASH_REUSE"]["status"] == "FAIL"
    assert {c["code"]: c for c in second["checks"]}["DOC_HASH_REUSE"][
        "detail"
    ] == "needs manual review"
    with batch_session() as s:
        n = len(
            list(
                s.scalars(
                    select(VerificationDocument).where(VerificationDocument.sha256.is_not(None))
                )
            )
        )
    assert n >= 4


def test_sanctions_hit_blocks_and_stays_hidden_from_the_applicant(
    client: TestClient, fake: FakeNeon, mail_box
) -> None:
    _, admin = admin_headers(fake)
    h, email, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=h))
    contact = {"full_name": "Zhao Meilin", "designation": "MD", "mobile": "01712345678"}
    must(client.put("/onboarding/contact", json=contact, headers=h))
    sent = must(client.post("/onboarding/phone/send", headers=h))
    must(client.post("/onboarding/phone/verify", json={"code": sent["demo_code"]}, headers=h))
    must(client.put("/onboarding/business", json=buyer_business(), headers=h))
    upload(client, h, "TRADE_LICENSE")
    upload(client, h, "IRC")
    consent(client, h)
    state = must(client.post("/onboarding/submit", headers=h))
    assert state["account_status"] == "PENDING_VERIFICATION"
    assert "SANCTIONS" not in str(state["checks"])
    item = next(
        i
        for i in client.get("/admin/onboarding", headers=admin).json()["items"]
        if i["user_email"] == email
    )
    assert item["recommendation"] == "BLOCK" and item["risk_summary"] == "FAIL"
    assert {c["code"]: c["status"] for c in item["checks"]}["SANCTIONS_SCREEN"] == "FAIL"
    res = client.post(f"/admin/onboarding/{item['id']}/approve", headers=admin)
    assert res.status_code == 409 and res.json()["code"] == "SANCTIONS_BLOCK"
    must(
        client.post(
            f"/admin/onboarding/{item['id']}/reject",
            json={"reason": "Screening hit confirmed by compliance"},
            headers=admin,
        )
    )


def test_company_name_on_the_sanctions_list_is_blocked_too(
    client: TestClient, fake: FakeNeon
) -> None:
    _, admin = admin_headers(fake)
    biz = supplier_business(legal_name_en="Baihe Orchid Logistics Limited")
    biz["bank"]["holder_name"] = "Baihe Orchid Logistics Limited"
    _, state = onboard(client, fake, "SUPPLIER", business=biz)
    assert checks_of(client, admin, state["email"])["SANCTIONS_SCREEN"]["status"] == "FAIL"


def test_auto_approve_setting_activates_clean_submissions_only(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ONBOARDING_AUTO_APPROVE", "true")
    get_settings.cache_clear()
    _, clean = onboard(client, fake)
    assert clean["account_status"] == "ACTIVE"
    biz = supplier_business()
    biz["bank"]["holder_name"] = "Someone Else"
    _, review = onboard(client, fake, "SUPPLIER", business=biz)
    assert review["account_status"] == "PENDING_VERIFICATION"
