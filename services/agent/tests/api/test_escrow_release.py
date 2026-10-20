"""FR-5 release/refund: evidence gate, balance, beneficiary, risk hook contract, FX, idempotency,
concurrency, state advance, invariant and audit. Real Postgres with the seeded demo."""

import threading
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.audit.export import line_of
from app.audit.keys import load_signing_key
from app.audit.verify import verify_lines
from app.db.enums import (
    AccountStatus,
    ApprovalAction,
    ApprovalStatus,
    EscrowStatus,
    KybStatus,
    LedgerDirection,
    LedgerKind,
    MilestoneStatus,
)
from app.db.models import (
    ApprovalRequest,
    AuditLog,
    BankAccount,
    Deal,
    EscrowAccount,
    LedgerEntry,
    Milestone,
    Party,
)
from app.db.session import batch_session
from app.domain.money import q2
from app.errors import Conflict
from app.security import risk_hook
from app.security.approvals import approval_binding_hash
from app.security.risk_hook import (
    ReleaseContext,
    RiskAction,
    RiskDecision,
    RiskReason,
    RiskResult,
)
from app.services import escrow
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAMENG,
    HUAXIN,
    HUAXIN_USER,
    KARIM,
    RAHIMA,
    as_user,
    confirmed,
    create,
    current_user_of,
    fund,
    funded_deal,
    give_cash,
    propose,
    release,
    verify_evidence,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def rich_buyers(seeded_db: str) -> None:
    give_cash("dhaka-stitch-works")
    give_cash("rahima-knitwear")


@pytest.fixture(autouse=True)
def seeded_tier3_decided(seeded_db: str) -> None:
    """The seeded CHANGE_BENEFICIARY (Tier 3) approval blocks every Huaxin release while open; the
    mechanics tests run with it decided. Tests of that block reopen it themselves."""
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.tier == 3, ApprovalRequest.status == ApprovalStatus.PENDING)
            .values(status=ApprovalStatus.REJECTED)
        )


@pytest.fixture(autouse=True)
def allow_hook():  # type: ignore[no-untyped-def]
    """Most tests are about escrow mechanics, not policy: they run under an ALLOW tier 0 hook.
    Tests of the interim policy select `risk_hook.default_evaluate` explicitly."""
    with risk_hook.use_hook(lambda a, c: RiskResult(decision=RiskDecision.ALLOW, tier=0)):
        yield


def ready_deal(**kw: Any) -> tuple[TestClient, TestClient, dict[str, Any]]:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim, **kw)
    return karim, admin, d


def totals(deal_id: str) -> dict[str, Decimal]:
    """Escrow row plus the same totals re-derived from the ledger (debit side of each kind)."""
    with batch_session() as s:
        e = s.scalars(
            select(EscrowAccount).where(EscrowAccount.deal_id == uuid.UUID(deal_id))
        ).one()
        by_kind = dict(
            s.execute(
                select(LedgerEntry.kind, func.coalesce(func.sum(LedgerEntry.amount), 0))
                .where(
                    LedgerEntry.deal_id == uuid.UUID(deal_id),
                    LedgerEntry.direction == LedgerDirection.DEBIT,
                )
                .group_by(LedgerEntry.kind)
            ).all()
        )
        out = {
            "funded": e.funded_total,
            "released": e.released_total,
            "refunded": e.refunded_total,
            "balance": e.balance,
        }
        assert e.funded_total == e.released_total + e.refunded_total + e.balance
        assert by_kind.get(LedgerKind.FUND, 0) == e.funded_total
        assert by_kind.get(LedgerKind.RELEASE, 0) == e.released_total
        assert by_kind.get(LedgerKind.REFUND, 0) == e.refunded_total
        return out


def release_rows(deal_id: str) -> int:
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


def ms_status(ms_id: str) -> MilestoneStatus:
    with batch_session() as s:
        return s.get(Milestone, uuid.UUID(ms_id)).status  # type: ignore[union-attr]


def audit_actions(deal_id: str) -> list[str]:
    with batch_session() as s:
        return list(
            s.scalars(
                select(AuditLog.action)
                .where(AuditLog.deal_id == uuid.UUID(deal_id))
                .order_by(AuditLog.seq)
            )
        )


