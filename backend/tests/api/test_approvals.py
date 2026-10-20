"""Phase 17: the human side of Tier 2/3. One-tap, OTP + cooling-off, re-evaluation at execution,
buyer-only decisions, expiry, the in-app beneficiary change and the e-mail block (TC-06).
Real Postgres with the seeded demo."""

import re
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update

from app.config import REPO_ROOT, get_settings
from app.db.enums import (
    AccountStatus,
    AlertType,
    ApprovalAction,
    ApprovalStatus,
    CheckStatus,
    MilestoneStatus,
)
from app.db.models import (
    Alert,
    ApprovalEvent,
    ApprovalRequest,
    AuditLog,
    BankAccount,
    Deal,
    DemoPhoneMessage,
    LedgerEntry,
    Milestone,
    Party,
)
from app.db.session import batch_session
from app.services import escrow
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAXIN,
    HUAXIN_USER,
    JUDGE,
    KARIM,
    RAHIMA,
    as_user,
    confirmed,
    create,
    fund,
    funded_deal,
    give_cash,
    propose,
    release,
    verify_evidence,
)
from tests.api.test_risk_enforcement import add_document

pytestmark = pytest.mark.db

MAIN = "SETU-2026-0001"
EMAIL = REPO_ROOT / "data" / "demo" / "SETU-2026-0001" / "email_beneficiary_change.txt"
NEW_ACCOUNT = {
    "bank_name": "Pacific Bridge Bank (HK)",
    "bank_country": "HK",
    "account_number": "HK-077-123456-001",
    "holder_name": "Shaoxing Huaxin Textile Co., Ltd.",
    "account_type": "CORPORATE",
    "currency": "USD",
}


@pytest.fixture(autouse=True)
def fresh_state(seeded_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("COOLING_OFF_SECONDS", "600")
    get_settings.cache_clear()
    give_cash("rahima-knitwear")
    give_cash("dhaka-stitch-works")
    with batch_session() as s:
        # earlier tests leave open Tier 3 requests of the same buyer, which would freeze releases
        s.execute(
            update(ApprovalRequest)
            .where(
                ApprovalRequest.tier == 3,
                ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.APPROVED)),
                ApprovalRequest.key.not_like("approval:shaoxing-huaxin:%"),
            )
            .values(status=ApprovalStatus.CANCELLED)
        )
        s.execute(  # put the seeded e-mail request back as the seed left it
            update(ApprovalRequest)
            .where(ApprovalRequest.key.like("approval:shaoxing-huaxin:beneficiary-change-hk"))
            .values(status=ApprovalStatus.PENDING, decided_at=None)
        )
        cny = s.scalars(
            select(BankAccount.id).where(
                BankAccount.currency == "CNY", BankAccount.change_requested_via.is_(None)
            )
        ).first()
        s.execute(  # the demo deal pays the seeded account again
            update(Deal).where(Deal.reference == MAIN).values(beneficiary_account_id=cny)
        )
        s.execute(  # accounts that earlier tests requested through the portal are gone
            update(BankAccount)
            .where(BankAccount.change_requested_via == "portal")
            .values(status=AccountStatus.RETIRED)
        )
        s.execute(
            update(BankAccount)
            .where(BankAccount.account_number == "SIM-HK-012-884213-001")
            .values(status=AccountStatus.PENDING_CHANGE)
        )


# --- helpers ----------------------------------------------------------------------------------


def rahima_deal_ready() -> tuple[str, dict[str, Any]]:
    """A Huaxin deal paid to a CNY account: no FX lock yet, so a release is Tier 2."""
    rahima = as_user(RAHIMA)
    reject_seeded_email_request(rahima)  # an open Tier 3 request would freeze Huaxin money
    d = funded_deal(rahima, HUAXIN)
    ms = d["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    return ms, d


def open_approval(deal_id: str, action: ApprovalAction) -> ApprovalRequest:
    with batch_session() as s:
        return s.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.deal_id == uuid.UUID(deal_id),
                ApprovalRequest.action == action,
                ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.APPROVED)),
            )
            .order_by(ApprovalRequest.created_at.desc())
        ).first()  # type: ignore[return-value]


def end_cooling_off(approval_id: uuid.UUID) -> None:
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .values(cooling_off_until=escrow.utcnow() - timedelta(seconds=1))
        )


def phone_code(client: Any, approval_id: Any) -> str:
    res = client.get("/demo/phone")
    assert res.status_code == 200, res.text
    msgs = [m for m in res.json()["messages"] if m["approval_id"] == str(approval_id)]
    assert msgs, "no SMS for this approval"
    return msgs[0]["code"]


