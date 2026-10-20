"""Phase C: emailed OTP, four-eyes, party roles on approvals, Tier 2 step-up. Approvals are created
through the demo login (as in test_approvals); the decision side is then driven in neon mode with
real accounts, a fake Neon key pair and an in-memory mail outbox."""

import json
import re
import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth import neon
from app.config import get_settings
from app.db.enums import ApprovalAction, ApprovalStatus, MemberRole, Role, UserStatus
from app.db.models import ApprovalEvent, ApprovalRequest, AuditLog, Deal, PartyMember, User
from app.db.session import batch_session
from app.main import create_app
from app.services import approval_otp, mail
from tests.api.deals_support import (
    KARIM,
    RAHIMA,
    as_user,
    current_user_of,
    release,
)
from tests.api.test_approvals import (  # noqa: F401  (autouse fixture + helpers)
    big_deal_approval,
    end_cooling_off,
    fresh_state,
    open_approval,
    rahima_deal_ready,
    status_of,
)
from tests.auth.support import BASE_URL, FakeNeon

pytestmark = pytest.mark.db
CODE_RE = re.compile(r"Your Setu code is (\d{6})")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def outbox() -> Iterator[mail.OutboxSender]:
    box = mail.OutboxSender()
    mail.set_sender(box)
    yield box
    mail.set_sender(None)


_made: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
def retire_members() -> Iterator[None]:
    yield
    with batch_session() as s:
        for uid in _made:
            s.execute(update(User).where(User.id == uid).values(status=UserStatus.SUSPENDED))
            s.execute(update(User).where(User.id == uid).values(party_id=None))
            for row in s.scalars(select(PartyMember).where(PartyMember.user_id == uid)):
                s.delete(row)
    _made.clear()


def add_member(
    party_id: uuid.UUID,
    role: MemberRole,
    *,
    demo: bool = False,
    status: UserStatus = UserStatus.ACTIVE,
) -> tuple[uuid.UUID, str, str]:
    uid, tag = uuid.uuid4(), uuid.uuid4().hex[:8]
    email, sub = f"{role.value.lower()}-{tag}@example.com", f"sub-{tag}"
    with batch_session() as s:
        s.add(
            User(
                id=uid,
                email=email,
                display_name=f"{role.value} {tag}",
                role=Role.BUYER,
                language="en",
                party_id=party_id,
                is_demo=demo,
                status=status,
                auth_subject=None if demo else sub,
            )
        )
        s.flush()
        s.add(PartyMember(id=uuid.uuid4(), party_id=party_id, user_id=uid, member_role=role))
    _made.append(uid)
    return uid, email, sub


def go_neon(monkeypatch: pytest.MonkeyPatch, **env: str) -> tuple[FakeNeon, TestClient]:
    f = FakeNeon()
    monkeypatch.setenv("AUTH_MODE", "neon")
    monkeypatch.setenv("NEON_AUTH_BASE_URL", BASE_URL)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(neon, "_cache", f.cache())
    return f, TestClient(create_app())


def code_of(message: mail.Mail) -> str:
    found = CODE_RE.search(message.text)
    assert found, "no code in the mail"
    return found.group(1)


def approval_row(approval_id: Any) -> ApprovalRequest:
    with batch_session() as s:
        row = s.get(ApprovalRequest, uuid.UUID(str(approval_id)))
        assert row is not None
        s.expunge(row)
        return row


def leaks(code: str, text: str) -> bool:
    return re.search(rf"(?<![0-9a-f]){code}(?![0-9a-f])", text) is not None


def stepup_token(c: TestClient, h: dict[str, str], box: mail.OutboxSender) -> dict[str, str]:
    assert c.post("/auth/stepup/start", headers=h).status_code == 200
    res = c.post("/auth/stepup/verify", json={"code": code_of(box.sent[-1])}, headers=h)
    assert res.status_code == 200, res.text
    return {**h, "X-Stepup": res.json()["token"]}


# --- OTP by email ------------------------------------------------------------------------------


