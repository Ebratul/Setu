"""Service-level enforcement of the risk engine for every money action except the release path
(which has its own, older checks in `services/escrow.release_tranche` and shares `record`/`notify`).

`run_gate` is called INSIDE the service, after it loaded the context from the DB and locked the
deal row. Nothing here reads a tier or an "approved" flag from a request.

- ALLOW (Tier 0/1): the caller executes.
- REQUIRE_APPROVAL (Tier 2/3): an `ApprovalRequest` is created (or the open identical one is
  returned, so two racing requests make one) and nothing moves. A person's own click on
  `inline_tier2_actions` (config/risk.yaml) is the one-tap and executes inline; the agent can only
  ever get an `ApprovalRequest`.
- BLOCK: refused with the reasons, a FRAUD alert and an audit row.
- `approval_id` (Python-level, for the human approval endpoint of Phase 17): the approval must be
  APPROVED, bound to these exact params, not stale in tier and past its cooling-off.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import CurrentUser
from app.db.enums import (
    Actor,
    AlertStatus,
    AlertType,
    ApprovalAction,
    ApprovalStatus,
    Severity,
)
from app.db.models import Alert, ApprovalRequest, Deal, RiskEvent
from app.errors import Conflict
from app.security.approvals import approval_binding_hash
from app.security.policy import load_policy
from app.security.risk_hook import RiskDecision as Verdict
from app.services import approval_otp
from app.services.risk import engine
from app.services.risk.engine import Action, Origin, RiskContext

log = structlog.get_logger("setu.risk")
OPEN = (ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
OWN_REASON = {
    Action.LOCK_FX: "LOCK_FX",
    Action.CONFIRM_MILESTONES: "CONFIRM_MILESTONES",
    Action.PROPOSE_MILESTONES: "PROPOSE_MILESTONES",
}


class RiskBlocked(Conflict):
    """The engine said BLOCK. `code` is RISK_BLOCKED."""


class ApprovalPending(Conflict):
    """The action needs a person's approval; an ApprovalRequest now exists and nothing moved.
    Carries the request and the decision so a caller (the agent tool) can say so."""

    def __init__(self, approval: ApprovalRequest, decision: engine.RiskDecision) -> None:
        super().__init__(decision.explanation_en, "APPROVAL_REQUIRED")
        self.approval = approval
        self.decision = decision


class ApprovalInvalid(Conflict):
    """An `approval_id` did not authorise this exact action."""


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: engine.RiskDecision
    proceed: bool  # the caller may execute now
    approval: ApprovalRequest | None = None  # open request (not proceeding) or the verified one
    inline: bool = False  # a person's one-tap executed a Tier 2 action


def actor_of(origin: Origin) -> str:
    return {Origin.AGENT: Actor.LLM, Origin.SYSTEM: Actor.SYSTEM}.get(origin, Actor.USER).value


def record(
    db: Session,
    *,
    ctx: RiskContext,
    decision: engine.RiskDecision,
    user: CurrentUser | None,
    deal: Deal | None,
    milestone_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> RiskEvent:
    """Store the decision twice: a readable `risk_events` row and a signed RISK_DECISION audit row
    (ids and the context hash only). Runs in the caller's transaction."""
    now = now or datetime.now(UTC)
    seq = write_audit(
        db,
        actor=actor_of(ctx.origin),
        action="RISK_DECISION",
        tier=decision.tier,
        params={
            "action": ctx.action.value,
            "origin": ctx.origin.value,
            "reasons": decision.reason_codes,
            "context_hash": decision.context_hash,
            "milestone_id": str(milestone_id) if milestone_id else None,
            "user_id": str(user.id) if user else None,
        },
        result=f"{decision.decision.value}:T{decision.tier}",
        ts=now,
        deal_id=deal.id if deal else None,
    )
    row = RiskEvent(
        id=uuid.uuid4(),
        ts=now,
        deal_id=deal.id if deal else None,
        milestone_id=milestone_id,
        actor_user_id=user.id if user else None,
        action=ctx.action.value,
        origin=ctx.origin.value,
        decision=decision.decision.value,
        tier=decision.tier,
        reason_codes=decision.reason_codes,
        explanation_en=decision.explanation_en[:600],
        explanation_bn=decision.explanation_bn[:900],
        context_hash=decision.context_hash,
        trace=[t.model_dump() for t in decision.trace],
        hints=[h.model_dump() for h in decision.hints],
        amount_usd=ctx.amount_usd if ctx.action != Action.ANALYSIS else None,
        audit_seq=seq,
    )
    db.add(row)
    return row


