"""Tier 0 supplier KYB tool (P12). Compute-only: it never writes the Party, KYB rows, alerts or the
audit log (the human `POST /kyb/verify/{id}` endpoint does). The card carries role labels only, no
account-holder, invoice or sanctions-hit names. Buyer isolation: a supplier the caller has no deal
with, or a deal that is not theirs, looks missing."""

import re

from pydantic import BaseModel, ConfigDict, Field

from app.agent.persistence import resolve_deal
from app.agent.registry import ToolContext, ToolError
from app.agent.tools.finance import DealId, _db
from app.agent.tools.readonly import REGISTRY
from app.domain.kyb import CODE_LABELS
from app.errors import NotFound
from app.schemas.cards import KybCard, KybData, KybReason
from app.security.tiers import Tier
from app.services import kyb

TOP_REASONS = 3
SupplierRef = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class VerifyPartyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=SupplierRef.pattern,
        description="Supplier id or code. Omit to use the supplier of the deal.",
    )
    deal_id: DealId | None = Field(
        default=None, description="Deal reference; its proforma invoice seller name is checked."
    )


@REGISTRY.tool(
    name="verify_party",
    tier=Tier.T0,
    args_schema=VerifyPartyIn,
    output_schema=KybCard,
    tags=("kyb", "suppliers"),
)
def verify_party(args: VerifyPartyIn, ctx: ToolContext) -> KybCard:
    """Supplier KYB check: is this supplier and its receiving bank account trustworthy? Returns
    status (VERIFIED, WARNING or BLOCKED), score, the top reasons and any pending account change.
    Read-only."""
    db = _db(ctx)
    deal_ref = args.deal_id or (None if args.supplier_id else ctx.deal_ref)
    try:
        if args.supplier_id:
            supplier = kyb.find_supplier(db, ctx.user, args.supplier_id)
            deal = kyb.find_deal(db, ctx.user, supplier, deal_ref) if deal_ref else None
        elif deal_ref:
            deal = resolve_deal(db, ctx.user, deal_ref)
            supplier = kyb.find_supplier(db, ctx.user, deal.supplier_id)
        else:
            raise ToolError("needs_supplier", "say which supplier or deal to check")
    except NotFound as exc:
        raise ToolError("not_found", "supplier or deal not found") from exc
    res = kyb.evaluate(db, supplier, deal=deal)
    # The model sees role labels, never holder, invoice or sanctions-hit names (people's names).
    bad = sorted(
        (c for c in res.checks if c.status != "PASS"),
        key=lambda c: (c.status != "FAIL", res.reason_codes.index(c.code)),
    )
    pending = res.pending_accounts[0].status if res.pending_accounts else None
    top = bad[:TOP_REASONS]
    label = {c.code: CODE_LABELS.get(c.code, (c.code, c.code)) for c in top}
    word = {"VERIFIED": "Verified", "WARNING": "Warning", "BLOCKED": "Blocked"}[res.status]
    word_bn = {"VERIFIED": "যাচাইকৃত", "WARNING": "সতর্কতা", "BLOCKED": "অবরুদ্ধ"}[res.status]
    en = f"{word} (score {res.score}/100)." + (
        " Main reasons: " + "; ".join(label[c.code][0] for c in top) + "." if top else ""
    )
    bn_ = f"{word_bn} (স্কোর {res.score}/100)।" + (
        " প্রধান কারণ: " + "; ".join(label[c.code][1] for c in top) + "।" if top else ""
    )
    return KybCard(
        data=KybData(
            supplier_id=supplier.id,
            supplier_code=supplier.code,
            supplier_name=supplier.legal_name,
            status=res.status,
            score=res.score,
            deal_ref=res.deal_ref,
            reasons=[
                KybReason(
                    code=c.code,
                    status=c.status,  # type: ignore[arg-type]
                    detail_en=label[c.code][0],
                    detail_bn=label[c.code][1],
                )
                for c in top
            ],
            checks_passed=sum(c.status == "PASS" for c in res.checks),
            checks_total=len(res.checks),
            has_pending_change=res.has_pending_change,
            pending_status=pending,
            supplier_route=res.route,
        ),
        explanation_codes=[res.status, *res.reason_codes[:TOP_REASONS]]
        + (["PENDING_BENEFICIARY_CHANGE"] if res.has_pending_change else []),
        explanation_en=_with_pending(en, res.has_pending_change, "en"),
        explanation_bn=_with_pending(bn_, res.has_pending_change, "bn"),
    )


def _with_pending(text: str, pending: bool, lang: str) -> str:
    if not pending:
        return text
    return text + (
        " A new receiving account is pending and is not trusted yet."
        if lang == "en"
        else " একটি নতুন প্রাপক অ্যাকাউন্ট অপেক্ষমাণ এবং এখনও বিশ্বাসযোগ্য নয়।"
    )


__all__ = ["verify_party"]