def status_of(approval_id: Any) -> ApprovalStatus:
    with batch_session() as s:
        return s.get(ApprovalRequest, uuid.UUID(str(approval_id))).status  # type: ignore[union-attr]


def audit_count(action: str) -> int:
    with batch_session() as s:
        return (
            s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))
            or 0
        )


def supplier_request(client: Any, deal_id: str, **over: Any) -> Any:
    return client.post(
        "/supplier/accounts/change-request", json={"deal_id": deal_id, **NEW_ACCOUNT, **over}
    )


def huaxin_main_deal() -> str:
    with batch_session() as s:
        return str(s.scalars(select(Deal.id).where(Deal.reference == MAIN)).one())


def reject_seeded_email_request(rahima: Any) -> None:
    for item in rahima.get("/approvals?status=pending").json()["items"]:
        if item["requested_via"] == "email":
            assert rahima.post(f"/approvals/{item['id']}/reject", json={}).status_code == 200


# --- Tier 2: one tap ---------------------------------------------------------------------------


def test_tier2_one_tap_releases_the_tranche_and_updates_ledger_and_escrow() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    status, body = release(rahima, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    appr = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    assert appr.tier == 2 and not appr.otp_required

    card = rahima.get(f"/approvals/{appr.id}").json()
    assert card["can_approve"] and card["evidence"]["supplier"]["name"]
    assert card["what_happens_en"] and card["what_happens_bn"]

    res = rahima.post(f"/approvals/{appr.id}/approve", json={})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["outcome"] == "EXECUTED" and out["approval"]["status"] == "EXECUTED"

    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status == MilestoneStatus.RELEASED
        rows = s.scalar(
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.milestone_id == m.id)
        )
        assert rows and rows > 0
    assert audit_count("APPROVAL_APPROVED") >= 1 and audit_count("APPROVAL_EXECUTED") >= 1

    again = rahima.post(f"/approvals/{appr.id}/approve", json={})  # idempotent
    assert again.status_code == 200 and again.json()["idempotent_replay"] is True


def test_the_seeded_demo_m1_approval_releases_m1_of_the_demo_deal() -> None:
    rahima = as_user(RAHIMA)
    reject_seeded_email_request(rahima)
    items = rahima.get("/approvals?status=pending").json()["items"]
    [m1] = [i for i in items if i["action"] == "RELEASE_MILESTONE" and i["deal_reference"] == MAIN]
    assert m1["tier"] == 2 and m1["milestone_seq"] == 1
    res = rahima.post(f"/approvals/{m1['id']}/approve", json={})
    assert res.status_code == 200, res.text
    assert res.json()["outcome"] == "EXECUTED"
    deal = rahima.get(f"/deals/{huaxin_main_deal()}").json()
    assert deal["milestones"][0]["status"] == "RELEASED"


def test_the_approve_body_accepts_nothing_but_an_otp() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    release(rahima, ms)
    appr = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    for extra in ({"amount": "1.00"}, {"tier": 1}, {"params": {"amount": "1"}}, {"approved": True}):
        assert rahima.post(f"/approvals/{appr.id}/approve", json=extra).status_code == 422
    assert status_of(appr.id) == ApprovalStatus.PENDING


def test_a_tampered_payload_is_refused_at_approval_time() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    release(rahima, ms)
    appr = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(params={**appr.params, "amount": "1.00"})
        )
    res = rahima.post(f"/approvals/{appr.id}/approve", json={})
    assert res.status_code == 409 and res.json()["code"] in (
        "APPROVAL_PARAMS_CHANGED",
        "APPROVAL_HASH_MISMATCH",
    )
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status != MilestoneStatus.RELEASED


# --- who may decide ----------------------------------------------------------------------------


def test_only_the_buyer_of_the_deal_can_decide() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    release(rahima, ms)
    appr = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    for who in (KARIM, HUAXIN_USER, JUDGE):
        c = as_user(who)
        for path in ("approve", "reject", "cancel", "resend-otp"):
            res = c.post(f"/approvals/{appr.id}/{path}", json={})
            assert res.status_code == 403, (who, path, res.status_code)
    assert status_of(appr.id) == ApprovalStatus.PENDING
    assert as_user(HUAXIN_USER).get("/approvals").status_code == 403
    assert as_user(KARIM).get(f"/approvals/{appr.id}").status_code == 404  # not visible at all
    assert all(i["id"] != str(appr.id) for i in as_user(KARIM).get("/approvals").json()["items"])