def code(res: Any) -> str:
    return res.json().get("code", "")


# --- the happy path, end to end ---------------------------------------------------------------


def test_full_lifecycle_with_cny_settlement_and_invariants(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    deal_id = d["id"]
    m1, m2, m3 = (m["id"] for m in d["milestones"])
    assert totals(deal_id)["balance"] == Decimal("2880.00")

    # a. evidence gate: nothing moves until the evidence is VERIFIED
    status, body = release(karim, m1)
    assert status == 409 and body["code"] == "EVIDENCE_NOT_VERIFIED"
    assert release_rows(deal_id) == 0 and ms_status(m1) == MilestoneStatus.READY
    assert "TRANCHE_RELEASE_REFUSED" in audit_actions(deal_id)
    for bad in ("FLAGGED", "REJECTED"):
        verify_evidence(admin, m1, bad)
        assert release(karim, m1)[1]["code"] == "EVIDENCE_NOT_VERIFIED"

    verify_evidence(admin, m1)
    status, r1 = release(karim, m1, "key-m1-0001")
    assert status == 200 and r1["outcome"] == "RELEASED" and r1["idempotent_replay"] is False
    assert r1["risk"]["decision"] == "ALLOW" and r1["risk"]["tier"] == 0
    assert r1["milestone"]["status"] == "RELEASED" and r1["milestone"]["released_at"]
    dr, cr = r1["ledger"]
    assert (dr["direction"], cr["direction"]) == ("DEBIT", "CREDIT")
    assert dr["account"].startswith("supplier:") and cr["account"] == f"escrow:{d['reference']}"
    assert dr["amount"] == cr["amount"] == "2880.00" and dr["currency"] == "USD"
    assert dr["kind"] == "RELEASE" and dr["milestone_seq"] == 1
    # CNY account: the rate and the counter amount are recorded on the posting.
    rate = Decimal(dr["fx_rate"])
    assert dr["counter_currency"] == "CNY" and Decimal(dr["counter_amount"]) == q2(
        Decimal("2880") * rate
    )
    assert r1["milestone"]["settlement"] == {
        "currency": "CNY",
        "fx_rate": dr["fx_rate"],
        "counter_amount": dr["counter_amount"],
    }
    deal = r1["deal"]
    assert deal["status"] == "IN_PRODUCTION"
    assert deal["escrow"]["released"] == "2880.00" and deal["escrow"]["balance"] == "0.00"
    assert deal["escrow"]["status"] == "TRANCHE_RELEASED" and deal["escrow"]["invariant_ok"]
    assert [m["status"] for m in deal["milestones"]] == ["RELEASED", "PENDING", "PENDING"]
    assert totals(deal_id) == {
        "funded": Decimal("2880"), "released": Decimal("2880"),
        "refunded": Decimal("0"), "balance": Decimal("0"),
    }  # fmt: skip

    # the next tranche is not funded yet: it is not READY, so it cannot be released
    verify_evidence(admin, m2)
    status, body = release(karim, m2)
    assert status == 409 and body["code"] == "MILESTONE_NOT_READY"
    d2 = fund(karim, deal_id)  # default = next uncovered tranche (M2)
    assert d2["escrow"]["balance"] == "5760.00"
    assert [m["status"] for m in d2["milestones"]] == ["RELEASED", "READY", "PENDING"]
    status, r2 = release(karim, m2)
    assert status == 200 and r2["deal"]["status"] == "SHIPPED"
    assert r2["deal"]["milestones"][2]["status"] == "PENDING"

    fund(karim, deal_id)
    verify_evidence(admin, m3)
    status, r3 = release(karim, m3)
    assert status == 200
    final = r3["deal"]
    assert final["status"] == "COMPLETED" and final["completed_on"]
    assert final["escrow"]["status"] == "COMPLETED"
    assert final["escrow"]["released"] == "9600.00" and final["escrow"]["balance"] == "0.00"
    assert [m["status"] for m in final["milestones"]] == ["RELEASED"] * 3
    assert final["next_milestone"] is None
    assert totals(deal_id)["released"] == Decimal("9600")
    ledger = karim.get(f"/deals/{deal_id}/ledger").json()
    assert ledger["balanced"] is True
    assert [r["kind"] for r in ledger["rows"]].count("RELEASE") == 6
    actions = audit_actions(deal_id)
    assert actions.count("TRANCHE_RELEASED") == 3 and actions.count("ESCROW_FUNDED") == 3
    # the deal's signed audit rows are part of one valid chain
    with batch_session() as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.seq)).all()
        lines = [line_of(a) for a in rows]
    assert verify_lines(lines, load_signing_key().public_key()).ok


