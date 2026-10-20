"""FR-6 document forensics. Upload (buyer or supplier of the deal, or admin), list and read
(suppliers get a status-only projection), recheck (buyer or admin), hidden text (not suppliers) and
a signed, short-lived file download. Foreign deals and documents look missing (404)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
from app.db.enums import DocType
from app.db.session import batch_session, get_db
from app.errors import Forbidden, PayloadTooLarge, UnsupportedMedia
from app.schemas.documents import (
    DocumentDetail,
    DocumentList,
    HiddenTextOut,
    UploadResult,
)
from app.services import deals as deal_service
from app.services import escrow as escrow_service
from app.services.documents import pipeline, read, signing, upload
from app.services.documents.storage import get_storage

router = APIRouter(tags=["documents"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]
UPLOAD_TYPES = Annotated[DocType, Form(description="Document type")]


def _check_in_background(document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Own session (the request's is closed). A failure is made visible on the document
    (WARNING, check_failed) so it can be retried with recheck; it is never raised to the client."""
    import structlog

    from app.auth.deps import to_current
    from app.db.models import User as UserRow

    log = structlog.get_logger("setu.documents")
    try:
        with batch_session() as db:
            row = db.get(UserRow, user_id)
            pipeline.process_document(db, document_id, user=to_current(row) if row else None)
    except Exception as exc:
        log.error("background_check_failed", error=type(exc).__name__, document_id=str(document_id))
        with batch_session() as db:
            pipeline.mark_check_failed(db, document_id)


@router.post("/deals/{deal_id}/documents", response_model=UploadResult, status_code=201)
def upload_document(
    deal_id: str,
    db: Db,
    user: User,
    background: BackgroundTasks,
    doc_type: UPLOAD_TYPES,
    file: Annotated[UploadFile, File(description="PDF, PNG or JPG, at most 10 MB")],
    wait: Annotated[bool, Query(description="Run the checks before answering")] = False,
) -> UploadResult:
    """Store a document and check it. By default the checks run in the background and the
    response has `checking: QUEUED`; with `wait=true` they finish first (`DONE`; buyers and
    admins only, a supplier's request is queued)."""
    deal = deal_service.find_deal(db, user, deal_id)
    limit = get_settings().document_max_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"file is larger than {limit // (1024 * 1024)} MB", "FILE_TOO_LARGE")
    outcome = upload.accept_upload(db, user, deal, doc_type, file.filename, data)
    doc = outcome.document
    done = outcome.reused
    role = read.role_of(user, deal)
    if not outcome.reused:
        # Inline checking holds a request open: only buyers and admins may ask for it.
        if wait and role in ("BUYER", "ADMIN"):
            try:
                doc = pipeline.process_document(db, doc.id, user=user)
            except Exception:
                pipeline.mark_check_failed(db, doc.id)
                db.refresh(doc)
            done = True
        else:
            background.add_task(_check_in_background, doc.id, user.id)
    return UploadResult(
        document=read.document_out(db, doc, deal, role),
        reused=outcome.reused,
        checking="DONE" if done else "QUEUED",
    )


@router.get("/deals/{deal_id}/documents", response_model=DocumentList)
def list_documents(deal_id: str, db: Db, user: User) -> DocumentList:
    """Documents of a deal with their check status (suppliers: status only)."""
    return read.list_documents(db, user, deal_service.find_deal(db, user, deal_id))


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Db, user: User) -> DocumentDetail:
    """Extracted fields, findings, verdict and a short-lived signed file URL. Suppliers get the
    status only (no score, findings, fields or hidden text)."""
    doc, deal = read.find_document(db, user, document_id)
    return read.detail(db, user, doc, deal)


@router.post("/documents/{document_id}/recheck", response_model=DocumentDetail)
def recheck(document_id: uuid.UUID, db: Db, user: User) -> DocumentDetail:
    """Re-extract and re-check one document (and its siblings). Buyer of the deal or admin."""
    doc, deal = read.find_document(db, user, document_id)
    escrow_service.authorize(db, user, deal, "DOC_RECHECK")
    doc = pipeline.process_document(
        db, doc.id, user=user, force_extract=True, action="DOC_RECHECKED_BY_USER"
    )
    return read.detail(db, user, doc, deal)


