"""Demo-flow coverage: drive the real flows (HTTP + services) in ONE seeded database, then check
that every action type a judge expects is in the signed log with the right tier and actor, that
the whole chain verifies and that no identifier survived masking in any row."""

# ruff: noqa: F811  (pytest fixtures imported by name)

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agent.registry import ToolContext, default_registry
from app.audit.export import line_of
from app.audit.keys import load_signing_key
from app.audit.verify import verify_lines
from app.config import REPO_ROOT, get_settings
from app.db.enums import ApprovalAction
from app.db.models import ApprovalRequest, AuditLog
from app.db.session import batch_session, get_engine
from app.privacy.gateway import CallRecord, PrivacyGateway, Stats
from app.privacy.records import persist_calls
from app.services import escrow
from seed.cli import seed
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.api.deals_support import (
    ADMIN,
    HUAXIN,
    HUAXIN_USER,
    RAHIMA,
    as_user,
    create,
    current_user_of,
    funded_deal,
    give_cash,
    party_id,
    propose,
    release,
    verify_evidence,
)
from tests.api.test_approvals import (
    big_deal_approval,
    end_cooling_off,
    huaxin_main_deal,
    open_approval,
    phone_code,
    reject_seeded_email_request,
    supplier_request,
)
from tests.audit.support import has_float, pii_hits
from tests.documents.support import DEAL as MAIN
from tests.documents.support import invoice_lines, upload
from tests.forensics.support import make_pdf

pytestmark = pytest.mark.db

EMAIL = REPO_ROOT / "data" / "demo" / "SETU-2026-0001" / "email_beneficiary_change.txt"


def approvals_of(deal_id: str, action: ApprovalAction) -> list[ApprovalRequest]:
    with batch_session() as s:
        return list(
            s.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.deal_id == uuid.UUID(deal_id), ApprovalRequest.action == action
                )
            )
        )


def run_flow(tmp: Path) -> dict[str, Any]:
    seed(reset=True)  # DEMO_RESET is entry 1 of the chain
    give_cash("rahima-knitwear")
    give_cash("dhaka-stitch-works")
    out: dict[str, Any] = {}
    admin, rahima = as_user(ADMIN), as_user(RAHIMA)

    # KYB
    sid = party_id(HUAXIN)
    res = admin.post(f"/kyb/verify/{sid}", params={"deal_id": MAIN})
    assert res.status_code == 200, res.text

    # documents: the forged B/L (hidden instruction) on the demo deal
    res = upload(rahima, MAIN, "BILL_OF_LADING", "bill_of_lading_forged.pdf")
    assert res.status_code == 201, res.text

    # registry: a fresh invoice is registered; the pre-financed one is a duplicate hit
    d = create(rahima, HUAXIN)
    propose(rahima, d["id"])
    ci = make_pdf(invoice_lines(nonce=uuid.uuid4().hex))
    assert upload(rahima, d["id"], "COMMERCIAL_INVOICE", "ci.pdf", ci).status_code == 201
    dup = upload(rahima, d["id"], "PROFORMA_INVOICE", "prefinanced_invoice.pdf")
    assert dup.status_code == 201, dup.text

    # injection console (admin)
    res = admin.post("/security/injection/run", json={"attack_id": "hidden-white-text"})
    assert res.status_code == 200, res.text

    # the seeded e-mail request is rejected by its buyer (human, Tier 3)
    reject_seeded_email_request(rahima)

    # Tier 2: fund, release approval requested and approved by a person
    fd = funded_deal(rahima, HUAXIN)
    ms = fd["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, body = release(rahima, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    appr = open_approval(fd["id"], ApprovalAction.RELEASE_MILESTONE)
    ok = rahima.post(f"/approvals/{appr.id}/approve", json={})
    assert ok.status_code == 200 and ok.json()["outcome"] == "EXECUTED", ok.text
    out["released_deal"] = fd["id"]

    # FX lock on the same deal (remaining tranches, CNY account)
    fx = rahima.post(f"/deals/{fd['id']}/fx-lock", json={})
    assert fx.status_code in (200, 202), fx.text
    out["fx_status"] = fx.status_code

    # Tier 2 rejected by the buyer
    rd = funded_deal(rahima, HUAXIN)
    rms = rd["milestones"][0]["id"]
    verify_evidence(admin, rms)
    assert release(rahima, rms)[0] == 202
    rej = open_approval(rd["id"], ApprovalAction.RELEASE_MILESTONE)
    assert (
        rahima.post(f"/approvals/{rej.id}/reject", json={"reason": "wrong goods"}).status_code
        == 200
    )

    # admin refund of a funded deal
    rf = funded_deal(rahima, HUAXIN)
    res = admin.post(f"/deals/{rf['id']}/refund", json={"reason": "supplier ceased trading"})
    assert res.status_code == 200, res.text

    # TC-06 e-mail redirection is blocked
    res = rahima.post("/inbox/email-check", json={"text": EMAIL.read_text(encoding="utf-8")})
    assert res.status_code == 200 and res.json()["blocked"], res.text

    # Tier 3: expired, locked (3 wrong codes), cancelled during cooling-off
    karim, _, _, appr = big_deal_approval()
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(expires_at=escrow.utcnow() - timedelta(minutes=1))
        )
    assert karim.get("/approvals?status=history").status_code == 200
    karim, _, _, appr = big_deal_approval()
    code = phone_code(karim, appr.id)
    end_cooling_off(appr.id)
    bad = "000000" if code != "000000" else "111111"
    for _ in range(3):
        karim.post(f"/approvals/{appr.id}/approve", json={"otp": bad})
    karim, _, _, appr = big_deal_approval()
    code = phone_code(karim, appr.id)
    early = karim.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert early.status_code == 409
    assert karim.post(f"/approvals/{appr.id}/cancel").status_code == 200

    # beneficiary change in-app: requested, approved with OTP after cooling-off (executed) ...
    huaxin, deal_id = as_user(HUAXIN_USER), huaxin_main_deal()
    assert supplier_request(huaxin, deal_id).status_code == 202
    appr = open_approval(deal_id, ApprovalAction.CHANGE_BENEFICIARY)
    code = phone_code(rahima, appr.id)
    end_cooling_off(appr.id)
    res = rahima.post(f"/approvals/{appr.id}/approve", json={"otp": code})
    assert res.status_code == 200 and res.json()["outcome"] == "EXECUTED", res.text
    # ... and a second one that is blocked by three wrong codes
    other = {"account_number": "HK-088-654321-002"}
    assert supplier_request(huaxin, deal_id, **other).status_code == 202
    appr = open_approval(deal_id, ApprovalAction.CHANGE_BENEFICIARY)
    code = phone_code(rahima, appr.id)
    end_cooling_off(appr.id)
    bad = "000000" if code != "000000" else "111111"
    for _ in range(3):
        rahima.post(f"/approvals/{appr.id}/approve", json={"otp": bad})

    # an LLM tool call through the guarded registry
    with Session(get_engine()) as s:
        ctx = ToolContext(caller="llm", user=current_user_of(RAHIMA), db=s, thread_id="t")
        outcome = default_registry().guard("check_documents", {"deal_id": MAIN}, ctx)
        assert outcome.ok, outcome.error
        s.commit()

    # a privacy gateway call that leaked
    gw = PrivacyGateway()
    gw.calls.append(
        CallRecord(
            node="explain", model="fake", payload="x", stats=Stats(leaked_count=1), sent=False
        )
    )
    with batch_session() as s:
        assert persist_calls(s, gw, source="chat", user_id=None) == 1
    return out