def test_usd_account_has_no_fx_fields(seeded_db: str) -> None:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = create(karim, BRIGHTLINE)
    propose(karim, d["id"])
    confirmed(karim, None, d["id"])
    d = fund(karim, d["id"])
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    status, r = release(karim, ms)
    assert status == 200
    assert r["ledger"][0]["fx_rate"] is None and r["ledger"][0]["counter_amount"] is None
    assert r["milestone"]["settlement"]["currency"] == "USD"


# --- idempotency ------------------------------------------------------------------------------


def test_same_key_replays_and_a_different_key_is_refused(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    s1, first = release(karim, ms, "idem-key-0001")
    s2, replay = release(karim, ms, "idem-key-0001")
    assert s1 == s2 == 200 and replay["idempotent_replay"] is True and replay["risk"] is None
    assert [r["id"] for r in replay["ledger"]] == [r["id"] for r in first["ledger"]]
    assert release_rows(d["id"]) == 2 and totals(d["id"])["released"] == Decimal("2880")
    status, body = release(karim, ms, "idem-key-0002")
    assert status == 409 and body["code"] == "MILESTONE_ALREADY_RELEASED"
    assert release_rows(d["id"]) == 2
    assert (
        karim.post(f"/milestones/{ms}/release", json={"idempotency_key": "short"}).status_code
        == 422
    )
    assert karim.post(f"/milestones/{ms}/release", json={}).status_code == 422


def test_concurrent_releases_with_the_same_key_release_once(seeded_db: str) -> None:
    _, admin, d = ready_deal()
    ms = uuid.UUID(d["milestones"][0]["id"])
    verify_evidence(admin, str(ms))
    user = current_user_of(KARIM)
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def worker() -> None:
        with batch_session() as s:
            barrier.wait()
            try:
                results.append(escrow.release_tranche(s, ms, user, "same-key-concurrent"))
            except Exception as exc:  # pragma: no cover - reported by the assertion below
                results.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    assert all(isinstance(r, escrow.ReleaseOutcome) for r in results), results
    assert sorted(r.replay for r in results) == [False, True]
    assert release_rows(d["id"]) == 2, "one release = one debit + one credit"
    assert totals(d["id"])["released"] == Decimal("2880")
    assert audit_actions(d["id"]).count("TRANCHE_RELEASED") == 1


def test_concurrent_releases_with_different_keys_second_is_refused(seeded_db: str) -> None:
    _, admin, d = ready_deal()
    ms = uuid.UUID(d["milestones"][0]["id"])
    verify_evidence(admin, str(ms))
    user = current_user_of(KARIM)
    barrier = threading.Barrier(2)
    results: list[Any] = []

    def worker(key: str) -> None:
        with batch_session() as s:
            barrier.wait()
            try:
                results.append(escrow.release_tranche(s, ms, user, key))
            except Conflict as exc:
                results.append(exc)

    threads = [threading.Thread(target=worker, args=(f"diff-key-000{i}",)) for i in range(2)]
    [t.start() for t in threads]
    [t.join(timeout=30) for t in threads]
    done = [r for r in results if isinstance(r, escrow.ReleaseOutcome)]
    refused = [r for r in results if isinstance(r, Conflict)]
    assert len(done) == 1 and len(refused) == 1
    assert refused[0].code == "MILESTONE_ALREADY_RELEASED"
    assert release_rows(d["id"]) == 2 and totals(d["id"])["released"] == Decimal("2880")


# --- hard checks before the hook --------------------------------------------------------------


def test_release_refuses_when_escrow_balance_is_short(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:  # simulate a smaller deposit without breaking the invariant
        s.execute(
            update(EscrowAccount)
            .where(EscrowAccount.deal_id == uuid.UUID(d["id"]))
            .values(funded_total=Decimal("1000"), balance=Decimal("1000"))
        )
    status, body = release(karim, ms)
    assert status == 409 and body["code"] == "INSUFFICIENT_ESCROW"
    assert release_rows(d["id"]) == 0


@pytest.mark.parametrize(
    ("account_status", "expected"),
    [
        (AccountStatus.PENDING_CHANGE, "BENEFICIARY_NOT_ACTIVE"),
        (AccountStatus.RETIRED, "BENEFICIARY_NOT_ACTIVE"),
    ],
)
def test_release_refuses_a_non_active_beneficiary(
    seeded_db: str, account_status: AccountStatus, expected: str
) -> None:
    """TC-06 support: the unreviewed Hong Kong account (PENDING_CHANGE) can never be paid."""
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:
        pending = s.scalars(
            select(BankAccount).where(BankAccount.status == AccountStatus.PENDING_CHANGE)
        ).first()
        assert pending is not None
        s.execute(
            update(Deal)
            .where(Deal.id == uuid.UUID(d["id"]))
            .values(beneficiary_account_id=pending.id)
        )
        if account_status == AccountStatus.RETIRED:
            s.execute(
                update(BankAccount)
                .where(BankAccount.id == pending.id)
                .values(status=account_status)
            )
    try:
        status, body = release(karim, ms)
        assert status == 409 and body["code"] == expected
        assert release_rows(d["id"]) == 0 and ms_status(ms) == MilestoneStatus.READY
        assert "TRANCHE_RELEASE_REFUSED" in audit_actions(d["id"])
    finally:
        with batch_session() as s:
            s.execute(
                update(BankAccount)
                .where(BankAccount.id == pending.id)
                .values(status=AccountStatus.PENDING_CHANGE)
            )


def test_release_refuses_a_blocked_supplier_and_a_foreign_account(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:
        s.execute(update(Party).where(Party.code == HUAXIN).values(kyb_status=KybStatus.FAILED))
    try:
        assert (
            code(karim.post(f"/milestones/{ms}/release", json={"idempotency_key": "blocked-0001"}))
            == "KYB_BLOCKED"
        )
    finally:
        with batch_session() as s:
            s.execute(
                update(Party).where(Party.code == HUAXIN).values(kyb_status=KybStatus.VERIFIED)
            )
    with batch_session() as s:
        other = s.scalars(
            select(BankAccount).where(
                BankAccount.party_id
                != s.scalars(select(Party.id).where(Party.code == HUAXIN)).one()
            )
        ).first()
        s.execute(
            update(Deal)
            .where(Deal.id == uuid.UUID(d["id"]))
            .values(beneficiary_account_id=other.id)
        )  # type: ignore[union-attr]
    assert (
        code(karim.post(f"/milestones/{ms}/release", json={"idempotency_key": "foreign-0001"}))
        == "BENEFICIARY_NOT_SUPPLIERS"
    )
    assert release_rows(d["id"]) == 0


def test_release_on_a_deal_that_is_not_active_is_refused(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with batch_session() as s:
        s.execute(update(Deal).where(Deal.id == uuid.UUID(d["id"])).values(status="DISPUTED"))
    assert (
        code(karim.post(f"/milestones/{ms}/release", json={"idempotency_key": "disputed-0001"}))
        == "DEAL_NOT_ACTIVE"
    )


# --- the risk-hook contract (Phase 5.1 plugs in here) -----------------------------------------


def fake(decision: RiskDecision, tier: int, *codes: str, seen: list[ReleaseContext] | None = None):  # type: ignore[no-untyped-def]
    def hook(action: RiskAction, ctx: ReleaseContext) -> RiskResult:
        assert action == RiskAction.RELEASE_TRANCHE
        if seen is not None:
            seen.append(ctx)
        return RiskResult(
            decision=decision,
            tier=tier,
            reasons=[RiskReason(code=c, message=f"because {c}") for c in codes],
        )

    return hook


def test_the_hook_receives_a_typed_context(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    seen: list[ReleaseContext] = []
    with risk_hook.use_hook(fake(RiskDecision.ALLOW, 1, seen=seen)):
        status, body = release(karim, ms)
    assert status == 200 and body["risk"]["tier"] == 1 and body["notice"]
    [ctx] = seen
    assert ctx.deal_ref == d["reference"] and ctx.milestone_seq == 1
    assert (ctx.amount, ctx.currency, ctx.amount_usd) == (
        Decimal("2880.00"),
        "USD",
        Decimal("2880.00"),
    )
    assert ctx.settlement_currency == "CNY" and ctx.fx_rate is not None
    assert ctx.beneficiary_status == "ACTIVE" and ctx.beneficiary_verified is True
    assert ctx.supplier_kyb_status == "VERIFIED" and ctx.evidence_status == "VERIFIED"
    assert ctx.escrow_balance == Decimal("2880.00") and ctx.advance_over_20k is False
    assert ctx.requested_by_role == "BUYER"
    assert ctx.model_config["extra"] == "forbid" and ctx.model_config["frozen"] is True


def request_approval(tier: int = 2) -> tuple[TestClient, dict[str, Any], str, dict[str, Any]]:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, tier, "FX_RATE_LOCK")):
        status, body = release(karim, ms, "approval-key-0001")
    assert status == 202, body
    return karim, d, ms, body


def test_require_approval_parks_the_tranche_and_moves_no_money(seeded_db: str) -> None:
    karim, d, ms, body = request_approval(2)
    assert body["outcome"] == "PENDING_APPROVAL" and body["ledger"] == []
    assert body["risk"]["decision"] == "REQUIRE_APPROVAL" and body["risk"]["tier"] == 2
    assert body["milestone"]["status"] == "PENDING_APPROVAL"
    assert body["milestone"]["can"]["can_release"]["allowed"] is False
    assert body["deal"]["can"]["can_release"]["reason"] == "Waiting for approval"
    appr = body["approval"]
    assert appr["tier"] == 2 and appr["status"] == "PENDING" and appr["otp_required"] is False
    assert appr["reasons"] == ["because FX_RATE_LOCK"]
    assert release_rows(d["id"]) == 0 and totals(d["id"])["balance"] == Decimal("2880")
    assert body["deal"]["escrow"]["status"] == "FUNDED"
    with batch_session() as s:
        row = s.get(ApprovalRequest, uuid.UUID(appr["id"]))
        assert row is not None
        assert row.action == ApprovalAction.RELEASE_MILESTONE and row.milestone_id == uuid.UUID(ms)
        assert row.params_hash == approval_binding_hash(
            action="RELEASE_MILESTONE", tier=2, deal_id=row.deal_id, milestone_id=row.milestone_id,
            bank_account_id=row.bank_account_id, params=row.params,
        )  # fmt: skip
        assert row.params["amount"] == "2880.00" and row.params["pay_currency"] == "CNY"
        assert row.bank_account_id is not None
    assert "RELEASE_APPROVAL_REQUESTED" in audit_actions(d["id"])
    # asking again (any key) does not create a second approval
    status, again = release(karim, ms, "approval-key-0002")
    assert status == 202 and again["idempotent_replay"] is True
    assert again["approval"]["id"] == appr["id"]
    with batch_session() as s:
        n = s.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.milestone_id == uuid.UUID(ms))
        )
        assert n == 1


def test_tier3_approval_has_otp_cooling_off_and_freezes_the_escrow(seeded_db: str) -> None:
    _, d, _, body = request_approval(3)
    appr = body["approval"]
    assert appr["tier"] == 3 and appr["otp_required"] is True and appr["cooling_off_until"]
    assert body["deal"]["escrow"]["status"] == "FROZEN"
    assert release_rows(d["id"]) == 0


def test_a_fail_closed_hook_is_normalised(seeded_db: str) -> None:
    low = risk_hook.normalise(RiskResult(decision=RiskDecision.REQUIRE_APPROVAL, tier=0))
    assert low.tier == 2
    high = risk_hook.normalise(RiskResult(decision=RiskDecision.ALLOW, tier=3))
    assert high.decision == RiskDecision.REQUIRE_APPROVAL
    ok = RiskResult(decision=RiskDecision.ALLOW, tier=1)
    assert risk_hook.normalise(ok) == ok
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.ALLOW, 3, "DOC_INSTRUCTION")):
        status, body = release(karim, ms)
    assert status == 202 and body["approval"]["tier"] == 3 and release_rows(d["id"]) == 0


