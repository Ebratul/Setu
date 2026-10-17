"""Tier 0 `check_documents` tool (P14). Read-only: it reads the stored forensic results of a deal's
documents and never uploads, re-checks, writes findings, alerts or audit rows (the human
endpoints do). The card carries role labels, codes, scores and links only: no file names, no
extracted text, no hidden-span text, no metadata. When a document carried hidden or
instruction-like text the card flags the turn (`security_flags`) so the answer says it was ignored.
Buyer isolation: a deal the caller cannot read looks missing; suppliers do not get this tool."""

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.registry import ToolContext, ToolError
from app.agent.tools.finance import DealId, _db, pick_deal
from app.agent.tools.readonly import REGISTRY
from app.db.enums import DocStatus, Role
from app.db.models import Document
from app.forensics.names import LABELS
from app.schemas.cards import (
    DocumentCheckCard,
    DocumentCheckData,
    DocumentCheckItem,
    DocumentReason,
)
from app.security.tiers import Tier
from app.services import alerts
from app.services.documents import read
from app.services.documents.checks import STATUS_FROM_DB

TOP_REASONS = 3
RANK = {"FAILED": 0, "WARNING": 1, "PENDING": 2, "NOT_RUN": 3, "PASSED": 4}


class CheckDocumentsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_id: DealId | None = Field(
        default=None, description="Deal reference, e.g. SETU-2026-0001. Omit for the chat's deal."
    )
    document_id: uuid.UUID | None = Field(
        default=None, description="One document of the deal. Omit to summarise all of them."
    )


def _item(db, doc: Document) -> DocumentCheckItem:  # type: ignore[no-untyped-def]
    rows = read.findings_of(db, doc)
    verdict = read.verdict_of(doc, rows)
    by = {r.check_code: STATUS_FROM_DB[r.status] for r in rows}
    codes = list(verdict.reason_codes) if verdict else []
    reasons = [
        DocumentReason(
            code=c,
            status=by[c],  # type: ignore[arg-type]
            detail_en=LABELS[c][0],
            detail_bn=LABELS[c][1],
        )
        for c in codes
        if c in LABELS and by.get(c) in ("WARN", "FAIL")
    ][:TOP_REASONS]
    en, bn = alerts.DOC_TYPE_LABELS.get(doc.doc_type.value, alerts.DOC_TYPE_LABELS["OTHER"])
    return DocumentCheckItem(
        document_id=doc.id,
        doc_type=doc.doc_type.value,
        doc_label_en=en,
        doc_label_bn=bn,
        status=doc.check_status.value,  # type: ignore[arg-type]
        score=verdict.score if verdict else None,
        reasons=reasons,
        instruction_from_document=by.get("INSTRUCTION_SCAN") == "FAIL",
        hidden_text_found=by.get("HIDDEN_TEXT") == "FAIL",
        route=f"/app/documents/{doc.id}",  # type: ignore[arg-type]
    )


def _explain(data: DocumentCheckData) -> tuple[list[str], str, str]:
    if data.status == "NONE":
        return (
            ["NO_DOCUMENTS"],
            "No documents have been uploaded for this deal yet.",
            "এই ডিলের জন্য এখনও কোনো ডকুমেন্ট আপলোড করা হয়নি।",
        )
    if data.instruction_from_document or data.hidden_text_found:
        return (
            ["HIDDEN_INSTRUCTION", data.status],
            "A document contains a hidden instruction that Setu ignored; it needs a human review.",
            "একটি ডকুমেন্টে লুকানো নির্দেশ ছিল যা Setu উপেক্ষা করেছে; মানুষের পর্যালোচনা দরকার।",
        )
    word = {"PASSED": "passed", "WARNING": "needs review", "FAILED": "failed"}.get(
        data.status, "is being checked"
    )
    word_bn = {"PASSED": "সফল", "WARNING": "পর্যালোচনা দরকার", "FAILED": "ব্যর্থ"}.get(
        data.status, "যাচাই চলছে"
    )
    return (
        [data.status],
        f"Document checks: {word} ({data.passed} passed, {data.warning} to review, "
        f"{data.failed} failed).",
        f"ডকুমেন্ট যাচাই: {word_bn} ({data.passed}টি সফল, {data.warning}টি পর্যালোচনা, "
        f"{data.failed}টি ব্যর্থ)।",
    )


@REGISTRY.tool(
    name="check_documents",
    tier=Tier.T0,
    args_schema=CheckDocumentsIn,
    output_schema=DocumentCheckCard,
    tags=("documents", "forensics"),
)
def check_documents(args: CheckDocumentsIn, ctx: ToolContext) -> DocumentCheckCard:
    """Document forensics for a deal: is a trade document (invoice, packing list, bill of
    lading, certificate of origin, bill of entry, photo) consistent and safe? Returns the stored
    status, score, top reasons and a link; flags hidden or instruction-like text. Read-only."""
    from app.domain.narrative import bn as to_bn

    if ctx.user.role == Role.SUPPLIER:
        raise ToolError("forbidden", "document forensics is for the buyer of the deal")
    db = _db(ctx)
    deal, defaulted = pick_deal(ctx, args.deal_id)
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.deal_id == deal.id, Document.status == DocStatus.UPLOADED)
            .order_by(Document.uploaded_at.desc().nulls_last(), Document.key)
        ).all()
    )
    if args.document_id is not None:
        docs = [d for d in docs if d.id == args.document_id]
        if not docs:
            raise ToolError("not_found", "document not found")
    items = sorted((_item(db, d) for d in docs), key=lambda i: RANK[i.status])
    focus = items[0] if items else None
    flags: list[str] = []
    if any(i.hidden_text_found for i in items):
        flags.append("HIDDEN_TEXT")
    if any(i.instruction_from_document for i in items):
        flags.append("DOC_INSTRUCTION")
    data = DocumentCheckData(
        deal_ref=deal.reference,
        defaulted_deal=defaulted,
        status=focus.status if focus else "NONE",
        score=focus.score if focus else None,
        focus=focus,
        documents=items,
        checks_total=len(items),
        passed=sum(i.status == "PASSED" for i in items),
        warning=sum(i.status == "WARNING" for i in items),
        failed=sum(i.status == "FAILED" for i in items),
        instruction_from_document="DOC_INSTRUCTION" in flags,
        hidden_text_found="HIDDEN_TEXT" in flags,
        security_flags=flags,
        deal_route=f"/app/deals/{deal.reference}",  # type: ignore[arg-type]
    )
    codes, en, bn_ = _explain(data)
    return DocumentCheckCard(
        data=data, explanation_codes=codes, explanation_en=en, explanation_bn=to_bn(bn_)
    )


__all__ = ["check_documents"]
