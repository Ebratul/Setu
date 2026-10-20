"""Dry-run, policy and overview endpoints (judge-facing risk views)."""

import pytest
from sqlalchemy import func, select

from app.db.models import RiskEvent
from app.db.session import batch_session
from tests.api.deals_support import ADMIN, JUDGE, KARIM, as_user

pytestmark = pytest.mark.db


def count_events() -> int:
    with batch_session() as s:
        return s.scalar(select(func.count()).select_from(RiskEvent)) or 0


def test_dry_run_calls_the_real_engine_and_saves_nothing(seeded_db: str) -> None:
    judge = as_user(JUDGE)
    before = count_events()
    res = judge.post("/risk/evaluate", json={"amount_usd": "22000"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["decision"], body["tier"], body["dry_run"], body["saved"]) == (
        "REQUIRE_APPROVAL",
        3,
        True,
        False,
    )
    assert any(t["code"] == "AMOUNT_OVER_LIMIT" and t["deciding"] for t in body["trace"])
    assert count_events() == before
    block = judge.post("/risk/evaluate", json={"sanctions_hit": True}).json()
    assert block["decision"] == "BLOCK"
    clean = judge.post("/risk/evaluate", json={}).json()
    assert (clean["decision"], clean["tier"]) == ("ALLOW", 1)


def test_dry_run_has_no_way_to_pass_a_tier(seeded_db: str) -> None:
    res = as_user(KARIM).post("/risk/evaluate", json={"tier": 0, "approved": True})
    assert res.status_code == 422


def test_policy_view_lists_the_yaml_and_the_rules(seeded_db: str) -> None:
    body = as_user(KARIM).get("/risk/policy").json()
    assert body["source"] == "config/risk.yaml" and "tier1_max_usd" in body["yaml"]
    assert body["tier1_max_usd"] == "20000" and body["cooling_off_minutes"] == 10
    assert {"BLOCK", "TIER3", "TIER2"} == {r["kind"] for r in body["rules"]}


def test_overview_is_for_admins_and_judges_only(seeded_db: str) -> None:
    assert as_user(KARIM).get("/risk/overview").status_code == 403
    for email in (ADMIN, JUDGE):
        res = as_user(email).get("/risk/overview")
        assert res.status_code == 200, res.text
        body = res.json()
        assert set(body["counters"]) == {"auto_released", "one_tap", "otp_required", "blocked"}
        assert len(body["series"]) == 15