def test_block_refuses_the_release(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.BLOCK, 3, "SANCTIONS")):
        status, body = release(karim, ms)
    assert (
        status == 409
        and body["code"] == "RELEASE_BLOCKED"
        and "because SANCTIONS" in body["detail"]
    )
    assert release_rows(d["id"]) == 0 and ms_status(ms) == MilestoneStatus.READY


def approve(approval_id: str, **changes: Any) -> None:
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(approval_id))
            .values(status=ApprovalStatus.APPROVED, **changes)
        )


def execute(ms: str, approval_id: str, hook: Any = None, key: str = "exec-key-0001") -> Any:
    with batch_session() as s:
        return escrow.release_tranche(
            s,
            uuid.UUID(ms),
            current_user_of(KARIM),
            key,
            approval_id=uuid.UUID(approval_id),
            hook=hook,
        )


def test_an_approved_release_executes_and_marks_the_approval_executed(seeded_db: str) -> None:
    _, d, ms, body = request_approval(2)
    aid = body["approval"]["id"]
    with pytest.raises(Conflict) as exc:
        execute(ms, aid, fake(RiskDecision.REQUIRE_APPROVAL, 2))
    assert exc.value.code == "APPROVAL_NOT_APPROVED", "still PENDING"
    approve(aid)
    out = execute(ms, aid, fake(RiskDecision.REQUIRE_APPROVAL, 2, "FX_RATE_LOCK"))
    assert out.outcome == "RELEASED" and len(out.ledger) == 2
    with batch_session() as s:
        assert s.get(ApprovalRequest, uuid.UUID(aid)).status == ApprovalStatus.EXECUTED  # type: ignore[union-attr]
    assert totals(d["id"])["released"] == Decimal("2880")
    again = execute(ms, aid, None, key="exec-key-0001")
    assert again.replay is True, "the approval cannot release twice"


