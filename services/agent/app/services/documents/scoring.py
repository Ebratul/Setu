"""Step 4: the document verdict from its stored findings (weights: app/forensics/scoring.py)."""

from datetime import datetime
from typing import Any

from app.config import get_settings
from app.db.enums import CheckStatus
from app.db.models import Document
from app.forensics.checks import Outcome
from app.forensics.scoring import Score, score_document
from app.services.documents.checks import FORENSICS_KEY

VERDICT_TO_DB = {
    "PASSED": CheckStatus.PASSED,
    "WARNING": CheckStatus.WARNING,
    "FAILED": CheckStatus.FAILED,
}


def score(outcomes: list[Outcome]) -> Score:
    s = get_settings()
    return score_document(
        outcomes, warn_at=s.forensics_warn_score, fail_above=s.forensics_fail_score
    )


def apply_score(doc: Document, result: Score, now: datetime) -> None:
    """Write the verdict to the row: `check_status` plus the details beside the extraction."""
    doc.check_status = VERDICT_TO_DB[result.status]
    ej: dict[str, Any] = dict(doc.extracted_json or {})
    meta = dict(ej.get(FORENSICS_KEY, {}))
    meta.pop("check_failed", None)
    meta["verdict"] = {
        "status": result.status,
        "score": result.score,
        "reason_codes": list(result.reason_codes),
        "forced_by": list(result.forced_by),
        "explanation_en": result.explanation_en,
        "explanation_bn": result.explanation_bn,
        "checked_at": now.isoformat(),
    }
    ej[FORENSICS_KEY] = meta
    doc.extracted_json = ej
