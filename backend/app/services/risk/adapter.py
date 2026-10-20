"""Glue between the escrow hook contract (`risk_hook.ReleaseContext`) and the engine."""

from app.security.risk_hook import (
    ReleaseContext,
    RiskAction,
    RiskReason,
    RiskResult,
)
from app.security.risk_hook import (
    RiskDecision as Verdict,
)
from app.services.risk import engine
from app.services.risk.engine import Action, Origin, RiskContext


def release_risk_context(c: ReleaseContext) -> RiskContext:
    return RiskContext(
        action=Action.RELEASE_TRANCHE,
        origin=Origin(c.origin),
        amount=c.amount,
        currency=c.currency,
        amount_usd=c.amount_usd,
        buyer_id=c.buyer_id,
        supplier_id=c.supplier_id,
        is_first_deal_with_supplier=c.supplier_deal_count == 0,
        beneficiary_changed_recently=c.beneficiary_changed_recently,
        beneficiary_status=c.beneficiary_status,
        beneficiary_verified=c.beneficiary_verified,
        kyb_status=c.supplier_kyb_status,
        kyb_account_warning=c.kyb_account_warning,
        max_document_fraud_score=c.max_document_fraud_score,
        any_document_warning=c.any_document_warning,
        any_document_failed=c.any_document_failed,
        duplicate_hash=c.document_duplicate,
        instruction_from_document=c.document_instruction,
        sanctions_hit=c.sanctions_hit,
        advance_over_limit=c.advance_over_20k,
        fx_lock_missing=c.fx_lock_missing,
        deal_ref=c.deal_ref,
        milestone_seq=c.milestone_seq,
    )


def to_result(d: engine.RiskDecision) -> RiskResult:
    reasons = [RiskReason(code=code, message=engine.TEXT[code][0]) for code in d.reason_codes]
    return RiskResult(
        decision=d.decision,
        tier=d.tier,
        reasons=reasons,
        context_hash=d.context_hash,
        decided_by=d.decided_by,
        trace=[t.model_dump() for t in d.trace],
        hints=[h.model_dump() for h in d.hints],
        explanation_en=d.explanation_en,
        explanation_bn=d.explanation_bn,
    )


def evaluate_release(action: RiskAction, context: ReleaseContext) -> RiskResult:
    """The production `RiskHook`. Deterministic: the same context gives the same result."""
    if action != RiskAction.RELEASE_TRANCHE:
        return RiskResult(decision=Verdict.BLOCK, tier=3)  # unknown action: fail closed
    return to_result(engine.evaluate(release_risk_context(context)))


def to_decision(result: RiskResult, context: ReleaseContext) -> engine.RiskDecision:
    """The engine-shaped decision of a hook result (a test hook may leave text and hash empty)."""
    ctx = release_risk_context(context)
    return engine.RiskDecision(
        decision=result.decision,
        tier=result.tier,
        reason_codes=[r.code for r in result.reasons],
        explanation_en=result.explanation_en or "; ".join(r.message for r in result.reasons),
        explanation_bn=result.explanation_bn,
        context_hash=result.context_hash or engine.context_hash(ctx),
        decided_by=result.decided_by,
        trace=[engine.TraceItem.model_validate(t) for t in result.trace],
        hints=[engine.Hint.model_validate(h) for h in result.hints],
    )
