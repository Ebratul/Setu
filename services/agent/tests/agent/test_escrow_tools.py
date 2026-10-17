"""The two escrow actions are registered above the LLM tier ceiling so the guard refuses them
from chat; they never execute and are never offered to the model."""

import uuid

import pytest

from app.agent.registry import INTENT_TOOLS, ToolContext, default_registry
from app.auth.deps import CurrentUser
from app.db.enums import Role
from app.security import audit
from app.security.tiers import MAX_LLM_TOOL_TIER, Tier

ARGS = {
    "propose_milestones": {"deal_id": "SETU-2026-0001", "template": "30/60/10"},
    "release_tranche": {"milestone_id": str(uuid.uuid4()), "idempotency_key": "chat-key-0001"},
}


def ctx() -> ToolContext:
    user = CurrentUser(uuid.uuid4(), "b@demo.setu", "B", Role.BUYER, "en", uuid.uuid4())
    return ToolContext(caller="llm", user=user, db=None)


def test_escrow_tools_are_registered_above_the_llm_ceiling() -> None:
    reg = default_registry()
    assert reg.get("propose_milestones").max_tier == Tier.T2  # type: ignore[union-attr]
    assert reg.get("release_tranche").max_tier == Tier.T3  # type: ignore[union-attr]
    assert all(reg.get(n).max_tier > MAX_LLM_TOOL_TIER for n in ARGS)  # type: ignore[union-attr]


@pytest.mark.parametrize("name", sorted(ARGS))
def test_guard_refuses_them_from_chat_before_anything_runs(name: str) -> None:
    reg = default_registry()
    before = len(audit.RECENT_EVENTS)
    out = reg.guard(name, ARGS[name], ctx(), allowed=frozenset({name}))
    assert out.ok is False and out.error is not None
    assert out.error["code"] == "requires_approval_flow"
    assert out.error["tier"] == int(reg.get(name).max_tier)  # type: ignore[union-attr]
    assert any(
        e["result"] == "REFUSED:requires_approval_flow" for e in list(audit.RECENT_EVENTS)[before:]
    )


@pytest.mark.parametrize("name", sorted(ARGS))
def test_even_a_mis_wired_call_cannot_run_the_function(name: str) -> None:
    from app.agent.registry import ToolError

    spec = default_registry().get(name)
    assert spec is not None
    parsed = spec.args_schema.model_validate(ARGS[name])
    with pytest.raises(ToolError) as exc:
        spec.fn(parsed, ctx())
    assert exc.value.code == "requires_approval_flow"


def test_they_are_in_no_intent_allowlist_and_hidden_from_the_model() -> None:
    reg = default_registry()
    for intent, names in INTENT_TOOLS.items():
        assert not set(ARGS) & names, intent
        assert not set(ARGS) & set(reg.llm_tools(names))
    assert not set(ARGS) & set(reg.llm_tools(frozenset(reg.names)))
    defs = {d["name"] for d in reg.definitions(reg.llm_tools(frozenset(reg.names)))}
    assert not set(ARGS) & defs


def test_unlisted_calls_are_also_refused_by_allowlist() -> None:
    reg = default_registry()
    out = reg.guard("release_tranche", ARGS["release_tranche"], ctx(), allowed=frozenset())
    assert out.error is not None and out.error["code"] == "requires_approval_flow"