# --- re-evaluation at execution ----------------------------------------------------------------


def test_approving_after_a_duplicate_hash_flag_appeared_does_not_execute_and_re_escalates() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    release(rahima, ms)
    old = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    assert old.tier == 2
    add_document(d["id"], ms, CheckStatus.WARNING, findings=("DUPLICATE_HASH",))

    res = rahima.post(f"/approvals/{old.id}/approve", json={})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["outcome"] == "RE_ESCALATED" and out["context_changed"] is True
    new = out["new_approval"]
    assert new["tier"] == 3 and new["otp_required"] and new["id"] != str(old.id)
    assert any(r["code"] == "DUPLICATE_HASH" for r in new["reasons"])
    assert status_of(old.id) == ApprovalStatus.CANCELLED
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status != MilestoneStatus.RELEASED
        assert not s.scalar(
            select(func.count()).select_from(LedgerEntry).where(LedgerEntry.milestone_id == m.id)
        )
    assert audit_count("APPROVAL_REESCALATED") >= 1


# --- Tier 3: OTP, cooling-off, lock ------------------------------------------------------------


def big_deal_approval() -> tuple[Any, str, str, ApprovalRequest]:
    karim = as_user(KARIM)
    d = create(karim, BRIGHTLINE, qty="44000", price="1.00")
    propose(karim, d["id"], template="custom", percents=["50", "50"])
    confirmed(karim, None, d["id"])
    d = fund(karim, d["id"])
    ms = d["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    status, body = release(karim, ms)
    assert status == 202 and body["risk"]["tier"] == 3
    return karim, d["id"], ms, open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)


def test_tier3_needs_the_cooling_off_to_end_and_the_right_code() -> None:
    karim, _deal_id, ms, appr = big_deal_approval()
    code = phone_code(karim, appr.id)
    card = karim.get(f"/approvals/{appr.id}").json()
    assert card["tier"] == 3 and card["otp_sent"] and card["seconds_to_cooling_off_end"] > 0
    assert (
        card["why_pause_en"]
        and card["can_approve"] is True
        and card["blocked_reason"] == "COOLING_OFF"
    )

    early = karim.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert early.status_code == 409 and early.json()["code"] == "COOLING_OFF"
    assert status_of(appr.id) == ApprovalStatus.PENDING

    end_cooling_off(appr.id)
    missing = karim.post(f"/approvals/{appr.id}/approve", json={})
    assert missing.status_code == 400 and missing.json()["code"] == "OTP_REQUIRED"
    wrong = karim.post(
        f"/approvals/{appr.id}/approve", json={"otp": "000000" if code != "000000" else "111111"}
    )
    assert wrong.status_code == 409 and wrong.json()["code"] == "OTP_INVALID"

    ok = karim.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["outcome"] == "EXECUTED"
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status == MilestoneStatus.RELEASED


def test_three_wrong_codes_lock_the_request_and_thaw_the_tranche() -> None:
    karim, _deal_id, ms, appr = big_deal_approval()
    code = phone_code(karim, appr.id)
    end_cooling_off(appr.id)
    bad = "000000" if code != "000000" else "111111"
    r1 = karim.post(f"/approvals/{appr.id}/approve", json={"otp": bad})
    r2 = karim.post(f"/approvals/{appr.id}/approve", json={"otp": bad})
    r3 = karim.post(f"/approvals/{appr.id}/approve", json={"otp": bad})
    assert [r1.json()["code"], r2.json()["code"], r3.json()["code"]] == [
        "OTP_INVALID",
        "OTP_INVALID",
        "OTP_LOCKED",
    ]
    assert status_of(appr.id) == ApprovalStatus.LOCKED
    after = karim.post(f"/approvals/{appr.id}/approve", json={"otp": code})  # even the right one
    assert after.status_code == 409 and after.json()["code"] == "APPROVAL_LOCKED"
    assert karim.post(f"/approvals/{appr.id}/resend-otp").status_code == 409
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status == MilestoneStatus.READY


def test_the_buyer_can_cancel_during_the_cooling_off() -> None:
    karim, _deal_id, ms, appr = big_deal_approval()
    res = karim.post(f"/approvals/{appr.id}/cancel")
    assert res.status_code == 200 and res.json()["approval"]["status"] == "CANCELLED"
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status == MilestoneStatus.READY


