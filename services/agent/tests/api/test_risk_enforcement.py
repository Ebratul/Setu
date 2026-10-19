"""Service-level enforcement of the risk engine (SR-1, SR-2, TC-07): the engine decides inside the
service from DB facts, the API ignores client tier/approved fields, the agent can only propose,
and every decision is stored. Real Postgres with the seeded demo."""

import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update

from app.agent.registry import ToolContext, default_registry
from app.db.enums import (
    AccountStatus,
    AlertType,
    ApprovalAction,
    ApprovalStatus,
    CheckStatus,
    DocStatus,
    DocType,
    FxLockStatus,
    LedgerKind,
    MilestoneStatus,
    Severity,
)
from app.db.models import (
    Alert,
    ApprovalRequest,
    AuditLog,
    BankAccount,
    Deal,
    Document,
    ForensicFinding,
    FxLock,
    LedgerEntry,
    Milestone,
    Party,
    RiskEvent,
)
from app.db.session import batch_session
from app.errors import Forbidden
from app.services import beneficiary, deals, escrow, fx_lock
from app.services.risk.engine import Origin
from app.services.risk.gate import ApprovalInvalid, ApprovalPending
from app.services.scope import demo_today
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAXIN,
    KARIM,
    RAHIMA,
    as_user,
    confirmed,
    create,
    current_user_of,
    fund,
    give_cash,
    propose,
    release,
    verify_evidence,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def fresh_state(seeded_db: str) -> None:
    give_cash("dhaka-stitch-works")
    give_cash("rahima-knitwear")
    with batch_session() as s:  # the seeded Tier 3 beneficiary approval would block Huaxin money
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.tier == 3, ApprovalRequest.status == ApprovalStatus.PENDING)
            .values(status=ApprovalStatus.REJECTED)
        )


# --- helpers ----------------------------------------------------------------------------------


def usd_deal(
    buyer: Any,
    goods: str = "9600.00",
    percents: list[str] | None = None,
    supplier: str = BRIGHTLINE,
) -> dict[str, Any]:
    """Confirmed deal (Brightline has a USD account) with the first tranche deposited."""
    d = create(buyer, supplier, qty=goods, price="1.00")
    body = {"template": "custom", "percents": percents} if percents else {}
    propose(buyer, d["id"], **body)
    confirmed(buyer, None, d["id"])
    return fund(buyer, d["id"])