def notify(
    db: Session,
    deal: Deal,
    *,
    key: str,
    kind: AlertType,
    severity: Severity,
    title: tuple[str, str],
    message: tuple[str, str],
    milestone_id: uuid.UUID | None = None,
    amount: Decimal | None = None,
    currency: str | None = None,
    facts: dict[str, Any] | None = None,
) -> None:
    """Idempotent by key: a repeat of the same decision does not add a second alert."""
    if db.scalar(select(Alert.id).where(Alert.key == key)) is not None:
        return
    db.add(
        Alert(
            id=uuid.uuid4(),
            key=key[:80],
            party_id=deal.buyer_id,
            deal_id=deal.id,
            milestone_id=milestone_id,
            type=kind,
            severity=severity,
            status=AlertStatus.OPEN,
            title_en=title[0][:200],
            title_bn=title[1][:200],
            message_en=message[0],
            message_bn=message[1],
            amount=amount,
            currency=currency,
            facts=facts or {},
        )
    )


def block_alert(
    db: Session, deal: Deal, decision: engine.RiskDecision, milestone_id: uuid.UUID | None = None
) -> None:
    notify(
        db,
        deal,
        key=f"risk:block:{deal.reference}:{decision.context_hash[:16]}",
        kind=AlertType.FRAUD,
        severity=Severity.CRITICAL,
        title=("Payment blocked by the risk engine", "ঝুঁকি ইঞ্জিন পেমেন্ট আটকেছে"),
        message=(decision.explanation_en, decision.explanation_bn),
        milestone_id=milestone_id,
        facts={"reason_codes": decision.reason_codes, "deal_ref": deal.reference},
    )


def fmt_amount(amount: Decimal, currency: str) -> str:
    text = f"{amount:,.2f}"
    return f"{currency} {text[:-3] if text.endswith('.00') else text}"


def tier1_notice(
    db: Session, deal: Deal, *, milestone_id: uuid.UUID, amount: Decimal, currency: str, to: str
) -> None:
    """INFO notice for an automatic (Tier 1) release: "Released USD 5,760 to Shaoxing Huaxin"."""
    money = fmt_amount(amount, currency)
    notify(
        db,
        deal,
        key=f"risk:auto:{milestone_id}",
        kind=AlertType.INFO,
        severity=Severity.INFO,
        title=(f"Released {money} to {to}", f"{to}-কে {money} ছাড় করা হয়েছে"),
        message=(
            f"{money} was released to {to} automatically (Tier 1: verified supplier, unchanged "
            "account, all checks passed). Simulated.",
            f"{to}-কে {money} স্বয়ংক্রিয়ভাবে ছাড় করা হয়েছে (টিয়ার ১: যাচাইকৃত সরবরাহকারী, "
            "অপরিবর্তিত অ্যাকাউন্ট, সব যাচাই সফল)। সিমুলেটেড।",
        ),
        milestone_id=milestone_id,
        amount=amount,
        currency=currency,
        facts={"deal_ref": deal.reference},
    )


def _binding(
    action: ApprovalAction,
    tier: int,
    deal: Deal,
    milestone_id: uuid.UUID | None,
    bank_account_id: uuid.UUID | None,
    params: dict[str, Any],
) -> str:
    return approval_binding_hash(
        action=action.value,
        tier=tier,
        deal_id=deal.id,
        milestone_id=milestone_id,
        bank_account_id=bank_account_id,
        params=params,
    )


def _open_approval(
    db: Session, deal: Deal, action: ApprovalAction, milestone_id: uuid.UUID | None
) -> list[ApprovalRequest]:
    return list(
        db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.deal_id == deal.id,
                ApprovalRequest.action == action,
                ApprovalRequest.milestone_id == milestone_id
                if milestone_id
                else ApprovalRequest.milestone_id.is_(None),
                ApprovalRequest.status.in_(OPEN),
            )
            .order_by(ApprovalRequest.tier.desc(), ApprovalRequest.created_at.desc())
        ).all()
    )


def verify_approval(
    db: Session,
    approval_id: uuid.UUID,
    *,
    deal: Deal,
    action: ApprovalAction,
    milestone_id: uuid.UUID | None,
    bank_account_id: uuid.UUID | None,
    params: dict[str, Any],
    tier: int,
    now: datetime,
) -> ApprovalRequest:
    appr = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id).with_for_update()
    ).first()

    def bad(code: str, detail: str) -> ApprovalInvalid:
        return ApprovalInvalid(detail, code)

    if appr is None or appr.deal_id != deal.id or appr.milestone_id != milestone_id:
        raise bad("APPROVAL_MISMATCH", "this approval does not belong to this action")
    if appr.action != action or appr.status != ApprovalStatus.APPROVED:
        raise bad("APPROVAL_NOT_APPROVED", "the approval has not been approved")
    if appr.params != params or appr.bank_account_id != bank_account_id:
        raise bad("APPROVAL_PARAMS_CHANGED", "the request changed after it was approved")
    if appr.params_hash != _binding(action, appr.tier, deal, milestone_id, bank_account_id, params):
        raise bad("APPROVAL_HASH_MISMATCH", "the approval no longer matches what was approved")
    if tier > appr.tier:
        raise bad("APPROVAL_TIER_STALE", "this action now needs a higher approval tier")
    if appr.cooling_off_until is not None and appr.cooling_off_until > now:
        raise bad("COOLING_OFF", "the cooling-off period has not ended")
    return appr


