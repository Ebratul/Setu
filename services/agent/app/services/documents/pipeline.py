"""Orchestration of the document pipeline for one deal.

`process_document` extracts (once; cached on the row), runs the checks for the document and for
its siblings (a new document can change a sibling's pack-level results), stores findings and
verdicts, raises a FRAUD alert, audits, and finally syncs milestone evidence, all in ONE
transaction under a per-deal Postgres advisory lock so two operations cannot interleave.

Automatic runs only tighten: a REJECTED milestone and an open FRAUD alert are cleared only by an
admin-triggered re-check (and that is audited). A check that crashes marks the document
`WARNING` with `check_failed` so it is visible and retryable (recheck), never silently PENDING.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import CheckStatus, DocStatus, DocType, Role
from app.db.models import Deal, Document, ForensicFinding
from app.errors import DomainError, NotFound
from app.forensics.analyze import analyze_photo, build_scan_view
from app.forensics.canonical import canonical_invoice_hash
from app.forensics.checks import Outcome
from app.forensics.context import DealContext, DocView
from app.forensics.fields import EXTRACTOR_VERSION, REQUIRED
from app.forensics.names import LABELS
from app.forensics.parse_fields import DateOrder
from app.services import alerts
from app.services import escrow as escrow_service
from app.services.documents import evidence, scoring
from app.services.documents.checks import (
    FORENSICS_KEY,
    build_context,
    build_pack,
    run_for_document,
    store_findings,
    view_from_row,
    with_reference_booking,
)
from app.services.documents.evidence import lock_deal_documents
from app.services.documents.extract_fields import extract_fields
from app.services.documents.extract_text import extract_text
from app.services.documents.storage import get_storage

log = structlog.get_logger("setu.documents")
KEEP_META = ("verdict", "accepted", "check_failed")


def utcnow() -> datetime:
    return datetime.now(UTC)


def _sibling_hint(docs: list[Document]) -> DateOrder | None:
    """A day/month order proven by another document of the deal (not just assumed)."""
    for d in docs:
        meta = (d.extracted_json or {}).get(FORENSICS_KEY) or {}
        if meta.get("date_order") and not meta.get("date_order_assumed"):
            return meta["date_order"]
    return None


def _kept(doc: Document) -> dict[str, Any]:
    prior = (doc.extracted_json or {}).get(FORENSICS_KEY) or {}
    return {k: prior[k] for k in KEEP_META if k in prior}


def ensure_extracted(
    db: Session,
    doc: Document,
    *,
    force: bool = False,
    hint: DateOrder | None = None,
    data: bytes | None = None,
) -> DocView:
    """The stored extraction, or read the file, extract and store it on the row."""
    if not force:
        view = view_from_row(doc)
        if view is not None:
            return view
    raw = data if data is not None else get_storage().get(doc.storage_path)
    sha = hashlib.sha256(raw).hexdigest()
    if doc.sha256 and sha != doc.sha256:
        raise DomainError("the stored file does not match its recorded hash", "FILE_INTEGRITY")
    doc.sha256 = sha
    meta: dict[str, Any] = {"extractor_version": EXTRACTOR_VERSION, "sha256": sha}
    kept = _kept(doc)
    is_image = doc.mime_type.startswith("image/")
    if is_image:
        view = analyze_photo(raw, sha).view
        view.doc_type = doc.doc_type.value
        meta["kind"] = "image"
        meta["warnings"] = view.warnings
        if view.photo_colour and doc.doc_type == DocType.PRODUCTION_PHOTO:
            name, rgb, dist = view.photo_colour
            meta["photo_colour"] = {"name": name, "rgb": list(rgb), "distance": dist}
        body: dict[str, Any] = {"doc_type": doc.doc_type.value}
    else:
        try:
            pdf = extract_text(raw, doc.mime_type)
            assert pdf is not None
            if doc.doc_type == DocType.OTHER:  # no field schema: hidden text and instructions only
                fx_view = build_scan_view(pdf, doc.doc_type.value)
                view, parsed, llm_fields = fx_view.view, None, []
            else:
                fx = extract_fields(
                    db, pdf, doc.doc_type.value, sha, date_order_hint=hint, doc_id=str(doc.id)
                )
                view, parsed, llm_fields = fx.analysis.view, fx.analysis.parsed, fx.llm_fields
        except Exception as exc:  # corrupt, encrypted, heavy or hostile file
            log.warning("document_unreadable", error=type(exc).__name__, sha256=sha)
            return _unreadable(db, doc, sha, kept)
        body = view.fields.model_dump(mode="json") if view.fields else {}
        if doc.doc_type == DocType.OTHER:
            body = {"doc_type": "OTHER"}
        meta.update(
            kind="pdf",
            missing=view.missing,
            warnings=view.warnings,
            llm_fields=llm_fields,
            hidden_spans=[s.as_dict() for s in view.hidden_spans],
            instruction_codes=view.instruction_codes,
            metadata=view.metadata,
            created=view.created.isoformat() if view.created else None,
            modified=view.modified.isoformat() if view.modified else None,
        )
        if parsed is not None:
            meta.update(date_order=parsed.date_order, date_order_assumed=parsed.date_order_assumed)
        f = view.fields
        if (
            doc.doc_type in (DocType.PROFORMA_INVOICE, DocType.COMMERCIAL_INVOICE)
            and f is not None
            and getattr(f, "invoice_no", None)
            and getattr(f, "seller", None)
            and getattr(f, "total", None) is not None
        ):
            doc.canonical_hash = canonical_invoice_hash(
                f.seller,  # type: ignore[union-attr]
                f.invoice_no,  # type: ignore[union-attr]
                f.total,  # type: ignore[union-attr]
                getattr(f, "currency", None) or "USD",
            )
    meta.update(kept)
    meta.pop("check_failed", None)  # a fresh extraction clears an earlier crash marker
    doc.extracted_json = {**body, FORENSICS_KEY: meta}
    view.sha256 = sha
    db.flush()
    return view


def _unreadable(db: Session, doc: Document, sha: str, kept: dict[str, Any]) -> DocView:
    """A file that could not be read: no fields, so only EXTRACTION_COMPLETE speaks (WARN)."""
    required = list(REQUIRED.get(doc.doc_type.value, ())) or ["file"]
    meta: dict[str, Any] = {
        "extractor_version": EXTRACTOR_VERSION,
        "sha256": sha,
        "kind": "pdf",
        "unreadable": True,
        "missing": required,
        "warnings": ["UNREADABLE_FILE"],
        "hidden_spans": [],
        "instruction_codes": {},
        "metadata": {},
        **kept,
    }
    meta.pop("check_failed", None)
    doc.extracted_json = {"doc_type": doc.doc_type.value, FORENSICS_KEY: meta}
    db.flush()
    view = view_from_row(doc)
    assert view is not None
    return view


def deal_rows(db: Session, deal: Deal) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.deal_id == deal.id, Document.status == DocStatus.UPLOADED)
            .order_by(Document.uploaded_at, Document.key)
        ).all()
    )


def _check_one(
    db: Session,
    doc: Document,
    views: dict[uuid.UUID, DocView],
    rows: list[Document],
    ctx: DealContext,
    now: datetime,
) -> tuple[list[Outcome], scoring.Score]:
    pack = build_pack([(d, views[d.id]) for d in rows])
    outcomes = run_for_document(db, doc, views[doc.id], pack, with_reference_booking(ctx, pack))
    store_findings(db, doc, outcomes, now)
    result = scoring.score(outcomes)
    scoring.apply_score(doc, result, now)
    return outcomes, result


def _flags(outcomes: list[Outcome]) -> bool:
    return any(
        o.code in ("INSTRUCTION_SCAN", "HIDDEN_TEXT") and o.status == "FAIL" for o in outcomes
    )


def process_document(
    db: Session,
    document_id: uuid.UUID,
    *,
    user: CurrentUser | None = None,
    force_extract: bool = False,
    action: str = "DOC_CHECKED",
    now: datetime | None = None,
) -> Document:
    """Check one document and its siblings, then sync evidence. Commits."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("document not found")
    deal = db.get(Deal, doc.deal_id)
    if deal is None:
        raise NotFound("deal not found")
    lock_deal_documents(db, deal.id)
    db.refresh(doc)
    now = now or utcnow()
    admin = user is not None and user.role == Role.ADMIN
    rows = deal_rows(db, deal)
    if doc.id not in {r.id for r in rows}:
        raise DomainError("this document is not an uploaded file", "NOT_CHECKABLE")
    hint = _sibling_hint(rows)
    views: dict[uuid.UUID, DocView] = {}
    for row in rows:
        views[row.id] = ensure_extracted(
            db, row, force=force_extract and row.id == doc.id, hint=hint
        )
    ctx = build_context(db, deal)
    # Primary document first, then every sibling (their pack-level results may have changed).
    order = [doc, *[r for r in rows if r.id != doc.id]]
    for row in order:
        before = row.check_status
        outcomes, result = _check_one(db, row, views, rows, ctx, now)
        primary = row.id == doc.id
        if primary or before != row.check_status:
            escrow_service.audit(
                db,
                deal,
                action if primary else "DOC_RECHECKED",
                0,
                {
                    "document_id": str(row.id),
                    "doc_type": row.doc_type.value,
                    "status": result.status,
                    "score": result.score,
                    "reason_codes": list(result.reason_codes),
                    "user_id": str(user.id) if user else None,
                },
                result.status,
                actor="user" if user and primary else "system",
                ts=now,
            )
        flagged = next(
            (o for o in outcomes if o.code == "INSTRUCTION_SCAN" and o.status == "FAIL"), None
        )
        if primary and flagged is not None:
            escrow_service.audit(
                db,
                deal,
                "DOC_INSTRUCTION_DETECTED",
                3,
                {
                    "document_id": str(row.id),
                    "sources": flagged.detail.get("sources", []),
                    "codes": flagged.detail.get("codes", []),
                },
                "IGNORED",
                actor="system",
                ts=now,
            )
        # A FRAUD alert is raised automatically but only an admin re-check may resolve it.
        outcome = alerts.sync_document_alert(
            db,
            deal,
            document_id=row.id,
            doc_type=row.doc_type.value,
            failed=result.status == "FAILED",
            score=result.score,
            reason_codes=list(result.reason_codes),
            labels=LABELS,
            instruction=_flags(outcomes),
            milestone_id=row.milestone_id,
            allow_resolve=admin,
        )
        if outcome == "resolved":
            escrow_service.audit(
                db,
                deal,
                "DOC_ALERT_RESOLVED",
                0,
                {"document_id": str(row.id), "user_id": str(user.id) if user else None},
                "RESOLVED",
                actor="user",
                ts=now,
            )
    evidence.sync(db, deal, actor=user if admin else None, now=now, commit=False)
    db.commit()
    db.refresh(doc)
    return doc


