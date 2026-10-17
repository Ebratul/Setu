"""Upload: validate by magic bytes, sanitise the name, store under a hash-derived key and create
the Document row (status UPLOADED, check PENDING). Checking runs afterwards (background task,
or `pipeline.process_document` synchronously).

Duplicates: the sha256 is UNIQUE. Re-uploading identical bytes to the SAME deal returns the
existing document (`reused=True`, nothing new is stored or re-checked). Identical bytes already
stored on ANOTHER deal are refused with 409 `DUPLICATE_DOCUMENT`: the same invoice cannot back two
deals (audited, tier 0). The cross-lender question "was this financed elsewhere?" is the hash
registry's (`services/hash_registry.py`, Phase 15); this rule only covers this platform.
"""

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import CheckStatus, DealStatus, DocStatus, DocType
from app.db.models import Deal, Document
from app.domain import escrow as rules
from app.errors import Conflict, DomainError, Forbidden, PayloadTooLarge, UnsupportedMedia
from app.services import escrow as escrow_service
from app.services.documents import evidence
from app.services.documents.pipeline import utcnow
from app.services.documents.storage import get_storage

PDF, PNG, JPEG = "application/pdf", "image/png", "image/jpeg"
EXTENSION = {PDF: ".pdf", PNG: ".png", JPEG: ".jpg"}
PDF_TYPES = frozenset(
    {
        DocType.PROFORMA_INVOICE,
        DocType.COMMERCIAL_INVOICE,
        DocType.PACKING_LIST,
        DocType.BILL_OF_LADING,
        DocType.CERTIFICATE_OF_ORIGIN,
        DocType.BILL_OF_ENTRY,
    }
)
NAME_MAX = 120
_SAFE = re.compile(r"[^A-Za-z0-9._() -]")


def sniff(data: bytes) -> str | None:
    """MIME type from the leading bytes only (the extension and client type are not trusted)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"%PDF-"):  # at offset 0: no polyglot with a leading image or script
        return PDF
    return None


def sanitise_filename(name: str | None, mime: str) -> str:
    """Base name only, ASCII-safe, capped, with the extension of the sniffed type."""
    raw = unicodedata.normalize("NFKC", name or "")
    base = re.split(r"[\\/]", raw)[-1]
    base = "".join(ch for ch in base if ch.isprintable())
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = _SAFE.sub("_", stem).strip(" ._-")
    stem = re.sub(r"[_ ]{2,}", "_", stem)[: NAME_MAX - 5] or "document"
    return stem + EXTENSION[mime]


@dataclass(slots=True)
class UploadOutcome:
    document: Document
    reused: bool = False


def _target_milestone(db: Session, deal: Deal, doc_type: DocType) -> uuid.UUID | None:
    for ms in escrow_service.milestones_of(db, deal.id):
        if ms.status not in rules.SETTLED and doc_type.value in ms.required_evidence:
            return ms.id
    return None


def _forbid(db: Session, user: CurrentUser, deal: Deal) -> None:
    escrow_service.audit(
        db,
        deal,
        "DOC_UPLOAD_FORBIDDEN",
        0,
        {"deal_id": str(deal.id), "user_id": str(user.id), "role": user.role.value},
        "FORBIDDEN",
    )
    db.commit()
    raise Forbidden("this demo user is read-only")


def accept_upload(
    db: Session,
    user: CurrentUser,
    deal: Deal,
    doc_type: DocType,
    filename: str | None,
    data: bytes,
    *,
    now: datetime | None = None,
) -> UploadOutcome:
    role = escrow_service.require_view(user, deal)
    if role not in ("BUYER", "SUPPLIER", "ADMIN"):
        _forbid(db, user, deal)
    if deal.status == DealStatus.CANCELLED:
        raise Conflict("this deal is cancelled", "DEAL_CLOSED")
    limit = get_settings().document_max_bytes
    if len(data) > limit:
        raise PayloadTooLarge(f"file is larger than {limit // (1024 * 1024)} MB", "FILE_TOO_LARGE")
    if not data:
        raise DomainError("the file is empty", "EMPTY_FILE")
    mime = sniff(data)
    if mime is None:
        raise UnsupportedMedia("only PDF, PNG and JPG files are accepted", "UNSUPPORTED_FILE_TYPE")
    if doc_type == DocType.PRODUCTION_PHOTO and mime == PDF:
        raise UnsupportedMedia("a production photo must be a PNG or JPG image", "WRONG_FILE_TYPE")
    if doc_type in PDF_TYPES and mime != PDF:
        raise UnsupportedMedia(f"{doc_type.value} must be a PDF", "WRONG_FILE_TYPE")
    now = now or utcnow()
    sha = hashlib.sha256(data).hexdigest()
    name = sanitise_filename(filename, mime)

    existing = db.scalars(select(Document).where(Document.sha256 == sha)).first()
    if existing is not None:
        if existing.deal_id == deal.id:
            return UploadOutcome(existing, reused=True)
        escrow_service.audit(
            db,
            deal,
            "DOC_DUPLICATE_REJECTED",
            0,
            {"deal_id": str(deal.id), "sha256": sha, "user_id": str(user.id)},
            "DUPLICATE_DOCUMENT",
            ts=now,
        )
        db.commit()
        raise Conflict(
            "this exact file is already stored on another deal and cannot be used again",
            "DUPLICATE_DOCUMENT",
        )

    path = get_storage().put(f"deals/{deal.id}/{sha}{EXTENSION[mime]}", data)
    placeholder = db.scalars(
        select(Document).where(
            Document.deal_id == deal.id,
            Document.doc_type == doc_type,
            Document.status == DocStatus.PLACEHOLDER,
            Document.file_name == name,
        )
    ).first()
    doc = placeholder or Document(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:document:{deal.id}:{sha}"),
        key=f"doc:{deal.reference}:{sha[:20]}",
        deal_id=deal.id,
        milestone_id=_target_milestone(db, deal, doc_type),
        doc_type=doc_type,
    )
    doc.file_name = name
    doc.storage_path = path
    doc.mime_type = mime
    doc.sha256 = sha
    doc.canonical_hash = None
    doc.size_bytes = len(data)
    doc.status = DocStatus.UPLOADED
    doc.check_status = CheckStatus.PENDING
    doc.extracted_json = None
    doc.uploaded_at = now
    doc.uploaded_by_user_id = user.id
    if placeholder is None:
        db.add(doc)
    try:
        db.flush()
    except IntegrityError:  # a concurrent upload of the same bytes won the race
        db.rollback()
        winner = db.scalars(select(Document).where(Document.sha256 == sha)).first()
        if winner is not None and winner.deal_id == deal.id:
            return UploadOutcome(winner, reused=True)
        raise Conflict("this exact file is already stored", "DUPLICATE_DOCUMENT") from None
    escrow_service.audit(
        db,
        deal,
        "DOC_UPLOADED",
        0,
        {
            "document_id": str(doc.id),
            "deal_id": str(deal.id),
            "doc_type": doc_type.value,
            "sha256": sha,
            "size_bytes": len(data),
            "mime": mime,
            "user_id": str(user.id),
        },
        "UPLOADED",
        ts=now,
    )
    # An unchecked document demotes a VERIFIED milestone to PENDING straight away; release also
    # refuses while any of the milestone's documents is unchecked.
    evidence.sync(db, deal, now=now, commit=False)
    db.commit()
    return UploadOutcome(doc)