@pytest.fixture(scope="module")
def flow(
    seeded_db: str, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[list[dict[str, Any]]]:
    tmp = tmp_path_factory.mktemp("flow")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DEMO_MODE", "true")
        mp.setenv("COOLING_OFF_SECONDS", "600")
        mp.setenv("STORAGE_DIR", str(tmp / "storage"))
        mp.setenv("DOCUMENT_URL_SECRET", "test-document-url-secret")
        mp.setenv("ENABLE_DEV_EVIDENCE", "true")
        mp.setenv("AGENT_MOCK_MODE", "true")
        mp.setenv("KB_EMBEDDER", "hash")
        get_settings.cache_clear()
        run_flow(tmp)
        with batch_session() as s:
            lines = [line_of(r) for r in s.scalars(select(AuditLog).order_by(AuditLog.seq))]
        yield lines
        get_settings.cache_clear()


def by_action(lines: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [ln for ln in lines if ln["action"] == action]


def test_whole_chain_verifies_after_the_demo_flow(flow: list[dict[str, Any]]) -> None:
    report = verify_lines(flow, load_signing_key().public_key())
    assert report.ok, report.detail
    assert report.anchored and report.entries_checked == len(flow) > 100
    assert [ln["seq"] for ln in flow] == list(range(1, len(flow) + 1))


def test_no_identifier_survives_in_any_row_of_the_whole_flow(flow: list[dict[str, Any]]) -> None:
    hits = pii_hits(flow)
    assert hits == [], hits[:5]


def test_no_float_is_stored_in_any_payload(flow: list[dict[str, Any]]) -> None:
    assert not [ln["seq"] for ln in flow if has_float(ln["payload"])]


# (action, expected actor_type, expected tiers seen). Every one must be produced by real code.
EXPECTED = [
    ("DEMO_RESET", "system", {0}),
    ("KYB_CHECKED", "user", {0}),
    ("DOC_UPLOADED", "user", {0}),
    ("DOC_CHECKED", "user", {0}),
    ("DOC_INSTRUCTION_DETECTED", "system", {3}),
    ("REGISTRY_REGISTERED", "user", {0}),
    ("REGISTRY_DUPLICATE_HIT", "user", {3}),
    ("INJECTION_DETECTED", "system", {3}),
    ("RISK_DECISION", "user", {1, 2, 3}),
    ("APPROVAL_REQUESTED", "user", {3}),
    ("RELEASE_APPROVAL_REQUESTED", "user", {2, 3}),
    ("APPROVAL_APPROVED", "user", {2, 3}),
    ("APPROVAL_REJECTED", "user", {2, 3}),
    ("APPROVAL_EXPIRED", "system", {3}),
    ("APPROVAL_LOCKED", "user", {3}),
    ("APPROVAL_OTP_FAILED", "user", {3}),
    ("APPROVAL_CANCELLED", "user", {3}),
    ("APPROVAL_TOO_EARLY", "user", {3}),
    ("ESCROW_FUNDED", "user", {0}),
    ("TRANCHE_RELEASED", "user", {2}),
    ("ESCROW_REFUNDED", "user", {0}),
    ("FX_LOCKED", "user", {2}),
    ("BENEFICIARY_CHANGE_REQUESTED", "user", {3}),
    ("BENEFICIARY_CHANGED", "user", {3}),
    ("EMAIL_BENEFICIARY_CHANGE_BLOCKED", "user", {3}),
    ("PRIVACY_LEAK_ALERT", "system", {3}),
]


@pytest.mark.parametrize(("action", "actor", "tiers"), EXPECTED, ids=[e[0] for e in EXPECTED])
def test_demo_flow_writes_the_action_with_the_right_actor_and_tier(
    flow: list[dict[str, Any]], action: str, actor: str, tiers: set[int]
) -> None:
    reset = by_action(flow, "DEMO_RESET")[0]["seq"]
    rows = [r for r in by_action(flow, action) if r["seq"] >= reset]  # not the seeded history
    assert rows, f"{action} was never written by the real flow"
    assert {r["actor_type"] for r in rows} == {actor}
    assert tiers <= {r["tier"] for r in rows}


def test_llm_tool_call_is_logged_as_an_llm_entry_with_the_tool_tier(
    flow: list[dict[str, Any]],
) -> None:
    [row] = by_action(flow, "TOOL:check_documents")
    assert (row["actor_type"], row["actor_id"], row["tier"]) == ("llm", "agent", 0)
    assert row["payload"]["caller"] == "llm" and row["payload"]["on_behalf_of"]
    assert default_registry().get("check_documents").max_tier <= 1  # type: ignore[union-attr]


def test_human_approvals_carry_the_deciding_users_id(flow: list[dict[str, Any]]) -> None:
    for action in ("APPROVAL_APPROVED", "APPROVAL_REJECTED", "BENEFICIARY_CHANGED"):
        for row in by_action(flow, action):
            assert str(uuid.UUID(row["actor_id"])) == row["actor_id"], (action, row["actor_id"])


def test_expiry_is_written_by_the_system_not_by_a_person(flow: list[dict[str, Any]]) -> None:
    [row] = by_action(flow, "APPROVAL_EXPIRED")
    assert (row["actor_type"], row["actor_id"]) == ("system", "system")


def test_a_blocked_beneficiary_change_exists_as_email_block_and_as_locked_change(
    flow: list[dict[str, Any]],
) -> None:
    [email] = by_action(flow, "EMAIL_BENEFICIARY_CHANGE_BLOCKED")
    assert email["decision"] == "BLOCKED" and email["deal_id"]
    locked = [
        r
        for r in by_action(flow, "APPROVAL_LOCKED")
        if r["payload"].get("approval_action") == "CHANGE_BENEFICIARY"
    ]
    assert len(locked) == 1 and locked[0]["tier"] == 3


def test_approval_entries_are_bound_to_the_params_hash_and_deal(flow: list[dict[str, Any]]) -> None:
    rows = by_action(flow, "APPROVAL_APPROVED")
    assert rows
    for r in rows:
        assert len(r["payload"]["params_hash"]) == 64 and r["deal_id"]


def test_the_wrong_code_counter_is_visible_in_the_otp_failed_decisions(
    flow: list[dict[str, Any]],
) -> None:
    left = {r["decision"] for r in by_action(flow, "APPROVAL_OTP_FAILED")}
    assert left == {"WRONG_CODE:2_LEFT", "WRONG_CODE:1_LEFT"}


def test_the_privacy_leak_alert_records_the_blocked_call_without_payload(
    flow: list[dict[str, Any]],
) -> None:
    [row] = by_action(flow, "PRIVACY_LEAK_ALERT")
    assert row["decision"] == "BLOCKED" and row["payload"]["leaked"] == 1
    assert "payload" not in row["payload"]


def test_flow_entries_all_follow_the_demo_reset(flow: list[dict[str, Any]]) -> None:
    reset = by_action(flow, "DEMO_RESET")[0]["seq"]
    first_flow = by_action(flow, "KYB_CHECKED")
    assert any(r["seq"] > reset for r in first_flow)
    assert flow[-1]["seq"] > reset