def mark_check_failed(db: Session, document_id: uuid.UUID, reason: str = "CHECK_FAILED") -> None:
    """The pipeline crashed for this document: make that visible (WARNING + a finding), keep the
    milestone from verifying, and leave `recheck` as the retry path. Never raises."""
    try:
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is None:
            return
        deal = db.get(Deal, doc.deal_id)
        lock_deal_documents(db, doc.deal_id)
        now = utcnow()
        doc.extracted_json = dict(doc.extracted_json or {"doc_type": doc.doc_type.value})
        outcomes = [Outcome("EXTRACTION_COMPLETE", "WARN", {"reason": reason})]
        store_findings(db, doc, outcomes, now)
        scoring.apply_score(doc, scoring.score(outcomes), now)
        ej = dict(doc.extracted_json)
        ej[FORENSICS_KEY] = {**ej.get(FORENSICS_KEY, {}), "check_failed": True}
        doc.extracted_json = ej
        doc.check_status = CheckStatus.WARNING
        if deal is not None:
            escrow_service.audit(
                db, deal, "DOC_CHECK_FAILED", 0,
                {"document_id": str(doc.id), "reason": reason}, "CHECK_FAILED", actor="system",
            )  # fmt: skip
            evidence.sync(db, deal, commit=False)
        db.commit()
    except Exception as exc:  # pragma: no cover - last resort
        log.error(
            "mark_check_failed_failed", error=type(exc).__name__, document_id=str(document_id)
        )
        db.rollback()