def test_approval_execution_rechecks_binding_tier_and_cooling_off(seeded_db: str) -> None:
    from datetime import UTC, datetime, timedelta

    _, d, ms, body = request_approval(2)
    aid = body["approval"]["id"]
    approve(aid)
    soft = fake(RiskDecision.REQUIRE_APPROVAL, 2)

    with batch_session() as s:  # params changed after approval -> hash/params mismatch
        original = s.get(ApprovalRequest, uuid.UUID(aid)).params  # type: ignore[union-attr]
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(aid))
            .values(params={"amount": "1.00"})
        )
    with pytest.raises(Conflict) as e1:
        execute(ms, aid, soft)
    assert e1.value.code == "APPROVAL_PARAMS_CHANGED"
    with batch_session() as s:  # restore params, but break the stored binding hash
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(aid))
            .values(params=original, params_hash="0" * 64)
        )
    with pytest.raises(Conflict) as e2:
        execute(ms, aid, soft)
    assert e2.value.code == "APPROVAL_HASH_MISMATCH"
    with batch_session() as s:
        a = s.get(ApprovalRequest, uuid.UUID(aid))
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == a.id)  # type: ignore[union-attr]
            .values(
                params_hash=approval_binding_hash(
                    action="RELEASE_MILESTONE",
                    tier=2,
                    deal_id=a.deal_id,
                    milestone_id=a.milestone_id,  # type: ignore[union-attr]
                    bank_account_id=a.bank_account_id,
                    params=a.params,  # type: ignore[union-attr]
                )
            )
        )
    with pytest.raises(
        Conflict
    ) as e3:  # the engine now says tier 3: the old tier-2 approval is stale
        execute(ms, aid, fake(RiskDecision.REQUIRE_APPROVAL, 3))
    assert e3.value.code == "APPROVAL_TIER_STALE"
    with pytest.raises(Conflict) as e4:  # block at execution time
        execute(ms, aid, fake(RiskDecision.BLOCK, 3))
    assert e4.value.code == "RELEASE_BLOCKED"
    with batch_session() as s:
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == uuid.UUID(aid))
            .values(cooling_off_until=datetime.now(UTC) + timedelta(minutes=5))
        )
    with pytest.raises(Conflict) as e5:
        execute(ms, aid, soft)
    assert e5.value.code == "COOLING_OFF"
    assert release_rows(d["id"]) == 0
    other = funded_deal(as_user(KARIM))
    with pytest.raises(Conflict) as e6:  # an approval for another tranche is not valid here
        execute(other["milestones"][0]["id"], aid, soft, key="other-key-0001")
    assert e6.value.code in ("APPROVAL_MISMATCH", "EVIDENCE_NOT_VERIFIED")