@router.post("/documents/{document_id}/accept-reference", response_model=DocumentDetail)
def accept_reference(document_id: uuid.UUID, db: Db, user: User) -> DocumentDetail:
    """The buyer (or an admin) accepts this proforma invoice, e.g. one that only WARNed, as the
    deal's reference for booking, dates and bank details. Tier 2 human action, audited."""
    doc, deal = read.find_document(db, user, document_id)
    escrow_service.authorize(db, user, deal, "DOC_ACCEPT_REFERENCE")
    doc = pipeline.accept_reference(db, doc.id, user)
    return read.detail(db, user, doc, deal)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, Field(min_length=3, max_length=200)]


@router.post("/documents/{document_id}/reject", response_model=DocumentDetail)
def reject(document_id: uuid.UUID, body: RejectIn, db: Db, user: User) -> DocumentDetail:
    """Withdraw an uploaded file (forged, wrong or replaced) so it no longer counts as evidence.
    Buyer of the deal or admin; audited. The file and its findings stay on record."""
    doc, deal = read.find_document(db, user, document_id)
    escrow_service.authorize(db, user, deal, "DOC_REJECT")
    doc = pipeline.reject_document(db, doc.id, user, body.reason)
    return read.detail(db, user, doc, deal)


@router.get("/documents/{document_id}/hidden-text", response_model=HiddenTextOut)
def hidden_text(document_id: uuid.UUID, db: Db, user: User) -> HiddenTextOut:
    """Text found hidden in the file (untrusted; shown as inert text). Not for suppliers."""
    doc, deal = read.find_document(db, user, document_id)
    return read.hidden_text(db, user, doc, deal)


# Verified in Chromium (Playwright build 1248, <iframe> and <object>): the built-in PDF viewer
# renders under every policy tried, including `sandbox`; this is the tightest useful one. Firefox
# (pdf.js) could not be driven in this environment, so it is unverified: if it ever refuses,
# drop the CSP for PDFs and keep nosniff, frame-ancestors and Referrer-Policy (docs/forensics.md).
INLINE_CSP = (
    "default-src 'none'; img-src 'self' data:; object-src 'self'; style-src 'unsafe-inline'; "
    "frame-ancestors 'self'"
)
DOWNLOAD_CSP = "sandbox; default-src 'none'"


@router.get("/documents/{document_id}/file")
def download(
    document_id: uuid.UUID,
    token: str,
    db: Db,
    user: User,
    inline: Annotated[bool, Query(description="Serve a validated PDF/PNG/JPG for preview")] = False,
) -> Response:
    """The stored file via a signed URL from `GET /documents/{id}` (expires after a few minutes
    and only works for the user it was issued to). An attachment by default; `inline=1` serves
    only PDF/PNG/JPG whose bytes still match their stored type, for the in-page viewer."""
    parsed = signing.decode(token)
    if parsed is None or parsed.document_id != document_id or parsed.user_id != user.id:
        raise Forbidden("this download link is invalid or has expired")
    doc, deal = read.find_document(db, user, document_id)
    if not read.may_download(user, deal, doc):
        raise Forbidden("you can only download documents you uploaded")
    data = get_storage().get(doc.storage_path)
    if inline and (doc.mime_type not in read.INLINE_TYPES or upload.sniff(data) != doc.mime_type):
        raise UnsupportedMedia("this file cannot be previewed", "NOT_PREVIEWABLE")
    escrow_service.audit(
        db,
        deal,
        "DOC_DOWNLOADED",
        0,
        {
            "document_id": str(doc.id),
            "user_id": str(user.id),
            "role": user.role.value,
            "inline": inline,
        },
        "OK",
    )
    db.commit()
    safe_name = doc.file_name.encode("ascii", "replace").decode().replace('"', "")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": INLINE_CSP if inline else DOWNLOAD_CSP,
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "private, no-store",
        },
    )