def findings_of_document(db: Session, doc: Document) -> list[ForensicFinding]:
    return list(db.scalars(select(ForensicFinding).where(ForensicFinding.document_id == doc.id)))


def accept_reference(db: Session, document_id: uuid.UUID, user: CurrentUser) -> Document:
    """Mark a proforma invoice as buyer-accepted (the pinned reference), then re-check the deal."""
    doc = db.get(Document, document_id)
    if doc is None or doc.status != DocStatus.UPLOADED:
        raise NotFound("document not found")
    if doc.doc_type != DocType.PROFORMA_INVOICE:
        raise DomainError("only a proforma invoice can be the reference", "NOT_A_PROFORMA")
    deal = db.get(Deal, doc.deal_id)
    assert deal is not None
    lock_deal_documents(db, deal.id)
    ej = dict(doc.extracted_json or {"doc_type": doc.doc_type.value})
    meta = dict(ej.get(FORENSICS_KEY) or {})
    meta["accepted"] = {"by": str(user.id), "at": utcnow().isoformat()}
    ej[FORENSICS_KEY] = meta
    doc.extracted_json = ej
    escrow_service.audit(
        db, deal, "DOC_REFERENCE_ACCEPTED", 2,
        {"document_id": str(doc.id), "user_id": str(user.id)}, "ACCEPTED",
    )  # fmt: skip
    db.commit()
    return process_document(db, doc.id, user=user, action="DOC_CHECKED")