def ready(buyer: Any, **kw: Any) -> tuple[str, dict[str, Any]]:
    d = usd_deal(buyer, **kw)
    ms = d["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    return ms, d


def release_events(deal_id: str) -> list[RiskEvent]:
    return [e for e in events(deal_id) if e.action == "RELEASE_TRANCHE"]


def events(deal_id: str) -> list[RiskEvent]:
    with batch_session() as s:
        return list(
            s.scalars(
                select(RiskEvent)
                .where(RiskEvent.deal_id == uuid.UUID(deal_id))
                .order_by(RiskEvent.ts, RiskEvent.id)
            )
        )


def ledger_rows(deal_id: str) -> int:
    with batch_session() as s:
        return (
            s.scalar(
                select(func.count())
                .select_from(LedgerEntry)
                .where(
                    LedgerEntry.deal_id == uuid.UUID(deal_id),
                    LedgerEntry.kind == LedgerKind.RELEASE,
                )
            )
            or 0
        )


def approvals(deal_id: str, action: ApprovalAction | None = None) -> list[ApprovalRequest]:
    with batch_session() as s:
        q = select(ApprovalRequest).where(ApprovalRequest.deal_id == uuid.UUID(deal_id))
        if action:
            q = q.where(ApprovalRequest.action == action)
        return list(s.scalars(q.order_by(ApprovalRequest.created_at)))


def add_document(
    deal_id: str,
    ms_id: str,
    check: CheckStatus,
    findings: tuple[str, ...] = (),
    score: int | None = None,
) -> None:
    with batch_session() as s:
        doc = Document(
            id=uuid.uuid4(),
            key=f"test:{uuid.uuid4().hex[:16]}",
            deal_id=uuid.UUID(deal_id),
            milestone_id=uuid.UUID(ms_id),
            doc_type=DocType.PROFORMA_INVOICE,
            file_name="x.pdf",
            storage_path="x",
            mime_type="application/pdf",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            status=DocStatus.UPLOADED,
            check_status=check,
            extracted_json={"_forensics": {"verdict": {"score": score}}} if score else None,
        )
        s.add(doc)
        s.flush()
        for code in findings:
            s.add(
                ForensicFinding(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    check_code=code,
                    status=CheckStatus.FAILED,
                    severity=Severity.CRITICAL,
                    detail={},
                    checked_at=doc.uploaded_at or escrow.utcnow(),
                )
            )


# --- decisions --------------------------------------------------------------------------------


def test_tc07_a_22000_release_needs_tier3_and_moves_nothing() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim, goods="44000.00", percents=["50", "50"])
    status, body = release(karim, ms)
    assert status == 202 and body["outcome"] == "PENDING_APPROVAL"
    assert body["risk"]["tier"] == 3
    assert any("USD 20,000" in r for r in body["risk"]["reasons"])
    assert body["approval"]["otp_required"] is True and body["approval"]["cooling_off_until"]
    assert ledger_rows(d["id"]) == 0
    [appr] = approvals(d["id"], ApprovalAction.RELEASE_MILESTONE)
    assert appr.tier == 3 and appr.status == ApprovalStatus.PENDING and appr.otp_required
    assert appr.cooling_off_until is not None and appr.params_hash


def test_clean_repeat_supplier_release_is_tier1_with_an_info_notice() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    status, body = release(karim, ms)
    assert status == 200 and body["outcome"] == "RELEASED" and body["risk"]["tier"] == 1
    assert ledger_rows(d["id"]) == 2
    with batch_session() as s:
        notice = s.scalars(select(Alert).where(Alert.key == f"risk:auto:{ms}")).one()
        assert notice.type == AlertType.INFO and notice.severity == Severity.INFO
        assert notice.title_en.startswith("Released USD 2,880 to ")
        assert notice.title_bn and notice.deal_id == uuid.UUID(d["id"])
    [ev] = release_events(d["id"])
    assert (ev.action, ev.decision, ev.tier, ev.origin) == (
        "RELEASE_TRANCHE",
        "ALLOW",
        1,
        "USER_UI",
    )
    assert ev.explanation_en and ev.explanation_bn and len(ev.context_hash) == 64


