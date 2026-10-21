"""TOTP through the API: setup, enable, recovery codes, replay, admin activation, step-up."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.models import User
from app.db.session import batch_session
from app.security import crypto, totp
from tests.auth.support import FakeNeon
from tests.onboarding.support import (
    admin_headers,
    audit,
    consent,
    identity,
    must,
    onboard,
    review_id_for,
)

pytestmark = pytest.mark.db


def row(email: str) -> User:
    with batch_session() as s:
        u = s.scalars(select(User).where(User.email == email)).one()
        s.expunge(u)
        return u


def buyer_with_secret(client: TestClient, fake: FakeNeon):
    headers, state = onboard(client, fake, submit=False)
    setup = must(client.post("/auth/mfa/totp/setup", headers=headers))
    return headers, state["email"], setup["secret"], setup


def test_setup_returns_the_secret_once_and_stores_it_encrypted(
    client: TestClient, fake: FakeNeon
) -> None:
    _, email, secret, setup = buyer_with_secret(client, fake)
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and secret in setup["otpauth_uri"]
    u = row(email)
    assert u.mfa_enabled is False and u.mfa_secret_encrypted
    assert secret.encode() not in bytes(u.mfa_secret_encrypted)
    assert crypto.decrypt_text(u.mfa_secret_encrypted) == secret


def test_enable_checks_the_code_and_returns_ten_recovery_codes_once(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, email, secret, _ = buyer_with_secret(client, fake)
    wrong = client.post("/auth/mfa/totp/enable", json={"code": "000000"}, headers=headers)
    assert wrong.status_code == 400 and wrong.json()["code"] == "MFA_INVALID_CODE"
    code = totp.code_at(secret, totp.current_step())
    out = must(client.post("/auth/mfa/totp/enable", json={"code": code}, headers=headers))
    assert out["mfa_enabled"] is True and len(out["recovery_codes"]) == 10
    u = row(email)
    assert u.mfa_enabled and len(u.mfa_recovery_hashes or []) == 10
    assert not set(out["recovery_codes"]) & set(u.mfa_recovery_hashes or [])  # hashed
    assert all(h.isalnum() and len(h) == 64 for h in u.mfa_recovery_hashes or [])
    assert [r.action for r in audit("auth.mfa_enabled")][-1] == "auth.mfa_enabled"
    again = client.post("/auth/mfa/totp/setup", headers=headers)
    assert again.status_code == 409 and again.json()["code"] == "MFA_ALREADY_ENABLED"
    assert must(client.get("/auth/me", headers=headers))["mfa_enabled"] is True


def test_a_used_code_cannot_be_replayed(client: TestClient, fake: FakeNeon) -> None:
    headers, _, secret, _ = buyer_with_secret(client, fake)
    code = totp.code_at(secret, totp.current_step())
    must(client.post("/auth/mfa/totp/enable", json={"code": code}, headers=headers))
    replay = client.post(
        "/auth/mfa/totp/recovery-codes/regenerate", json={"code": code}, headers=headers
    )
    assert replay.status_code == 400 and replay.json()["code"] == "MFA_INVALID_CODE"
    fresh = totp.code_at(secret, totp.current_step() + 1)  # next step: inside the window
    assert (
        len(
            must(
                client.post(
                    "/auth/mfa/totp/recovery-codes/regenerate",
                    json={"code": fresh},
                    headers=headers,
                )
            )["recovery_codes"]
        )
        == 10
    )


def test_recovery_codes_work_once_and_regeneration_replaces_them(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, email, secret, _ = buyer_with_secret(client, fake)
    codes = must(
        client.post(
            "/auth/mfa/totp/enable",
            json={"code": totp.code_at(secret, totp.current_step())},
            headers=headers,
        )
    )["recovery_codes"]
    new = must(
        client.post(
            "/auth/mfa/totp/recovery-codes/regenerate", json={"code": codes[0]}, headers=headers
        )
    )["recovery_codes"]
    assert set(new).isdisjoint(codes)
    spent = client.post(
        "/auth/mfa/totp/recovery-codes/regenerate", json={"code": codes[0]}, headers=headers
    )
    assert spent.status_code == 400  # the old list is gone, including the code just used
    assert len(row(email).mfa_recovery_hashes or []) == 10


def test_a_buyer_can_turn_it_off_with_a_code_an_admin_cannot(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, email, secret, _ = buyer_with_secret(client, fake)
    codes = must(
        client.post(
            "/auth/mfa/totp/enable",
            json={"code": totp.code_at(secret, totp.current_step())},
            headers=headers,
        )
    )["recovery_codes"]
    bad = client.post("/auth/mfa/totp/disable", json={"code": "ABCDE-FGHJK"}, headers=headers)
    assert bad.status_code == 400
    assert must(
        client.post("/auth/mfa/totp/disable", json={"code": codes[1]}, headers=headers)
    ) == {"mfa_enabled": False}
    u = row(email)
    assert not u.mfa_enabled and u.mfa_secret_encrypted is None and u.mfa_recovery_hashes is None
    assert audit("auth.mfa_disabled")
    _, admin = admin_headers(fake)
    res = client.post("/auth/mfa/totp/disable", json={"code": "123456"}, headers=admin)
    assert res.status_code == 403 and res.json()["code"] == "MFA_REQUIRED"


def test_enable_without_setup_and_demo_users_are_refused(
    client: TestClient, fake: FakeNeon
) -> None:
    headers, _, _ = identity(fake)
    must(client.post("/onboarding/role", json={"role": "BUYER"}, headers=headers))
    res = client.post("/auth/mfa/totp/enable", json={"code": "123456"}, headers=headers)
    assert res.status_code == 400 and res.json()["code"] == "MFA_NOT_STARTED"
    assert client.post("/auth/mfa/totp/setup").status_code == 401


def test_allowlisted_admin_becomes_active_only_with_totp_and_consent(
    client: TestClient, fake: FakeNeon, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAIL_ALLOWLIST", "chief@example.com")
    get_settings.cache_clear()
    h, email, _ = identity(fake, email="chief@example.com")
    state = must(client.post("/onboarding/role", json={"role": "ADMIN"}, headers=h))
    assert state["account_status"] == "PENDING_PROFILE"
    assert client.get("/admin/onboarding", headers=h).status_code == 403  # not ACTIVE, no TOTP
    early = client.post("/onboarding/submit", headers=h)
    assert early.status_code == 422 and early.json()["code"] == "MFA_REQUIRED"
    secret = must(client.post("/auth/mfa/totp/setup", headers=h))["secret"]
    must(
        client.post(
            "/auth/mfa/totp/enable",
            json={"code": totp.code_at(secret, totp.current_step())},
            headers=h,
        )
    )
    assert row(email).mfa_enabled and row(email).status.value == "PENDING_PROFILE"  # no consent yet
    done = consent(client, h)
    assert done["account_status"] == "ACTIVE" and done["mfa"] == {"enabled": True, "required": True}
    assert must(client.get("/admin/onboarding", headers=h)) is not None
    assert must(client.post("/onboarding/submit", headers=h))["account_status"] == "ACTIVE"


def test_stepup_accepts_totp_and_recovery_codes_but_not_a_replayed_one(
    client: TestClient, fake: FakeNeon, mail_box, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEPUP_REQUIRED", "true")
    get_settings.cache_clear()
    monkeypatch.setenv("ADMIN_EMAIL_ALLOWLIST", "second@example.com")
    get_settings.cache_clear()
    h, _, _ = identity(fake, email="second@example.com")
    must(client.post("/onboarding/role", json={"role": "ADMIN"}, headers=h))
    secret = must(client.post("/auth/mfa/totp/setup", headers=h))["secret"]
    step = totp.current_step()
    codes = must(
        client.post("/auth/mfa/totp/enable", json={"code": totp.code_at(secret, step)}, headers=h)
    )["recovery_codes"]
    consent(client, h)
    _, _applicant = onboard(client, fake)
    rid = review_id_for(client, h, _applicant["email"])
    assert (
        client.post(f"/admin/onboarding/{rid}/approve", headers=h).json()["code"]
        == "STEPUP_REQUIRED"
    )
    replay = client.post(
        "/auth/stepup/verify", json={"code": totp.code_at(secret, step)}, headers=h
    )
    assert replay.status_code == 400  # that step was spent by `enable`; no email code is pending
    tok = must(
        client.post("/auth/stepup/verify", json={"code": totp.code_at(secret, step + 1)}, headers=h)
    )["token"]
    ok = client.post(f"/admin/onboarding/{rid}/approve", headers={**h, "X-Stepup": tok})
    assert ok.status_code == 200, ok.text
    rec = must(client.post("/auth/stepup/verify", json={"code": codes[0]}, headers=h))
    assert rec["token"]
    spent = client.post("/auth/stepup/verify", json={"code": codes[0]}, headers=h)
    assert spent.status_code == 400
    assert not any("Your Setu code" in m.text for m in mail_box.sent)  # no emailed code needed


def test_totp_attempts_are_rate_limited(client: TestClient, fake: FakeNeon) -> None:
    headers, _, _, _ = buyer_with_secret(client, fake)
    codes = [
        client.post("/auth/mfa/totp/enable", json={"code": "000000"}, headers=headers).status_code
        for _ in range(12)
    ]
    assert codes[0] == 400 and 429 in codes