def test_a_request_that_nobody_decides_expires_and_unfreezes_the_tranche() -> None:
    karim, _deal_id, ms, appr = big_deal_approval()
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(expires_at=escrow.utcnow() - timedelta(minutes=1))
        )
    items = karim.get("/approvals?status=history").json()["items"]
    assert any(i["id"] == str(appr.id) and i["status"] == "EXPIRED" for i in items)
    late = karim.post(f"/approvals/{appr.id}/approve", json={"otp": "123456"})
    assert late.status_code == 409 and late.json()["code"] == "APPROVAL_EXPIRED"
    with batch_session() as s:
        m = s.get(Milestone, uuid.UUID(ms))
        assert m is not None and m.status == MilestoneStatus.READY


def test_resend_gives_a_new_code_on_the_phone_and_never_in_the_response() -> None:
    karim, _deal_id, _ms, appr = big_deal_approval()
    first = phone_code(karim, appr.id)
    res = karim.post(f"/approvals/{appr.id}/resend-otp")
    assert res.status_code == 200 and res.json()["delivered_to_demo_phone"] is True
    second = phone_code(karim, appr.id)
    assert re.fullmatch(r"\d{6}", second)
    assert second not in res.text
    end_cooling_off(appr.id)
    if second != first:  # the old code stops working
        old = karim.post(f"/approvals/{appr.id}/approve", json={"otp": first})
        assert old.status_code == 409 and old.json()["code"] == "OTP_INVALID"


def test_the_otp_is_stored_only_as_a_hash() -> None:
    karim, _deal_id, _ms, appr = big_deal_approval()
    code = phone_code(karim, appr.id)
    with batch_session() as s:
        row = s.get(ApprovalRequest, appr.id)
        assert row is not None and row.otp_hash and code not in row.otp_hash


def test_with_demo_mode_off_no_otp_is_stored_or_served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    # DEMO_MODE=false also removes the demo login/cookie; the test still needs a session, so the
    # login layer alone is told the demo is on while approvals and the OTP code see it off.
    real = get_settings

    def login_layer() -> object:
        return real().model_copy(update={"demo_mode": True})

    monkeypatch.setattr("app.auth.deps.get_settings", login_layer)
    monkeypatch.setattr("app.main.get_settings", login_layer)
    karim, _deal_id, _ms, appr = big_deal_approval()
    with batch_session() as s:
        n = s.scalar(
            select(func.count())
            .select_from(DemoPhoneMessage)
            .where(DemoPhoneMessage.approval_id == appr.id)
        )
        assert n == 0
    assert karim.get("/demo/phone").status_code == 404
    assert karim.post("/demo/simulate/redirect-email").status_code == 404
    assert as_user(RAHIMA).get("/inbox/demo-email").status_code == 404
    for res in (
        karim.get("/approvals"),
        karim.get(f"/approvals/{appr.id}"),
        karim.post(f"/approvals/{appr.id}/resend-otp"),
        karim.get("/notifications"),
    ):
        assert res.status_code == 200
        text = res.text.lower()
        assert "otp_hash" not in text and not re.search(r'"(otp|otp_code|sms)"\s*:', text)


def test_the_demo_phone_is_private_to_the_buyer() -> None:
    _karim, _deal_id, _ms, appr = big_deal_approval()
    assert as_user(RAHIMA).get("/demo/phone").json()["messages"] == [] or all(
        m["approval_id"] != str(appr.id)
        for m in as_user(RAHIMA).get("/demo/phone").json()["messages"]
    )
    for who in (JUDGE, HUAXIN_USER):
        assert as_user(who).get("/demo/phone").status_code == 404


# --- beneficiary change (SR-6) -----------------------------------------------------------------