def test_first_deal_is_tier2_and_the_second_deal_with_the_same_supplier_is_tier1() -> None:
    rahima = as_user(RAHIMA)
    ms, _ = ready(rahima)  # Rahima has never funded a deal with Brightline
    status, body = release(rahima, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    assert "First deal with this supplier." in body["risk"]["reasons"]
    ms2, _ = ready(rahima)  # the first deal is FUNDED now, so this supplier is a repeat one
    status, body = release(rahima, ms2)
    assert status == 200 and body["risk"]["tier"] == 1


def test_a_recently_opened_receiving_account_is_tier3() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    with batch_session() as s:
        deal = s.get(Deal, uuid.UUID(d["id"]))
        assert deal is not None
        acct_id = deal.beneficiary_account_id
        original = s.get(BankAccount, acct_id).first_seen_on  # type: ignore[union-attr]
        s.execute(
            update(BankAccount)
            .where(BankAccount.id == acct_id)
            .values(first_seen_on=demo_today(s) - timedelta(days=5))
        )
    try:
        status, body = release(karim, ms)
    finally:
        with batch_session() as s:
            s.execute(
                update(BankAccount).where(BankAccount.id == acct_id).values(first_seen_on=original)
            )
    assert status == 202 and body["risk"]["tier"] == 3
    assert any("recently" in r for r in body["risk"]["reasons"])
    assert ledger_rows(d["id"]) == 0


@pytest.mark.parametrize("finding", ["DUPLICATE_HASH", "INSTRUCTION_SCAN"])
def test_duplicate_hash_and_document_instruction_are_tier3(finding: str) -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    add_document(d["id"], ms, CheckStatus.PASSED, (finding,))
    status, body = release(karim, ms)
    assert status == 202 and body["risk"]["tier"] == 3
    assert ledger_rows(d["id"]) == 0


def test_a_document_warning_is_tier2() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    add_document(d["id"], ms, CheckStatus.WARNING, score=45)
    status, body = release(karim, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    assert "A document has a forensic warning." in body["risk"]["reasons"]


def test_a_failed_document_blocks_with_a_fraud_alert_and_a_stored_decision() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    add_document(d["id"], ms, CheckStatus.FAILED, score=72)
    status, body = release(karim, ms)
    assert status == 409 and body["code"] == "RELEASE_BLOCKED"
    assert ledger_rows(d["id"]) == 0 and not approvals(d["id"])
    with batch_session() as s:
        alert = s.scalars(select(Alert).where(Alert.deal_id == uuid.UUID(d["id"]))).one()
        assert alert.type == AlertType.FRAUD and alert.severity == Severity.CRITICAL
        assert s.get(Milestone, uuid.UUID(ms)).status == MilestoneStatus.READY  # type: ignore[union-attr]
    [ev] = release_events(d["id"])
    assert (ev.decision, ev.tier) == ("BLOCK", 3) and ev.reason_codes == ["DOCUMENT_FAILED"]
    with batch_session() as s:
        assert s.get(AuditLog, ev.audit_seq).action == "RISK_DECISION"  # type: ignore[union-attr]


def test_a_conversion_release_needs_a_rate_lock_and_a_person_can_lock_one_inline() -> None:
    karim = as_user(RAHIMA)
    # Huaxin settles in CNY: Tier 2 until a rate is locked.
    d = create(karim, HUAXIN)
    propose(karim, d["id"])
    confirmed(karim, as_user("huaxin@demo.setu"), d["id"])
    fund(karim, d["id"])
    ms = d["milestones"][0]["id"] if d["milestones"] else None
    detail = karim.get(f"/deals/{d['id']}").json()
    ms = detail["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    res = karim.post(f"/deals/{d['id']}/fx-lock", json={"tier": 0, "approved": True})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outcome"] == "LOCKED" and body["base"] == "USD" and body["quote"] == "CNY"
    assert body["risk"]["tier"] == 2 and body["risk"]["decision"] == "REQUIRE_APPROVAL"
    with batch_session() as s:
        [lock] = s.scalars(select(FxLock).where(FxLock.deal_id == uuid.UUID(d["id"]))).all()
        assert lock.status == FxLockStatus.ACTIVE and lock.rate > 0
    status, rel = release(karim, ms)
    assert status == 200 and rel["risk"]["tier"] == 1


def test_a_conversion_release_without_a_lock_is_tier2() -> None:
    karim = as_user(RAHIMA)
    d = create(karim, HUAXIN)
    propose(karim, d["id"])
    confirmed(karim, as_user("huaxin@demo.setu"), d["id"])
    fund(karim, d["id"])
    ms = karim.get(f"/deals/{d['id']}").json()["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    status, body = release(karim, ms)
    assert status == 202 and body["risk"]["tier"] == 2
    assert "The payment converts currency and no rate is locked." in body["risk"]["reasons"]


# --- bypass attempts --------------------------------------------------------------------------


def test_client_supplied_tier_and_approved_fields_are_ignored() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim, goods="44000.00", percents=["50", "50"])
    res = karim.post(
        f"/milestones/{ms}/release",
        json={
            "idempotency_key": "bypass-key-0001",
            "tier": 0,
            "approved": True,
            "approval_id": "x",
        },
    )
    assert res.status_code == 202, res.text
    assert res.json()["risk"]["tier"] == 3 and ledger_rows(d["id"]) == 0
    fres = karim.post(f"/deals/{d['id']}/escrow/fund", json={"tier": 0, "approved": True})
    assert fres.status_code in (200, 409)  # decided by the engine, never by the body


def test_a_fake_agent_tool_can_only_create_an_approval_request() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)  # a clean Tier 1 release for a person
    user = current_user_of(KARIM)
    with batch_session() as s:
        out = escrow.release_tranche(s, uuid.UUID(ms), user, "agent-key-0001", origin=Origin.AGENT)

        assert out.outcome == "PENDING_APPROVAL" and out.approval is not None
        assert out.approval.tier == 2 and out.approval.requested_by.value == "llm"
    assert ledger_rows(d["id"]) == 0
    [ev] = [e for e in events(d["id"]) if e.origin == "AGENT"]
    print(ev.reason_codes)
    assert ev.decision == "REQUIRE_APPROVAL" and "AGENT_ORIGIN" in ev.reason_codes


def test_an_approval_can_only_be_executed_by_a_person() -> None:
    karim = as_user(KARIM)
    ms, _ = ready(karim)
    user = current_user_of(KARIM)
    with batch_session() as s, pytest.raises(Forbidden):
        escrow.release_tranche(
            s, uuid.UUID(ms), user, "agent-key-0002", approval_id=uuid.uuid4(), origin=Origin.AGENT
        )


def test_the_propose_tool_sends_for_approval_and_never_executes() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim)
    user = current_user_of(KARIM)
    with batch_session() as s:
        out = default_registry().guard(
            "propose_release_tranche",
            {"milestone_id": ms, "idempotency_key": "tool-key-0001"},
            ToolContext(caller="llm", user=user, db=s),
            allowed=frozenset({"propose_release_tranche"}),
        )
    assert out.ok and out.data is not None, out.error
    assert out.data["status"] == "SENT_FOR_APPROVAL" and out.data["tier"] == 2
    assert "I've sent this for your approval" in out.data["message"]
    assert ledger_rows(d["id"]) == 0 and len(approvals(d["id"])) == 1


