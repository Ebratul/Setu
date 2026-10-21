"""The money tools are propose-only: they call the services with origin AGENT, so the result is
always an ApprovalRequest (or a block) and nothing moves."""

import uuid

from app.agent.registry import INTENT_TOOLS, ToolContext, default_registry
from app.auth.deps import CurrentUser
from app.db.enums import Role
from app.security.tiers import Tier

PROPOSE = {
    "propose_release_tranche",
    "propose_milestones",
    "propose_confirm_milestones",
    "propose_fund_escrow",
    "propose_fx_lock",
    "propose_change_beneficiary",
}


def ctx() -> ToolContext:
    user = CurrentUser(uuid.uuid4(), "b@demo.setu", "B", Role.BUYER, "en", uuid.uuid4())
    return ToolContext(caller="llm", user=user, db=None)


def test_propose_tools_are_tier0_and_reachable_from_deal_chat_only() -> None:
    reg = default_registry()
    for name in PROPOSE:
        assert reg.get(name).max_tier == Tier.T0  # type: ignore[union-attr]
    offered = {n for intent, names in INTENT_TOOLS.items() if PROPOSE & names for n in [intent]}
    assert offered == {"deal_status"}


def test_a_propose_tool_without_a_database_fails_closed() -> None:
    reg = default_registry()
    out = reg.guard(
        "propose_fx_lock",
        {"deal_id": "SETU-2026-0001"},
        ctx(),
        allowed=frozenset({"propose_fx_lock"}),
    )
    assert out.ok is False and out.error is not None
    assert out.error["code"] == "unavailable"


def test_propose_arguments_cannot_smuggle_a_tier_or_approval() -> None:
    reg = default_registry()
    out = reg.guard(
        "propose_fx_lock",
        {"deal_id": "SETU-2026-0001", "tier": 0, "approved": True},
        ctx(),
        allowed=frozenset({"propose_fx_lock"}),
    )
    assert out.ok is False  # extra="forbid": rejected before the service is reached