def test_the_code_is_mailed_to_owner_and_finance_only_and_nowhere_else(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _karim, _deal_id, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, owner_mail, owner_sub = add_member(party, MemberRole.OWNER)
    _, fin_mail, _ = add_member(party, MemberRole.FINANCE)
    _, viewer_mail, _ = add_member(party, MemberRole.VIEWER)
    _, gone_mail, _ = add_member(party, MemberRole.FINANCE, status=UserStatus.SUSPENDED)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=owner_sub, email=owner_mail))

    res = c.post(f"/approvals/{appr.id}/resend-otp", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["delivered_by_email"] is True
    recipients = {m.to for m in outbox.sent}
    assert recipients == {owner_mail, fin_mail}  # not the viewer, the suspended or the demo user
    assert viewer_mail not in recipients and gone_mail not in recipients
    code = code_of(outbox.sent[0])
    assert {code_of(m) for m in outbox.sent} == {code}
    assert approval_otp.code_matches(approval_row(appr.id), code)

    m = outbox.sent[0]
    assert "SETU-" in m.subject and "SETU-" in m.text  # the deal reference
    for needle in ("5 minutes", "Never share", "reject the request", "আপনার সেতু কোড", "মিনিট"):
        assert needle in m.text, needle
    assert "Never share" in m.html and "Release a payment tranche" in m.text
    assert "<b>" + code + "</b>" in m.html

    assert not leaks(code, res.text)
    with batch_session() as s:
        payloads = [json.dumps(r.payload) for r in s.scalars(select(AuditLog))]
        events = [
            r.title_en + r.detail_en + r.title_bn + r.detail_bn
            for r in s.scalars(select(ApprovalEvent))
        ]
    assert not any(leaks(code, p) for p in payloads + events)
    assert not leaks(code, c.get(f"/approvals/{appr.id}", headers=h).text)
    assert not leaks(code, c.get("/approvals", headers=h).text)
    assert not leaks(code, c.get("/notifications", headers=h).text)


def test_neon_mode_issues_no_demo_phone_message_for_real_deployments(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _karim, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, owner_mail, owner_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch, DEMO_MODE="false")
    h = bearer(fake.token(sub=owner_sub, email=owner_mail))
    assert c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code == 200
    assert [m.to for m in outbox.sent] == [owner_mail]
    assert c.get("/demo/phone", headers=h).status_code == 404


def test_a_viewer_cannot_decide_or_get_a_code(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, v_mail, v_sub = add_member(party, MemberRole.VIEWER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=v_sub, email=v_mail))
    sent_before = len(outbox.sent)
    card = c.get(f"/approvals/{appr.id}", headers=h)
    assert card.status_code == 200 and card.json()["can_approve"] is False
    for path, body in (
        ("approve", {"otp": "123456"}),
        ("reject", {}),
        ("cancel", None),
        ("resend-otp", None),
    ):
        res = c.post(f"/approvals/{appr.id}/{path}", json=body, headers=h)
        assert res.status_code == 403 and res.json()["code"] == "VIEWER_READ_ONLY", path
    assert len(outbox.sent) == sent_before
    assert status_of(appr.id) == ApprovalStatus.PENDING


def test_a_finance_member_can_approve_with_the_mailed_code(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, f_mail, f_sub = add_member(party, MemberRole.FINANCE)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=f_sub, email=f_mail))
    assert c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code == 200
    code = code_of(outbox.sent[-1])
    wrong = "000000" if code != "000000" else "111111"
    path = f"/approvals/{appr.id}/approve"

    early = c.post(path, json={"otp": code}, headers=h)  # cooling-off is still enforced
    assert early.status_code == 409 and early.json()["code"] == "COOLING_OFF"
    end_cooling_off(appr.id)
    bad = c.post(path, json={"otp": wrong}, headers=h)
    assert bad.status_code == 409 and bad.json()["code"] == "OTP_INVALID"
    ok = c.post(path, json={"otp": code}, headers=h)  # Tier 3: its own OTP, no X-Stepup needed
    assert ok.status_code == 200, ok.text
    assert ok.json()["outcome"] == "EXECUTED"
    assert approval_row(appr.id).status == ApprovalStatus.EXECUTED