def test_closing_an_approval_thaws_the_tranche_and_the_escrow(seeded_db: str) -> None:
    _, d, ms, body = request_approval(3)
    aid = uuid.UUID(body["approval"]["id"])
    with batch_session() as s:
        with pytest.raises(Conflict) as exc:
            escrow.release_approval_closed(s, aid)
        assert exc.value.code == "APPROVAL_STILL_OPEN"
        s.rollback()
        s.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == aid)
            .values(status=ApprovalStatus.REJECTED)
        )
        s.commit()
        escrow.release_approval_closed(s, aid)
    assert ms_status(ms) == MilestoneStatus.READY
    with batch_session() as s:
        e = s.scalars(
            select(EscrowAccount).where(EscrowAccount.deal_id == uuid.UUID(d["id"]))
        ).one()
        assert e.status == EscrowStatus.FUNDED


def test_an_open_approval_blocks_an_allow_decision(seeded_db: str) -> None:
    """The seeded Tier 2 approval for SETU-2026-0001 M1 stays authoritative: even with the
    placeholder ALLOW hook, no money moves past a human approval that is still open."""
    karim, admin, d = ready_deal()
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, 2)):
        assert release(karim, ms)[0] == 202
    with risk_hook.use_hook(fake(RiskDecision.ALLOW, 0)):
        status, body = release(karim, ms, "allow-key-0001")
    assert status == 202 and body["outcome"] == "PENDING_APPROVAL" and release_rows(d["id"]) == 0


