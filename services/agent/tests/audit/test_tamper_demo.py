"""POST /audit/tamper-demo: edit, delete or reorder a COPY of the chain and show where
verification breaks, while the real table stays byte-identical."""

# ruff: noqa: F811  (pytest fixtures imported by name)

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select

from app.db.models import AuditLog
from app.db.session import batch_session
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.api.deals_support import ADMIN, HUAXIN_USER, JUDGE, KARIM, RAHIMA, as_user

pytestmark = pytest.mark.db


def snapshot() -> tuple[list[tuple[Any, ...]], int]:
    with batch_session() as s:
        rows = s.execute(
            select(AuditLog.seq, AuditLog.entry_hash, AuditLog.payload_hash, AuditLog.signature)
            .order_by(AuditLog.seq)
        ).all()  # fmt: skip
        count = s.scalar(select(func.count()).select_from(AuditLog))
    return [tuple(r) for r in rows], count or 0


@pytest.fixture(scope="module")
def target(seeded_db: str) -> int:
    """A mid-chain ESCROW_FUNDED entry (the seed has no 5760.00 one), with room on both sides."""
    with batch_session() as s:
        head = s.scalar(select(func.max(AuditLog.seq))) or 0
        seq = s.scalars(
            select(AuditLog.seq)
            .where(AuditLog.action == "ESCROW_FUNDED", AuditLog.seq > 13, AuditLog.seq < head - 3)
            .order_by(AuditLog.seq)
        ).first()
    assert seq is not None
    return seq


def amount_of(seq: int) -> str:
    with batch_session() as s:
        return s.get(AuditLog, seq).payload["amount"]  # type: ignore[union-attr,no-any-return]


def demo(body: dict[str, Any], who: str = JUDGE) -> Any:
    return as_user(who).post("/audit/tamper-demo", json=body)


def test_editing_an_amount_breaks_the_chain_at_exactly_that_seq(target: int) -> None:
    before = snapshot()
    wrong = str(Decimal(amount_of(target)) * 10)
    res = demo({"mode": "edit", "seq": target, "field": "amount", "value": wrong})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["simulated"] is True and out["real_table_changed"] is False
    assert out["report"]["ok"] is False
    assert (out["report"]["broken_seq"], out["report"]["reason"]) == (target, "hash_mismatch")
    shown = next(e for e in out["entries"] if e["seq"] == target)
    assert shown["payload"]["amount"] == wrong != amount_of(target)
    assert snapshot() == before


def test_deleting_an_entry_reports_the_missing_seq(target: int) -> None:
    before = snapshot()
    out = demo({"mode": "delete", "seq": target, "window_from": target - 3}).json()
    assert out["report"]["ok"] is False
    assert (out["report"]["broken_seq"], out["report"]["reason"]) == (target, "missing_seq")
    assert target not in [e["seq"] for e in out["entries"]]
    assert out["real_table_changed"] is False and snapshot() == before


def test_reordering_two_entries_reports_reordered_at_the_first_swapped_seq(target: int) -> None:
    before = snapshot()
    out = demo({"mode": "reorder", "seq": target, "other_seq": target + 1}).json()
    assert out["report"]["ok"] is False
    assert (out["report"]["broken_seq"], out["report"]["reason"]) == (target, "reordered")
    assert snapshot() == before


def test_editing_a_top_level_field_also_breaks_at_that_seq(target: int) -> None:
    out = demo({"mode": "edit", "seq": target, "field": "decision", "value": "REFUNDED"}).json()
    assert (out["report"]["broken_seq"], out["report"]["reason"]) == (target, "hash_mismatch")


def test_downgrading_the_tier_is_detected(target: int) -> None:
    out = demo({"mode": "edit", "seq": target, "field": "tier", "value": "0"}).json()
    assert out["report"]["ok"] is False and out["report"]["broken_seq"] == target


def test_the_real_chain_still_verifies_after_every_demo(target: int) -> None:
    demo({"mode": "edit", "seq": target, "field": "amount", "value": "1.00"})
    body = as_user(ADMIN).get("/audit/verify").json()
    assert body["ok"] is True and body["broken_seq"] is None


def test_an_edit_that_changes_nothing_in_the_copy_verifies(target: int) -> None:
    with batch_session() as s:
        same = s.get(AuditLog, target).payload["amount"]  # type: ignore[union-attr]
    out = demo({"mode": "edit", "seq": target, "field": "amount", "value": same}).json()
    assert out["report"]["ok"] is True and out["report"]["broken_seq"] is None


@pytest.mark.parametrize("who", [RAHIMA, KARIM, HUAXIN_USER])
def test_buyers_and_suppliers_get_403(target: int, who: str) -> None:
    before = snapshot()
    res = demo({"mode": "delete", "seq": target}, who=who)
    assert res.status_code == 403
    assert snapshot() == before


def test_unauthenticated_gets_401(target: int) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    res = TestClient(create_app()).post("/audit/tamper-demo", json={"mode": "delete", "seq": 2})
    assert res.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "edit", "seq": 20},  # no field/value
        {"mode": "edit", "seq": 20, "field": "tier", "value": "high"},
        {"mode": "delete", "seq": 99999999},  # outside the window
        {"mode": "reorder", "seq": 20, "other_seq": 99999999},
    ],
    ids=["edit-no-field", "tier-not-number", "seq-outside-window", "other-seq-outside"],
)
def test_bad_input_is_a_400_with_the_bad_tamper_code(body: dict[str, Any]) -> None:
    res = demo(body)
    assert res.status_code == 400, res.text
    assert res.json()["code"] == "BAD_TAMPER"


@pytest.mark.parametrize(
    "body",
    [{"mode": "explode", "seq": 3}, {"mode": "delete", "seq": 0}, {"mode": "delete"}],
    ids=["unknown-mode", "seq-zero", "no-seq"],
)
def test_malformed_request_is_422(body: dict[str, Any]) -> None:
    assert demo(body).status_code == 422