def run_gate(
    db: Session,
    *,
    user: CurrentUser,
    deal: Deal,
    ctx: RiskContext,
    approval_action: ApprovalAction,
    params: dict[str, Any],
    milestone_id: uuid.UUID | None = None,
    bank_account_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> GateResult:
    """Decide and enforce. Commits the audit/alert rows on BLOCK (then raises) and the new
    ApprovalRequest on REQUIRE_APPROVAL; on a proceed the caller commits with its own work."""
    now = now or datetime.now(UTC)
    decision = engine.evaluate(ctx)
    record(db, ctx=ctx, decision=decision, user=user, deal=deal, milestone_id=milestone_id, now=now)

    if decision.decision == Verdict.BLOCK:
        block_alert(db, deal, decision, milestone_id)
        db.commit()
        raise RiskBlocked(decision.explanation_en, "RISK_BLOCKED")

    if approval_id is not None:
        if ctx.origin != Origin.USER_UI:
            db.rollback()
            raise ApprovalInvalid("only a person can execute an approval", "APPROVAL_NOT_HUMAN")
        try:
            appr = verify_approval(
                db,
                approval_id,
                deal=deal,
                action=approval_action,
                milestone_id=milestone_id,
                bank_account_id=bank_account_id,
                params=params,
                tier=decision.tier,
                now=now,
            )
        except ApprovalInvalid:
            db.commit()  # keep the RISK_DECISION row of the refused attempt
            raise
        return GateResult(decision, True, appr)

    if decision.decision == Verdict.ALLOW:
        return GateResult(decision, True)

    # REQUIRE_APPROVAL
    own = OWN_REASON.get(ctx.action)
    policy = load_policy()
    if (
        decision.tier == 2
        and ctx.origin == Origin.USER_UI
        and ctx.action.value in policy.inline_tier2_actions
        and own is not None
        and set(decision.reason_codes) <= {own}
    ):
        return GateResult(decision, True, inline=True)

    approval = _request(
        db,
        user=user,
        deal=deal,
        ctx=ctx,
        decision=decision,
        action=approval_action,
        params=params,
        milestone_id=milestone_id,
        bank_account_id=bank_account_id,
        now=now,
    )
    db.commit()
    return GateResult(decision, False, approval)


def _request(
    db: Session,
    *,
    user: CurrentUser,
    deal: Deal,
    ctx: RiskContext,
    decision: engine.RiskDecision,
    action: ApprovalAction,
    params: dict[str, Any],
    milestone_id: uuid.UUID | None,
    bank_account_id: uuid.UUID | None,
    now: datetime,
) -> ApprovalRequest:
    tier = decision.tier
    for existing in _open_approval(db, deal, action, milestone_id):
        if existing.params != params:
            continue
        if existing.tier >= tier:
            return existing  # idempotent: the same request is already waiting
        existing.status = ApprovalStatus.CANCELLED  # superseded by a stricter request
        existing.decided_at = now
    binding = _binding(action, tier, deal, milestone_id, bank_account_id, params)
    appr = ApprovalRequest(
        id=uuid.uuid4(),
        key=f"approval:{deal.reference}:{action.value.lower()}:{binding[:12]}:{uuid.uuid4().hex[:8]}"[
            :80
        ],
        deal_id=deal.id,
        milestone_id=milestone_id,
        bank_account_id=bank_account_id,
        action=action,
        tier=tier,
        params=params,
        params_hash=binding,
        reasons=[
            {"code": code, "message": engine.TEXT[code][0], "message_bn": engine.TEXT[code][1]}
            for code in decision.reason_codes
        ],
        status=ApprovalStatus.PENDING,
        requested_by=Actor.LLM if ctx.origin == Origin.AGENT else Actor.USER,
        requested_by_user_id=user.id if ctx.origin == Origin.USER_UI else None,
        otp_required=tier == 3,
        cooling_off_until=approval_otp.cooling_off_until(now, tier),
        created_at=now,
    )
    db.add(appr)
    db.flush()
    seq = write_audit(
        db,
        actor=actor_of(ctx.origin),
        action="APPROVAL_REQUESTED",
        tier=tier,
        params={
            "approval_id": str(appr.id),
            "approval_action": action.value,
            "params_hash": binding,
            "reasons": decision.reason_codes,
            "context_hash": decision.context_hash,
            "user_id": str(user.id),
        },
        result=f"PENDING_APPROVAL:T{tier}",
        ts=now,
        deal_id=deal.id,
    )
    approval_otp.on_created(
        db,
        appr,
        deal,
        context_hash=decision.context_hash,
        now=now,
        actor=actor_of(ctx.origin),
        audit_seq=seq,
        summary=(decision.explanation_en, decision.explanation_bn),
    )
    log.info("approval_requested", deal=deal.reference, action=action.value, tier=tier)
    return appr
