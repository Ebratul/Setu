"""Money "propose" tools (Phase 5.1). The agent may ASK for a money action; it can never DO one.

Each tool calls the same service the HTTP endpoint calls, with `origin=AGENT`. The risk engine
treats an agent origin as Tier 2 at least, so the service answers with an `ApprovalRequest` and
nothing moves; only a person's approval (an HTTP endpoint, Phase 17) executes it, and an
`approval_id` is refused for a non-human origin. The tools are Tier 0 because their only effect is
to queue a request for a human; the tier lives in the service, not in a prompt.
"""

import uuid
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.persistence import resolve_deal
from app.agent.registry import ToolContext, ToolError
from app.agent.tools.finance import DealId, _db
from app.agent.tools.readonly import REGISTRY
from app.db.models import ApprovalRequest, Milestone
from app.errors import DomainError, NotFound
from app.schemas.deals import ProposeRequest
from app.security.tiers import Tier
from app.services import beneficiary, deals, escrow, fx_lock
from app.services.risk.engine import Origin
from app.services.risk.gate import ApprovalPending, RiskBlocked

Amount = Field(default=None, max_length=24, pattern=r"^\d{1,16}(\.\d{1,2})?$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposeReleaseIn(Strict):
    milestone_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    idempotency_key: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")


class ProposeMilestonesIn(Strict):
    deal_id: DealId
    template: Literal["30/60/10"] = "30/60/10"


class ProposeConfirmIn(Strict):
    deal_id: DealId


class ProposeAmountIn(Strict):
    deal_id: DealId
    amount: str | None = Amount


class ProposeBeneficiaryIn(Strict):
    deal_id: DealId
    bank_account_id: str = Field(min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")


class ProposalOut(Strict):
    """What the agent may say: the request was queued (or refused). Nothing here is an action."""

    simulated: Literal[True] = True
    status: Literal["SENT_FOR_APPROVAL", "BLOCKED"]
    action: str
    tier: int
    reasons: list[str]
    approval_id: str | None
    message: str


def _sent(action: str, approval: ApprovalRequest) -> ProposalOut:
    return ProposalOut(
        status="SENT_FOR_APPROVAL",
        action=action,
        tier=approval.tier,
        reasons=[str(r.get("message") or r.get("code")) for r in approval.reasons],
        approval_id=str(approval.id),
        message=(
            f"I've sent this for your approval (Tier {approval.tier}). Nothing has moved yet; "
            "you can review it under Approvals."
        ),
    )


def _blocked(action: str, exc: RiskBlocked) -> ProposalOut:
    return ProposalOut(
        status="BLOCKED",
        action=action,
        tier=3,
        reasons=[exc.detail],
        approval_id=None,
        message="The risk checks blocked this request, so it was not sent for approval.",
    )


def _propose(action: str, run: Callable[[], ProposalOut]) -> ProposalOut:
    try:
        return run()
    except ApprovalPending as pending:
        return _sent(action, pending.approval)
    except RiskBlocked as blocked:
        return _blocked(action, blocked)
    except NotFound as exc:
        raise ToolError("not_found", exc.detail) from exc
    except DomainError as exc:
        raise ToolError(exc.code or "refused", exc.detail) from exc


def _amount(value: str | None) -> Decimal | None:
    try:
        return None if value is None else Decimal(value)
    except InvalidOperation as exc:
        raise ToolError("invalid_amount", "the amount is not a number") from exc


def _never_executed(action: str) -> ToolError:
    # Unreachable by construction (the engine makes an agent origin Tier 2+); fail loudly if not.
    return ToolError("unexpected_execution", f"'{action}' did not wait for approval")


@REGISTRY.tool(
    name="propose_release_tranche",
    tier=Tier.T0,
    args_schema=ProposeReleaseIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_release_tranche(args: ProposeReleaseIn, ctx: ToolContext) -> ProposalOut:
    """Ask for an escrow tranche to be released to the supplier. This only sends the request to
    the user's approvals; a person must approve it and nothing moves until then."""
    db = _db(ctx)

    def run() -> ProposalOut:
        try:
            ms = db.get(Milestone, uuid.UUID(args.milestone_id))
        except ValueError as exc:
            raise NotFound("milestone not found") from exc
        if ms is None:
            raise NotFound("milestone not found")
        resolve_deal(db, ctx.user, str(ms.deal_id))  # foreign deals look missing
        out = escrow.release_tranche(db, ms.id, ctx.user, args.idempotency_key, origin=Origin.AGENT)
        if out.outcome != "PENDING_APPROVAL" or out.approval is None:
            raise _never_executed("release_tranche")
        return _sent("release_tranche", out.approval)

    return _propose("release_tranche", run)


@REGISTRY.tool(
    name="propose_milestones",
    tier=Tier.T0,
    args_schema=ProposeMilestonesIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_milestones(args: ProposeMilestonesIn, ctx: ToolContext) -> ProposalOut:
    """Ask for the standard 30/60/10 milestone schedule to be created for a deal. This only sends
    the request to the user's approvals."""
    db = _db(ctx)

    def run() -> ProposalOut:
        deal = resolve_deal(db, ctx.user, args.deal_id)
        deals.propose_milestones(
            db, ctx.user, deal.id, ProposeRequest(template=args.template), origin=Origin.AGENT
        )
        raise _never_executed("propose_milestones")

    return _propose("propose_milestones", run)


@REGISTRY.tool(
    name="propose_confirm_milestones",
    tier=Tier.T0,
    args_schema=ProposeConfirmIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_confirm_milestones(args: ProposeConfirmIn, ctx: ToolContext) -> ProposalOut:
    """Ask for the user's side of the milestone schedule to be confirmed. This only sends the
    request to the user's approvals."""
    db = _db(ctx)

    def run() -> ProposalOut:
        deal = resolve_deal(db, ctx.user, args.deal_id)
        deals.confirm_milestones(db, ctx.user, deal.id, None, origin=Origin.AGENT)
        raise _never_executed("confirm_milestones")

    return _propose("confirm_milestones", run)


@REGISTRY.tool(
    name="propose_fund_escrow",
    tier=Tier.T0,
    args_schema=ProposeAmountIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_fund_escrow(args: ProposeAmountIn, ctx: ToolContext) -> ProposalOut:
    """Ask for a deposit into a deal's escrow. This only sends the request to the user's
    approvals; omit the amount for the next tranche."""
    db = _db(ctx)

    def run() -> ProposalOut:
        deal = resolve_deal(db, ctx.user, args.deal_id)
        escrow.fund_escrow(db, ctx.user, deal.id, _amount(args.amount), origin=Origin.AGENT)
        raise _never_executed("fund_escrow")

    return _propose("fund_escrow", run)


@REGISTRY.tool(
    name="propose_fx_lock",
    tier=Tier.T0,
    args_schema=ProposeAmountIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_fx_lock(args: ProposeAmountIn, ctx: ToolContext) -> ProposalOut:
    """Ask for today's FX rate to be locked for a deal. This only sends the request to the
    user's approvals."""
    db = _db(ctx)

    def run() -> ProposalOut:
        deal = resolve_deal(db, ctx.user, args.deal_id)
        out = fx_lock.lock_fx(db, ctx.user, deal.id, _amount(args.amount), origin=Origin.AGENT)
        if out.outcome != "PENDING_APPROVAL" or out.approval is None:
            raise _never_executed("lock_fx")
        return _sent("lock_fx", out.approval)

    return _propose("lock_fx", run)


@REGISTRY.tool(
    name="propose_change_beneficiary",
    tier=Tier.T0,
    args_schema=ProposeBeneficiaryIn,
    output_schema=ProposalOut,
    tags=("escrow", "propose"),
)
def propose_change_beneficiary(args: ProposeBeneficiaryIn, ctx: ToolContext) -> ProposalOut:
    """Ask for a deal's receiving bank account to be changed. Always the strictest approval
    (OTP and cooling-off); this only sends the request."""
    db = _db(ctx)

    def run() -> ProposalOut:
        deal = resolve_deal(db, ctx.user, args.deal_id)
        out = beneficiary.change_beneficiary(
            db, ctx.user, deal.id, uuid.UUID(args.bank_account_id), origin=Origin.AGENT
        )
        if out.outcome != "PENDING_APPROVAL" or out.approval is None:
            raise _never_executed("change_beneficiary")
        return _sent("change_beneficiary", out.approval)

    return _propose("change_beneficiary", run)


__all__ = ["ProposalOut"]