# --- refunds ----------------------------------------------------------------------------------


def test_admin_refunds_a_tranche_and_the_invariant_holds(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    deal_id = d["id"]
    m1, m2, _ = (m["id"] for m in d["milestones"])
    verify_evidence(admin, m1)
    assert release(karim, m1)[0] == 200
    fund(karim, deal_id)  # M2 deposited and READY
    assert totals(deal_id)["balance"] == Decimal("5760")
    assert (
        karim.post(f"/milestones/{m2}/refund", json={"reason": "buyer asks nicely"}).status_code
        == 403
    )
    res = admin.post(f"/milestones/{m2}/refund", json={"reason": "Shipment never left port"})
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["refunded_amount"] == "5760.00"
    assert {x["kind"] for x in r["ledger"]} == {"REFUND"}
    assert r["ledger"][0]["account"].startswith("buyer:") and r["ledger"][1]["account"].startswith(
        "escrow:"
    )
    assert r["deal"]["status"] == "DISPUTED" and r["deal"]["dispute_count"] == 1
    assert [m["status"] for m in r["deal"]["milestones"]] == ["RELEASED", "REFUNDED", "PENDING"]
    e = r["deal"]["escrow"]
    assert (e["funded"], e["released"], e["refunded"], e["balance"]) == (
        "8640.00",
        "2880.00",
        "5760.00",
        "0.00",
    )
    assert e["status"] == "FROZEN" and e["invariant_ok"]
    assert totals(deal_id)["refunded"] == Decimal("5760")
    assert "ESCROW_REFUNDED" in audit_actions(deal_id)
    again = admin.post(f"/milestones/{m2}/refund", json={"reason": "second try"})
    assert again.status_code == 409
    assert (
        admin.post(f"/milestones/{m1}/refund", json={"reason": "already released"}).status_code
        == 409
    )


def test_refund_returns_cash_and_a_deal_refund_cancels_the_deal(seeded_db: str) -> None:
    from app.db.session import batch_session as bs

    give_cash("dhaka-stitch-works", "10000.00")
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim, amount=None)
    fund(karim, d["id"], "6720.00")  # fully funded, nothing released
    with bs() as s:
        cash = s.scalars(select(Party.cash_balance).where(Party.code == "dhaka-stitch-works")).one()
        assert cash == Decimal("400.00")
    assert (
        karim.post(f"/deals/{d['id']}/refund", json={"reason": "cancel please"}).status_code == 403
    )
    res = admin.post(f"/deals/{d['id']}/refund", json={"reason": "supplier ceased trading"})
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["refunded_amount"] == "9600.00" and r["deal"]["status"] == "CANCELLED"
    assert [m["status"] for m in r["deal"]["milestones"]] == ["REFUNDED", "REFUNDED", "REFUNDED"]
    assert r["deal"]["escrow"]["status"] == "REFUNDED" and r["deal"]["escrow"]["balance"] == "0.00"
    assert totals(d["id"])["refunded"] == Decimal("9600")
    with bs() as s:
        assert s.scalars(
            select(Party.cash_balance).where(Party.code == "dhaka-stitch-works")
        ).one() == Decimal("10000.00")
    assert (
        admin.post(f"/deals/{d['id']}/refund", json={"reason": "again please"}).status_code == 409
    )
    assert karim.get(f"/deals/{d['id']}/ledger").json()["balanced"] is True