def test_three_wrong_codes_still_lock_a_mailed_request(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, o_mail, o_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=o_sub, email=o_mail))
    assert c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code == 200
    code = code_of(outbox.sent[-1])
    wrong = "000000" if code != "000000" else "111111"
    end_cooling_off(appr.id)
    path = f"/approvals/{appr.id}/approve"
    assert c.post(path, json={"otp": wrong}, headers=h).json()["code"] == "OTP_INVALID"
    assert c.post(path, json={"otp": wrong}, headers=h).json()["code"] == "OTP_INVALID"
    assert c.post(path, json={"otp": wrong}, headers=h).json()["code"] == "OTP_LOCKED"
    assert status_of(appr.id) == ApprovalStatus.LOCKED
    assert c.post(path, json={"otp": code}, headers=h).status_code == 409


def test_an_expired_mailed_code_is_refused(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, o_mail, o_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=o_sub, email=o_mail))
    assert c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code == 200
    code = code_of(outbox.sent[-1])
    end_cooling_off(appr.id)
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(otp_expires_at=approval_row(appr.id).created_at - timedelta(hours=1))
        )
    res = c.post(f"/approvals/{appr.id}/approve", json={"otp": code}, headers=h)
    assert res.status_code == 409 and res.json()["code"] == "OTP_EXPIRED"


def test_a_failed_mail_is_a_503_without_the_code_and_the_old_code_stays(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, o_mail, o_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=o_sub, email=o_mail))
    before = approval_row(appr.id).otp_hash
    outbox.fail = True
    res = c.post(f"/approvals/{appr.id}/resend-otp", headers=h)
    assert res.status_code == 503 and "could not send the code" in res.text
    assert not re.search(r"\d{6}", res.json()["detail"])
    assert approval_row(appr.id).otp_hash == before
    outbox.fail = False
    assert c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code == 200
    assert approval_row(appr.id).otp_hash != before