def test_agent_tools_for_other_money_actions_only_queue_requests() -> None:
    karim = as_user(KARIM)
    d = create(karim, BRIGHTLINE)
    ref = d["reference"]
    user = current_user_of(KARIM)
    reg = default_registry()
    for tool, args in (
        ("propose_milestones", {"deal_id": ref}),
        ("propose_confirm_milestones", {"deal_id": ref}),
        ("propose_fund_escrow", {"deal_id": ref}),
        ("propose_fx_lock", {"deal_id": ref}),
    ):
        with batch_session() as s:
            out = reg.guard(
                tool,
                args,
                ToolContext(caller="llm", user=user, db=s),
                allowed=frozenset({tool}),
            )
        # A refusal for a state the deal is not in (fund before confirm, nothing to lock) is fine;
        # what must never happen is an executed action.
        if out.ok:
            assert out.data is not None and out.data["status"] == "SENT_FOR_APPROVAL", tool
    detail = karim.get(f"/deals/{d['id']}").json()
    assert detail["status"] == "DRAFT" and detail["milestones"] == []
    with batch_session() as s:
        assert (
            s.scalar(
                select(func.count()).select_from(FxLock).where(FxLock.deal_id == uuid.UUID(d["id"]))
            )
            == 0
        )


def test_two_concurrent_releases_make_one_approval_request() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim, goods="44000.00", percents=["50", "50"])
    user = current_user_of(KARIM)
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def worker(key: str) -> None:
        with batch_session() as s:
            barrier.wait()
            try:
                results.append(escrow.release_tranche(s, uuid.UUID(ms), user, key))
            except Exception as exc:  # pragma: no cover - reported by the assertion below
                results.append(exc)

    threads = [threading.Thread(target=worker, args=(f"race-key-000{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert all(isinstance(r, escrow.ReleaseOutcome) for r in results), results
    assert {r.outcome for r in results} == {"PENDING_APPROVAL"}
    assert len(approvals(d["id"], ApprovalAction.RELEASE_MILESTONE)) == 1
    assert ledger_rows(d["id"]) == 0


# --- the other enforcement points -------------------------------------------------------------


def test_fund_escrow_by_the_agent_queues_an_approval_and_moves_no_cash() -> None:
    karim = as_user(KARIM)
    d = create(karim, BRIGHTLINE)
    propose(karim, d["id"])
    confirmed(karim, None, d["id"])
    user = current_user_of(KARIM)
    with batch_session() as s:
        with pytest.raises(ApprovalPending) as pending:
            escrow.fund_escrow(s, user, uuid.UUID(d["id"]), None, origin=Origin.AGENT)
        assert pending.value.approval.action == ApprovalAction.FUND_ESCROW
        assert pending.value.approval.tier == 2
    detail = karim.get(f"/deals/{d['id']}").json()
    assert detail["status"] == "CONFIRMED" and detail["escrow"]["funded"] == "0.00"
    assert len(approvals(d["id"], ApprovalAction.FUND_ESCROW)) == 1


def test_a_persons_fund_request_runs_and_records_a_decision() -> None:
    karim = as_user(KARIM)
    d = usd_deal(karim)
    assert d["escrow"]["funded"] != "0.00"
    [ev] = [e for e in events(d["id"]) if e.action == "FUND_ESCROW"]
    assert (ev.action, ev.decision, ev.tier) == ("FUND_ESCROW", "ALLOW", 1)


def test_schedule_and_confirmation_by_the_agent_queue_requests_and_by_a_person_run_inline() -> None:
    karim = as_user(KARIM)
    d = create(karim, BRIGHTLINE)
    user = current_user_of(KARIM)
    from app.schemas.deals import ProposeRequest

    with batch_session() as s, pytest.raises(ApprovalPending):
        deals.propose_milestones(s, user, uuid.UUID(d["id"]), ProposeRequest(), origin=Origin.AGENT)
    assert karim.get(f"/deals/{d['id']}").json()["milestones"] == []
    assert len(approvals(d["id"], ApprovalAction.CHANGE_MILESTONE_SCHEDULE)) == 1
    propose(karim, d["id"])  # a person's own request is the one-tap
    with batch_session() as s, pytest.raises(ApprovalPending):
        deals.confirm_milestones(s, user, uuid.UUID(d["id"]), None, origin=Origin.AGENT)
    assert karim.post(f"/deals/{d['id']}/milestones/confirm", json={}).status_code == 200
    kinds = [(e.action, e.origin, e.tier) for e in events(d["id"])]
    assert ("PROPOSE_MILESTONES", "USER_UI", 2) in kinds
    assert ("CONFIRM_MILESTONES", "USER_UI", 2) in kinds
    assert ("PROPOSE_MILESTONES", "AGENT", 2) in kinds


def test_lock_fx_by_the_agent_is_an_approval_request_not_a_lock() -> None:
    karim = as_user(KARIM)
    d = create(karim, HUAXIN)
    propose(karim, d["id"])
    confirmed(karim, as_user("huaxin@demo.setu"), d["id"])
    fund(karim, d["id"])
    user = current_user_of(KARIM)
    with batch_session() as s:
        out = fx_lock.lock_fx(s, user, uuid.UUID(d["id"]), origin=Origin.AGENT)
    assert out.outcome == "PENDING_APPROVAL" and out.lock is None and out.approval is not None
    assert out.approval.action == ApprovalAction.LOCK_FX_RATE
    with batch_session() as s:
        assert (
            s.scalar(
                select(func.count()).select_from(FxLock).where(FxLock.deal_id == uuid.UUID(d["id"]))
            )
            == 0
        )


def pending_account(supplier_code: str) -> uuid.UUID:
    with batch_session() as s:
        return s.scalars(
            select(BankAccount.id)
            .join(Party, Party.id == BankAccount.party_id)
            .where(Party.code == supplier_code, BankAccount.status == AccountStatus.PENDING_CHANGE)
        ).first()  # type: ignore[return-value]


def test_a_beneficiary_change_is_tier3_and_runs_only_after_approval_and_cooling_off() -> None:
    karim = as_user(KARIM)
    d = create(karim, HUAXIN)
    new = pending_account(HUAXIN)
    res = karim.post(f"/deals/{d['id']}/beneficiary", json={"bank_account_id": str(new)})
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["outcome"] == "PENDING_APPROVAL" and body["risk"]["tier"] == 3
    assert body["approval"]["otp_required"] and body["approval"]["cooling_off_until"]
    [appr] = approvals(d["id"], ApprovalAction.CHANGE_BENEFICIARY)
    with batch_session() as s:
        old = s.get(Deal, uuid.UUID(d["id"])).beneficiary_account_id  # type: ignore[union-attr]
    assert old != new

    user = current_user_of(KARIM)
    with batch_session() as s:  # approved by a person, but still inside the cooling-off window
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(status=ApprovalStatus.APPROVED)
        )
    with batch_session() as s, pytest.raises(ApprovalInvalid) as exc:
        beneficiary.change_beneficiary(s, user, uuid.UUID(d["id"]), new, approval_id=appr.id)
    assert exc.value.code == "COOLING_OFF"
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == appr.id)
            .values(cooling_off_until=escrow.utcnow() - timedelta(minutes=1))
        )
    with batch_session() as s, pytest.raises(ApprovalInvalid) as agent_exc:
        beneficiary.change_beneficiary(
            s, user, uuid.UUID(d["id"]), new, approval_id=appr.id, origin=Origin.AGENT
        )
    assert agent_exc.value.code == "APPROVAL_NOT_HUMAN"
    with batch_session() as s:
        out = beneficiary.change_beneficiary(s, user, uuid.UUID(d["id"]), new, approval_id=appr.id)
        assert out.outcome == "CHANGED"
    with batch_session() as s:
        assert s.get(Deal, uuid.UUID(d["id"])).beneficiary_account_id == new  # type: ignore[union-attr]
        assert s.get(ApprovalRequest, appr.id).status == ApprovalStatus.EXECUTED  # type: ignore[union-attr]
    with batch_session() as s:  # leave the shared demo data as it was
        s.execute(
            update(BankAccount)
            .where(BankAccount.id == new)
            .values(status=AccountStatus.PENDING_CHANGE)
        )


def test_decisions_are_deterministic_and_readable_for_the_admin_console() -> None:
    karim = as_user(KARIM)
    ms, d = ready(karim, goods="44000.00", percents=["50", "50"])
    release(karim, ms, "stable-key-0001")
    release(karim, ms, "stable-key-0002")  # returns the open approval, no second decision
    evs = [e for e in events(d["id"]) if e.action == "RELEASE_TRANCHE"]
    assert len(evs) == 1
    assert evs[0].decision == "REQUIRE_APPROVAL" and evs[0].tier == 3
    assert evs[0].amount_usd is not None and evs[0].amount_usd > Decimal("20000")


def test_a_tiny_fx_lock_does_not_clear_the_conversion_rule() -> None:
    rahima = as_user(RAHIMA)
    d = create(rahima, HUAXIN)
    propose(rahima, d["id"])
    confirmed(rahima, as_user("huaxin@demo.setu"), d["id"])
    fund(rahima, d["id"])
    ms = rahima.get(f"/deals/{d['id']}").json()["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    assert rahima.post(f"/deals/{d['id']}/fx-lock", json={"amount": "0.01"}).status_code == 200
    status, body = release(rahima, ms)
    assert status == 202 and body["risk"]["tier"] == 2
