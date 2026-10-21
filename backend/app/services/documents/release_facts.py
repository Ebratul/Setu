"""Document facts the release path needs (ReleaseContext): unchecked documents on the tranche,
and deal-level red flags (instruction-like text, duplicate hash) from ANY document of the deal,
whichever milestone it belongs to or none."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import CheckStatus, DocStatus
from app.db.models import Document, ForensicFinding
from app.security.injection.events import deal_flagged
from app.services.documents.checks import FORENSICS_KEY


@dataclass(frozen=True, slots=True)
class DocumentFacts:
    pending: bool = False
    instruction: bool = False
    duplicate: bool = False
    # This tranche's uploaded documents (risk engine inputs).
    max_score: int = 0
    warning: bool = False
    failed: bool = False


def facts(db: Session, deal_id: uuid.UUID, milestone_id: uuid.UUID) -> DocumentFacts:
    pending = db.scalars(
        select(Document.id)
        .where(
            Document.milestone_id == milestone_id,
            Document.status == DocStatus.UPLOADED,
            Document.check_status.in_((CheckStatus.PENDING, CheckStatus.NOT_RUN)),
        )
        .limit(1)
    ).first()
    failed = set(
        db.scalars(
            select(ForensicFinding.check_code)
            .join(Document, Document.id == ForensicFinding.document_id)
            .where(
                Document.deal_id == deal_id,
                Document.status == DocStatus.UPLOADED,
                ForensicFinding.status == CheckStatus.FAILED,
                ForensicFinding.check_code.in_(("INSTRUCTION_SCAN", "DUPLICATE_HASH")),
            )
        ).all()
    )
    docs = db.execute(
        select(Document.check_status, Document.extracted_json).where(
            Document.milestone_id == milestone_id,
            Document.status == DocStatus.UPLOADED,
        )
    ).all()
    scores = [_score(extracted) for _, extracted in docs]
    return DocumentFacts(
        pending=pending is not None,
        instruction="INSTRUCTION_SCAN" in failed or deal_flagged(db, deal_id),
        duplicate="DUPLICATE_HASH" in failed,
        max_score=max(scores, default=0),
        warning=any(status == CheckStatus.WARNING for status, _ in docs),
        failed=any(status == CheckStatus.FAILED for status, _ in docs),
    )


def _score(extracted: dict[str, Any] | None) -> int:
    verdict = ((extracted or {}).get(FORENSICS_KEY) or {}).get("verdict") or {}
    score = verdict.get("score")
    return score if isinstance(score, int) and 0 <= score <= 100 else 0
