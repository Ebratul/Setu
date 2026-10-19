"""Pure rule tests for the deterministic tier engine (no DB). SR-1, TC-07."""

from decimal import Decimal

import pytest

from app.security.policy import load_policy
from app.security.risk_hook import RiskDecision as Verdict
from app.services.risk.engine import Action, Origin, RiskContext, evaluate


def ctx(**over: object) -> RiskContext:
    base: dict[str, object] = dict(
        action=Action.RELEASE_TRANCHE,
        amount=Decimal("5760"),
        currency="USD",
        amount_usd=Decimal("5760"),
        buyer_id="b",
        supplier_id="s",
        is_first_deal_with_supplier=False,
    )
    return RiskContext(**{**base, **over})  # type: ignore[arg-type]


def decide(**over: object) -> tuple[Verdict, int, list[str]]:
    d = evaluate(ctx(**over))
    return d.decision, d.tier, d.reason_codes


def test_clean_repeat_release_is_tier1_auto() -> None:
    assert decide() == (Verdict.ALLOW, 1, [])


def test_tc07_twenty_two_thousand_is_tier3() -> None:
    assert decide(amount=Decimal("22000"), amount_usd=Decimal("22000")) == (
        Verdict.REQUIRE_APPROVAL,
        3,
        ["AMOUNT_OVER_LIMIT"],
    )


@pytest.mark.parametrize(
    ("usd", "tier"), [("20000", 1), ("20000.00", 1), ("20000.0000001", 3), ("20000.01", 3)]
)
def test_the_limit_is_strict_on_the_unrounded_amount(usd: str, tier: int) -> None:
    assert decide(amount_usd=Decimal(usd))[1] == tier


def test_first_deal_is_tier2_and_second_deal_tier1() -> None:
    assert decide(is_first_deal_with_supplier=True) == (
        Verdict.REQUIRE_APPROVAL,
        2,
        ["FIRST_DEAL"],
    )
    assert decide(is_first_deal_with_supplier=False)[:2] == (Verdict.ALLOW, 1)


@pytest.mark.parametrize(
    "over",
    [
        {"beneficiary_status": "PENDING_CHANGE"},
        {"beneficiary_changed_recently": True},
        {"max_document_fraud_score": 72},
        {"duplicate_hash": True},
        {"instruction_from_document": True},
        {"kyb_status": "WARNING", "kyb_account_warning": True},
        {"advance_over_limit": True},
    ],
)
def test_tier3_triggers(over: dict[str, object]) -> None:
    decision, tier, reasons = decide(**over)
    assert (decision, tier) == (Verdict.REQUIRE_APPROVAL, 3) and reasons


def test_fraud_score_boundary_is_strict() -> None:
    assert decide(max_document_fraud_score=60)[1] == 1
    assert decide(max_document_fraud_score=61)[1] == 3


@pytest.mark.parametrize(
    "over",
    [
        {"sanctions_hit": True},
        {"kyb_status": "BLOCKED"},
        {"beneficiary_status": "BLOCKED"},
        {"any_document_failed": True},
    ],
)
def test_block_rules(over: dict[str, object]) -> None:
    decision, _tier, reasons = decide(**over)
    assert decision == Verdict.BLOCK and reasons


def test_block_beats_every_tier_and_the_highest_tier_beats_lower_ones() -> None:
    d = evaluate(ctx(sanctions_hit=True, duplicate_hash=True, is_first_deal_with_supplier=True))
    assert d.decision == Verdict.BLOCK and d.reason_codes == ["SANCTIONS_HIT"]
    d = evaluate(
        ctx(duplicate_hash=True, is_first_deal_with_supplier=True, any_document_warning=True)
    )
    assert d.tier == 3 and d.reason_codes[0] == "DUPLICATE_HASH"
    assert set(d.reason_codes) == {"DUPLICATE_HASH", "FIRST_DEAL", "DOCUMENT_WARNING"}


def test_document_warning_is_tier2_and_kyb_warning_without_account_reason_too() -> None:
    assert decide(any_document_warning=True)[:2] == (Verdict.REQUIRE_APPROVAL, 2)
    assert decide(kyb_status="WARNING")[:2] == (Verdict.REQUIRE_APPROVAL, 2)
    assert decide(beneficiary_verified=False)[:2] == (Verdict.REQUIRE_APPROVAL, 2)


@pytest.mark.parametrize("action", [a for a in Action if a != Action.ANALYSIS])
def test_agent_origin_never_yields_auto_execution(action: Action) -> None:
    d = evaluate(ctx(action=action, origin=Origin.AGENT))
    assert d.decision != Verdict.ALLOW and d.tier >= 2