def test_creating_an_approval_survives_a_mail_outage_and_resend_recovers(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    add_member(party, MemberRole.OWNER)
    go_neon(monkeypatch)
    outbox.fail = True
    with batch_session() as s:
        row = s.get(ApprovalRequest, appr.id)
        assert row is not None
        deal = s.get(Deal, row.deal_id)
        ok = approval_otp.issue_otp_quietly(s, row, deal, row.created_at)
    assert ok is False and outbox.sent == []


def test_resend_is_limited_in_neon_mode_too(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    party = current_user_of(KARIM).party_id
    assert party is not None
    _, o_mail, o_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=o_sub, email=o_mail))
    codes = [c.post(f"/approvals/{appr.id}/resend-otp", headers=h).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 409


# --- roles ---------------------------------------------------------------------------------------


def test_supplier_and_other_buyers_still_cannot_decide(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    _, _d, _ms, appr = big_deal_approval()
    other = current_user_of(RAHIMA).party_id
    assert other is not None
    _, o_mail, o_sub = add_member(other, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    h = bearer(fake.token(sub=o_sub, email=o_mail))
    res = c.post(f"/approvals/{appr.id}/approve", json={}, headers=h)
    assert res.status_code in (403, 404)
    assert status_of(appr.id) == ApprovalStatus.PENDING


# --- four-eyes -----------------------------------------------------------------------------------


def rahima_tier2() -> ApprovalRequest:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    status, _ = release(rahima, ms)
    assert status == 202
    return open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)


def second_demo_member(role: MemberRole = MemberRole.FINANCE) -> str:
    party = current_user_of(RAHIMA).party_id
    assert party is not None
    return add_member(party, role, demo=True)[1]


def test_requested_by_is_the_human_who_asked(outbox: mail.OutboxSender) -> None:
    appr = rahima_tier2()
    assert approval_row(appr.id).requested_by_user_id == current_user_of(RAHIMA).id


def test_four_eyes_refuses_the_requester_when_a_colleague_could_approve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUR_EYES_ENFORCE", "true")
    get_settings.cache_clear()
    appr = rahima_tier2()
    colleague = second_demo_member()
    rahima = as_user(RAHIMA)
    res = rahima.post(f"/approvals/{appr.id}/approve", json={})
    assert res.status_code == 403 and res.json()["code"] == "FOUR_EYES"
    assert status_of(appr.id) == ApprovalStatus.PENDING
    # a colleague (not the requester) can approve
    appr2 = rahima_tier2()
    ok = as_user(colleague).post(f"/approvals/{appr2.id}/approve", json={})
    assert ok.status_code == 200, ok.text
    assert approval_row(appr2.id).decided_by_user_id != current_user_of(RAHIMA).id


def test_four_eyes_is_waived_for_a_one_person_company_and_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOUR_EYES_ENFORCE", "true")
    get_settings.cache_clear()
    appr = rahima_tier2()
    sole = as_user(RAHIMA)  # no other OWNER/FINANCE member: the rule must not deadlock
    colleague = second_demo_member(MemberRole.VIEWER)  # a viewer is not an alternative approver
    assert colleague
    res = sole.post(f"/approvals/{appr.id}/approve", json={})
    assert res.status_code == 200, res.text
    with batch_session() as s:
        rows = [
            r
            for r in s.scalars(select(AuditLog).where(AuditLog.action == "APPROVAL_APPROVED"))
            if r.payload.get("approval_id") == str(appr.id)
        ]
    assert len(rows) == 1 and rows[0].payload["four_eyes_waived"] is True


def test_four_eyes_does_not_block_a_non_requester_and_off_is_the_demo_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    assert get_settings().four_eyes_active is False  # demo default: seeded flows unchanged
    appr = rahima_tier2()
    second_demo_member()
    res = as_user(RAHIMA).post(f"/approvals/{appr.id}/approve", json={})
    assert res.status_code == 200, res.text
    with batch_session() as s:
        rows = [
            r
            for r in s.scalars(select(AuditLog).where(AuditLog.action == "APPROVAL_APPROVED"))
            if r.payload.get("approval_id") == str(appr.id)
        ]
    assert "four_eyes_waived" not in rows[0].payload


def test_four_eyes_defaults_on_in_neon_mode_and_can_be_forced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "neon")
    monkeypatch.setenv("NEON_AUTH_BASE_URL", BASE_URL)
    monkeypatch.delenv("FOUR_EYES_ENFORCE", raising=False)
    get_settings.cache_clear()
    assert get_settings().four_eyes_active is True
    monkeypatch.setenv("FOUR_EYES_ENFORCE", "false")
    get_settings.cache_clear()
    assert get_settings().four_eyes_active is False


# --- Tier 2 step-up ---------------------------------------------------------------------------


def test_tier2_approve_needs_a_stepup_token_in_neon_mode(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    appr = rahima_tier2()
    party = current_user_of(RAHIMA).party_id
    assert party is not None
    _, a_mail, a_sub = add_member(party, MemberRole.OWNER)
    _, b_mail, b_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch)
    a = bearer(fake.token(sub=a_sub, email=a_mail))
    b = bearer(fake.token(sub=b_sub, email=b_mail))
    path = f"/approvals/{appr.id}/approve"

    missing = c.post(path, json={}, headers=a)
    assert missing.status_code == 403 and missing.json()["code"] == "STEPUP_REQUIRED"
    junk = c.post(path, json={}, headers={**a, "X-Stepup": "junk"})
    assert junk.status_code == 403 and junk.json()["code"] == "STEPUP_REQUIRED"
    other = stepup_token(c, b, outbox)  # b's valid token is useless for a
    wrong_user = c.post(path, json={}, headers={**a, "X-Stepup": other["X-Stepup"]})
    assert wrong_user.status_code == 403 and wrong_user.json()["code"] == "STEPUP_REQUIRED"
    assert status_of(appr.id) == ApprovalStatus.PENDING

    ok = c.post(path, json={}, headers=stepup_token(c, a, outbox))
    assert ok.status_code == 200, ok.text
    assert ok.json()["outcome"] == "EXECUTED"


def test_tier2_stepup_can_be_switched_off_outside_prod(
    monkeypatch: pytest.MonkeyPatch, outbox: mail.OutboxSender
) -> None:
    appr = rahima_tier2()
    party = current_user_of(RAHIMA).party_id
    assert party is not None
    _, a_mail, a_sub = add_member(party, MemberRole.OWNER)
    fake, c = go_neon(monkeypatch, STEPUP_REQUIRED="false")
    a = bearer(fake.token(sub=a_sub, email=a_mail))
    assert c.post(f"/approvals/{appr.id}/approve", json={}, headers=a).status_code == 200


def test_the_demo_does_not_ask_for_stepup() -> None:
    appr = rahima_tier2()
    assert as_user(RAHIMA).post(f"/approvals/{appr.id}/approve", json={}).status_code == 200
    assert get_settings().stepup_enabled is False