def test_deal_refund_cancels_unfunded_tranches(seeded_db: str) -> None:
    _, admin, d = ready_deal()  # only M1 deposited
    res = admin.post(f"/deals/{d['id']}/refund", json={"reason": "buyer withdrew"})
    assert res.status_code == 200, res.text
    assert [m["status"] for m in res.json()["deal"]["milestones"]] == [
        "REFUNDED",
        "CANCELLED",
        "CANCELLED",
    ]
    assert res.json()["deal"]["escrow"]["invariant_ok"]


def test_refund_of_an_unfunded_deal_or_tranche_is_refused(seeded_db: str) -> None:
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = create(karim)
    propose(karim, d["id"])
    assert (
        admin.post(f"/deals/{d['id']}/refund", json={"reason": "nothing there"}).status_code == 409
    )
    d2 = funded_deal(karim)
    m3 = d2["milestones"][2]["id"]
    assert admin.post(f"/milestones/{m3}/refund", json={"reason": "not funded"}).status_code == 409


# --- flags ------------------------------------------------------------------------------------


def test_can_release_flags_follow_the_state(seeded_db: str) -> None:
    karim, admin, d = ready_deal()
    assert d["can"]["can_release"] == {
        "allowed": False,
        "reason": "The required evidence has not been verified yet",
    }
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    after = karim.get(f"/deals/{d['id']}").json()
    assert after["can"]["can_release"]["allowed"] is True
    assert after["milestones"][0]["can"]["can_release"]["allowed"] is True
    assert after["milestones"][1]["can"]["can_release"]["allowed"] is False
    assert after["can"]["can_refund"] == {"allowed": False, "reason": "Only an admin can refund"}
    adm = admin.get(f"/deals/{d['id']}").json()
    assert adm["viewer_role"] == "ADMIN" and adm["can"]["can_refund"]["allowed"] is True
    assert (
        adm["can"]["can_release"]["allowed"] is True and adm["can"]["can_fund"]["allowed"] is True
    )


def test_huameng_deal_passes_the_warning_to_the_hook(seeded_db: str) -> None:
    """A WARNING supplier is not refused by the escrow service; the risk engine decides."""
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = create(karim, HUAMENG)
    propose(karim, d["id"])
    confirmed(karim, None, d["id"])
    d = fund(karim, d["id"])
    ms = d["milestones"][0]["id"]
    verify_evidence(admin, ms)
    seen: list[ReleaseContext] = []
    with risk_hook.use_hook(fake(RiskDecision.REQUIRE_APPROVAL, 3, "KYB_WARNING", seen=seen)):
        status, _ = release(karim, ms)
    assert status == 202
    assert seen[0].supplier_kyb_status == "WARNING" and seen[0].beneficiary_verified is False
    assert seen[0].settlement_currency in ("CNY", "USD")


def test_rahima_and_the_supplier_user_use_the_same_endpoints(seeded_db: str) -> None:
    rahima = as_user(RAHIMA)
    d = funded_deal(rahima, amount="2880.00")
    assert d["buyer_name"].startswith("Rahima")
    assert as_user(HUAXIN_USER).get(f"/deals/{d['id']}").status_code == 200
