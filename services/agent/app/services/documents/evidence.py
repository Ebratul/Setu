"""Step 5: milestone evidence from document verdicts. A milestone is VERIFIED when every required
document type has a PASSED document; a WARNING document makes it FLAGGED (the buyer reviews);
a FAILED one makes it REJECTED. Worst verdict wins, so a rejected document keeps the tranche
blocked until an admin resolves it. Release itself stays gated by `escrow.release_tranche`
(EVIDENCE_NOT_VERIFIED); the dev-only evidence endpoint remains an override for tests and demos."""

import uuid
from collections.abc import Iterable
from datetime import datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import CheckStatus, DocStatus, EvidenceStatus, Role
from app.db.models import Deal, Document, Milestone
from app.domain import escrow as rules
from app.services import escrow

log = structlog.get_logger("setu.documents.evidence")


def evaluate(required: Iterable[str], docs: list[Document]) -> EvidenceStatus:
    """Evidence verdict from the check statuses of the milestone's uploaded documents."""
    per_type: list[str] = []
    for doc_type in required:
        mine = [d for d in docs if d.doc_type.value == doc_type]
        statuses = {d.check_status for d in mine}
        if not mine:
            per_type.append("MISSING")
        elif CheckStatus.FAILED in statuses:
            per_type.append("REJECTED")
        elif CheckStatus.WARNING in statuses:
            per_type.append("FLAGGED")
        elif statuses <= {CheckStatus.PASSED}:
            per_type.append("VERIFIED")
        else:
            per_type.append("PENDING")
    if "REJECTED" in per_type:
        return EvidenceStatus.REJECTED
    if "FLAGGED" in per_type:
        return EvidenceStatus.FLAGGED
    if per_type and all(s == "VERIFIED" for s in per_type):
        return EvidenceStatus.VERIFIED
    return EvidenceStatus.PENDING


STRICTNESS = {
    EvidenceStatus.VERIFIED: 0,
    EvidenceStatus.PENDING: 1,
    EvidenceStatus.FLAGGED: 2,
    EvidenceStatus.REJECTED: 3,
}


def lock_deal_documents(db: Session, deal_id: uuid.UUID) -> None:
    """One document operation per deal at a time (transaction-scoped, re-entrant per session)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"docs:{deal_id}"}
    )


def sync(
    db: Session,
    deal: Deal,
    *,
    actor: CurrentUser | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> list[Milestone]:
    """Recompute the evidence status of every unsettled milestone that has uploaded documents and
    record changes through `escrow.set_evidence_status` (audited, deal-locked). Returns the
    milestones that changed. A milestone with no documents is left as it is.

    The evaluation runs under the per-deal document lock on fresh rows, so a stale VERIFIED from
    a concurrent run can never overwrite a REJECTED. Automatic runs only tighten: a FLAGGED or
    REJECTED milestone is loosened only when an admin triggers the run."""
    lock_deal_documents(db, deal.id)
    admin = actor is not None and actor.role == Role.ADMIN
    changed: list[Milestone] = []
    for ms in escrow.milestones_of(db, deal.id):
        if ms.status in rules.SETTLED:
            continue
        docs = db.scalars(
            select(Document)
            .where(Document.milestone_id == ms.id, Document.status == DocStatus.UPLOADED)
            .execution_options(populate_existing=True)
        ).all()
        if not docs:
            continue
        verdict = evaluate(ms.required_evidence, list(docs))
        if verdict == ms.evidence_status:
            continue
        loosening = STRICTNESS[verdict] < STRICTNESS[ms.evidence_status]
        held = ms.evidence_status in (EvidenceStatus.FLAGGED, EvidenceStatus.REJECTED)
        if loosening and held and not admin:
            continue
        escrow.set_evidence_status(db, ms.id, verdict, actor=actor, now=now, commit=False)
        changed.append(ms)
    if commit:
        db.commit()
    return changed