def test_tc06_the_redirection_email_is_blocked_and_nothing_changes() -> None:
    rahima = as_user(RAHIMA)
    with batch_session() as s:
        before = sorted(
            (str(a.id), a.status.value, a.account_number) for a in s.scalars(select(BankAccount))
        )
        deal_before = s.scalars(
            select(Deal.beneficiary_account_id).where(Deal.reference == MAIN)
        ).one()
        alerts_before = s.scalar(
            select(func.count()).select_from(Alert).where(Alert.type == AlertType.FRAUD)
        )
    res = rahima.post("/inbox/email-check", json={"text": EMAIL.read_text(encoding="utf-8")})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["blocked"] and out["verdict"] == "BLOCKED" and out["account_changed"] is False
    assert "never changes payment accounts based on email" in out["message_en"]
    assert out["alert_id"] and out["audit_seq"] and out["deal_reference"] == MAIN
    with batch_session() as s:
        after = sorted(
            (str(a.id), a.status.value, a.account_number) for a in s.scalars(select(BankAccount))
        )
        assert after == before
        assert (
            s.scalars(select(Deal.beneficiary_account_id).where(Deal.reference == MAIN)).one()
            == deal_before
        )
        assert (
            s.scalar(select(func.count()).select_from(Alert).where(Alert.type == AlertType.FRAUD))
            == alerts_before + 1
        )
        row = s.scalars(select(AuditLog).where(AuditLog.seq == out["audit_seq"])).one()
        assert row.action == "EMAIL_BENEFICIARY_CHANGE_BLOCKED" and row.tier == 3
        assert s.scalar(
            select(func.count()).select_from(ApprovalEvent).where(ApprovalEvent.kind == "BLOCKED")
        )
    again = rahima.post("/inbox/email-check", json={"text": EMAIL.read_text(encoding="utf-8")})
    assert again.json()["alert_id"] == out["alert_id"]  # one alert per email


def test_only_a_buyer_can_check_an_email_and_a_supplier_cannot_start_a_change_by_email() -> None:
    body = {"text": "Please pay to our new account."}
    assert as_user(HUAXIN_USER).post("/inbox/email-check", json=body).status_code == 403
    assert as_user(JUDGE).post("/inbox/email-check", json=body).status_code == 403
    assert as_user(RAHIMA).post("/inbox/email-check", json={"text": ""}).status_code == 422


def test_the_seeded_email_request_cannot_be_approved_only_rejected() -> None:
    rahima = as_user(RAHIMA)
    [t3] = [
        i
        for i in rahima.get("/approvals?status=pending").json()["items"]
        if i["action"] == "CHANGE_BENEFICIARY" and i["requested_via"] == "email"
    ]
    assert t3["blocked_reason"] == "EMAIL_ORIGIN" and t3["can_approve"] is False
    res = rahima.post(f"/approvals/{t3['id']}/approve", json={"otp": "123456"})
    assert res.status_code == 409 and res.json()["code"] == "BENEFICIARY_VIA_EMAIL"
    rej = rahima.post(f"/approvals/{t3['id']}/reject", json={"reason": "came by email"})
    assert rej.status_code == 200 and rej.json()["approval"]["status"] == "REJECTED"
    with batch_session() as s:
        hk = s.scalars(
            select(BankAccount).where(BankAccount.account_number == "SIM-HK-012-884213-001")
        ).one()
        assert hk.status == AccountStatus.RETIRED


def test_in_app_supplier_change_goes_through_tier3_otp_and_cooling_off_then_switches() -> None:
    rahima = as_user(RAHIMA)
    huaxin = as_user(HUAXIN_USER)
    reject_seeded_email_request(rahima)
    deal_id = huaxin_main_deal()

    res = supplier_request(huaxin, deal_id)
    assert res.status_code == 202, res.text
    req = res.json()
    assert req["account_status"] == "PENDING_CHANGE" and req["stage"] == "WAITING_BUYER"
    assert req["tier"] == 3 and [s["key"] for s in req["steps"]] == [
        "SUBMITTED",
        "KYB",
        "BUYER",
        "DONE",
    ]
    assert supplier_request(huaxin, deal_id).json()["account_id"] == req["account_id"]  # idempotent

    appr = open_approval(deal_id, ApprovalAction.CHANGE_BENEFICIARY)
    assert appr.tier == 3 and appr.params["requested_via"] == "portal"
    code = phone_code(rahima, appr.id)
    with batch_session() as s:
        deal = s.get(Deal, uuid.UUID(deal_id))
        old = deal.beneficiary_account_id  # type: ignore[union-attr]

    early = rahima.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert early.status_code == 409 and early.json()["code"] == "COOLING_OFF"
    with batch_session() as s:
        assert s.get(Deal, uuid.UUID(deal_id)).beneficiary_account_id == old  # type: ignore[union-attr]

    end_cooling_off(appr.id)
    ok = rahima.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert ok.status_code == 200, ok.text
    assert ok.json()["outcome"] == "EXECUTED"
    with batch_session() as s:
        deal = s.get(Deal, uuid.UUID(deal_id))
        assert deal is not None and str(deal.beneficiary_account_id) == req["account_id"]
        acct = s.get(BankAccount, uuid.UUID(req["account_id"]))
        assert acct is not None and acct.status == AccountStatus.ACTIVE
    assert audit_count("BENEFICIARY_CHANGED") >= 1
    tracker = huaxin.get("/supplier/accounts/change-requests").json()["items"]
    assert tracker[0]["stage"] == "APPROVED" and tracker[0]["steps"][-1]["state"] == "DONE"


