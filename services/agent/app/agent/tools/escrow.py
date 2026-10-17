"""Escrow actions that exist in the registry only so the guard can REFUSE them from chat.

`propose_milestones` (schedule create/change, Tier 2) and `release_tranche` (Tier 3 ceiling) are
human actions behind `/deals/...` and `/milestones/...` endpoints. They are registered above the LLM
tier ceiling, are in no intent allow-list, and `ToolRegistry.llm_tools` hides them from the model.
If the model asks for one anyway, `guard()` returns `requires_approval_flow` before anything runs;
the function bodies below refuse too, so they cannot be run even by a mis-wired caller.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.registry import ToolContext, ToolError
from app.agent.tools.finance import DealId
from app.agent.tools.readonly import REGISTRY
from app.security.tiers import Tier


class ProposeMilestonesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_id: DealId
    template: Literal["30/60/10", "custom"] = "30/60/10"


class ReleaseTrancheIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    milestone_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")


class EscrowActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulated: Literal[True] = True
    message: str


def _refuse(name: str) -> ToolError:
    return ToolError(
        "requires_approval_flow",
        f"'{name}' is done by a person in the Setu app, not by the assistant.",
    )


@REGISTRY.tool(
    name="propose_milestones",
    tier=Tier.T2,
    args_schema=ProposeMilestonesIn,
    output_schema=EscrowActionOut,
    tags=("escrow", "human-only"),
)
def propose_milestones(args: ProposeMilestonesIn, ctx: ToolContext) -> EscrowActionOut:
    """Propose a milestone payment schedule for a deal. Human-only (Tier 2)."""
    raise _refuse("propose_milestones")


@REGISTRY.tool(
    name="release_tranche",
    tier=Tier.T3,
    args_schema=ReleaseTrancheIn,
    output_schema=EscrowActionOut,
    tags=("escrow", "human-only"),
)
def release_tranche(args: ReleaseTrancheIn, ctx: ToolContext) -> EscrowActionOut:
    """Release an escrow tranche to the supplier. Human-only (up to Tier 3)."""
    raise _refuse("release_tranche")


__all__ = ["propose_milestones", "release_tranche"]
