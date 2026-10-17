"""Document facts the release path needs (ReleaseContext): unchecked documents on the tranche,
and deal-level red flags (instruction-like text, duplicate hash) from ANY document of the deal,
whichever milestone it belongs to or none."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import CheckStatus, DocStatus
from app.db.models import Document, ForensicFinding


@dataclass(frozen=True, slots=True)
class DocumentFacts:
    pending: bool = False
    instruction: bool = False
    duplicate: bool = False


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
    return DocumentFacts(
        pending=pending is not None,
        instruction="INSTRUCTION_SCAN" in failed,
        duplicate="DUPLICATE_HASH" in failed,
    )