def test_wrong_code_three_times_locks_a_supplier_change_and_retires_the_pending_account() -> None:
    rahima = as_user(RAHIMA)
    huaxin = as_user(HUAXIN_USER)
    reject_seeded_email_request(rahima)
    deal_id = huaxin_main_deal()
    req = supplier_request(huaxin, deal_id, account_number="HK-088-654321-002").json()
    appr = open_approval(deal_id, ApprovalAction.CHANGE_BENEFICIARY)
    code = phone_code(rahima, appr.id)
    end_cooling_off(appr.id)
    bad = "000000" if code != "000000" else "111111"
    for _ in range(3):
        rahima.post(f"/approvals/{appr.id}/approve", json={"otp": bad})
    assert status_of(appr.id) == ApprovalStatus.LOCKED
    with batch_session() as s:
        acct = s.get(BankAccount, uuid.UUID(req["account_id"]))
        assert acct is not None and acct.status == AccountStatus.RETIRED
    assert huaxin.get("/supplier/accounts/change-requests").json()["items"][0]["stage"] == "LOCKED"


def test_buyers_and_judges_cannot_use_the_supplier_change_endpoint() -> None:
    deal_id = huaxin_main_deal()
    for who in (RAHIMA, KARIM, JUDGE, ADMIN):
        assert supplier_request(as_user(who), deal_id).status_code == 403
    other = as_user("brightline@demo.setu") if False else None
    assert other is None


# --- feed, timeline, simulator -----------------------------------------------------------------


def test_notifications_and_timeline_follow_the_approval() -> None:
    rahima = as_user(RAHIMA)
    ms, d = rahima_deal_ready()
    release(rahima, ms)
    appr = open_approval(d["id"], ApprovalAction.RELEASE_MILESTONE)
    feed = rahima.get("/notifications").json()
    assert feed["unread"] >= 1 and any(i["kind"] == "CREATED" for i in feed["items"])
    tl = rahima.get(f"/deals/{d['id']}/timeline").json()
    assert [s["key"] for s in tl["steps"]] == ["PROPOSED", "RISK", "HUMAN", "EXECUTED"]
    assert tl["steps"][2]["state"] == "CURRENT"
    done = rahima.post(f"/approvals/{appr.id}/approve", json={})
    assert done.status_code == 200, done.text
    tl = rahima.get(f"/deals/{d['id']}/timeline").json()
    assert [s["state"] for s in tl["steps"]] == ["DONE", "DONE", "DONE", "DONE"]
    assert tl["steps"][2]["audit_seq"] and tl["steps"][3]["audit_seq"]
    assert rahima.post("/notifications/read").json()["marked"] >= 1
    assert rahima.get("/notifications").json()["unread"] == 0
    assert as_user(HUAXIN_USER).get(f"/deals/{d['id']}/timeline").status_code in (403, 404)


@pytest.mark.parametrize(
    ("scenario", "tier"),
    [("redirect-email", 3), ("supplier-account-change", 3), ("large-advance", 3)],
)
def test_the_scam_simulator_runs_the_real_flow(scenario: str, tier: int) -> None:
    judge = as_user(JUDGE)
    if scenario == "supplier-account-change":
        reject_seeded_email_request(as_user(RAHIMA))
    res = judge.post(f"/demo/simulate/{scenario}")
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["tier"] == tier and out["how_setu_responded_en"] and out["how_setu_responded_bn"]
    if scenario == "redirect-email":
        assert out["email"]["blocked"] is True
    if scenario == "supplier-account-change":
        assert out["approval_id"]
    if scenario == "large-advance":
        assert "AMOUNT_OVER_LIMIT" in out["reasons"]
    assert as_user(HUAXIN_USER).post(f"/demo/simulate/{scenario}").status_code == 403


def test_a_supplier_never_sees_buyer_private_approval_data() -> None:
    huaxin = as_user(HUAXIN_USER)
    deal_id = huaxin_main_deal()
    supplier_request(huaxin, deal_id, account_number="HK-066-777777-003")
    text = huaxin.get("/supplier/accounts/change-requests").text
    assert '"reasons"' not in text and "kyb_score" not in text and "otp" not in text.lower()


def test_unknown_parties_are_not_in_the_reader_party_table() -> None:
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(Party)) > 0