def test_lock_fx_confirm_and_propose_are_tier2_for_a_person() -> None:
    for action in (Action.LOCK_FX, Action.CONFIRM_MILESTONES, Action.PROPOSE_MILESTONES):
        d = evaluate(ctx(action=action))
        assert (d.decision, d.tier, d.reason_codes) == (
            Verdict.REQUIRE_APPROVAL,
            2,
            [action.value],
        )


def test_change_beneficiary_is_always_tier3() -> None:
    d = evaluate(ctx(action=Action.CHANGE_BENEFICIARY, beneficiary_status="PENDING_CHANGE"))
    assert (d.decision, d.tier) == (Verdict.REQUIRE_APPROVAL, 3)
    assert "BENEFICIARY_CHANGE" in d.reason_codes


def test_fund_escrow_only_applies_block_and_origin_rules() -> None:
    big = dict(action=Action.FUND_ESCROW, amount_usd=Decimal("90000"), duplicate_hash=True)
    assert evaluate(ctx(**big)).decision == Verdict.ALLOW
    assert evaluate(ctx(**big, sanctions_hit=True)).decision == Verdict.BLOCK
    assert evaluate(ctx(**big, origin=Origin.AGENT)).tier == 2


def test_analysis_is_tier0() -> None:
    d = evaluate(ctx(action=Action.ANALYSIS, sanctions_hit=True))
    assert (d.decision, d.tier) == (Verdict.ALLOW, 0)


def test_deterministic_and_context_hash_changes_with_the_context() -> None:
    a, b = evaluate(ctx()), evaluate(ctx())
    assert a == b and len(a.context_hash) == 64
    assert evaluate(ctx(duplicate_hash=True)).context_hash != a.context_hash


def test_explanations_exist_in_english_and_bangla() -> None:
    d = evaluate(ctx(duplicate_hash=True))
    assert d.explanation_en.startswith("Needs Tier 3 approval") and d.explanation_bn


def test_context_rejects_client_supplied_tier_or_approved() -> None:
    with pytest.raises(ValueError):
        RiskContext(action=Action.RELEASE_TRANCHE, tier=0)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        RiskContext(action=Action.RELEASE_TRANCHE, approved=True)  # type: ignore[call-arg]


def test_thresholds_come_from_the_yaml() -> None:
    p = load_policy()
    assert p.tier1_max_usd == Decimal("20000") and p.fraud_score_tier3_above == 60
    assert p.new_beneficiary_days == 30 and p.cooling_off_minutes == 10


def test_rule_trace_shows_every_applicable_rule_the_value_and_the_deciding_rule() -> None:
    d = evaluate(ctx(amount=Decimal("22000"), amount_usd=Decimal("22000")))
    by = {t.code: t for t in d.trace}
    amount = by["AMOUNT_OVER_LIMIT"]
    assert amount.fired and amount.deciding
    assert amount.value_en == "Amount USD 22,000 vs limit USD 20,000"
    assert not by["DUPLICATE_HASH"].fired and not by["DUPLICATE_HASH"].deciding
    assert "BENEFICIARY_CHANGE" not in by  # does not apply to a release
    assert d.decided_by == ["AMOUNT_OVER_LIMIT"]
    assert all(t.label_bn and t.value_bn for t in d.trace)


def test_trace_marks_only_the_top_tier_rules_as_deciding() -> None:
    d = evaluate(ctx(duplicate_hash=True, is_first_deal_with_supplier=True))
    deciding = {t.code for t in d.trace if t.deciding}
    assert deciding == {"DUPLICATE_HASH"}
    assert {t.code for t in d.trace if t.fired} == {"DUPLICATE_HASH", "FIRST_DEAL"}


def test_hints_are_counterfactuals_for_fired_rules() -> None:
    d = evaluate(ctx(is_first_deal_with_supplier=True, any_document_warning=True))
    texts = {h.code: h for h in d.hints}
    assert texts["FIRST_DEAL"].to_tier == 1 and "one completed deal" in texts["FIRST_DEAL"].text_en
    assert "Upload" in texts["DOCUMENT_WARNING"].text_en and texts["DOCUMENT_WARNING"].text_bn
    blocked = evaluate(ctx(sanctions_hit=True))
    assert blocked.hints[0].to_tier is None and blocked.decided_by == ["SANCTIONS_HIT"]
    assert evaluate(ctx()).hints == []


def test_the_policy_table_lists_every_rule_with_both_languages() -> None:
    from app.services.risk.engine import rules_table

    rows = {r.code: r for r in rules_table()}
    assert rows["AMOUNT_OVER_LIMIT"].kind == "TIER3"
    assert "20,000" in rows["AMOUNT_OVER_LIMIT"].condition_en
    assert rows["SANCTIONS_HIT"].kind == "BLOCK" and rows["FIRST_DEAL"].kind == "TIER2"
    assert all(r.condition_bn and r.label_bn for r in rows.values())
