"""Verification documents for onboarding. Reuses the P14 upload rules (magic-byte MIME, size cap,
sanitised names, private hash-derived storage keys, short-lived signed URLs bound to the viewer);
the files are never served from a public path and never reach a model."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.ratelimit import check_limit
from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import Role, VerificationDocStatus, VerificationDocType
from app.db.models import User, VerificationDocument
from app.errors import Conflict, DomainError, Forbidden, NotFound, PayloadTooLarge, UnsupportedMedia
from app.schemas.onboarding import VerificationDocumentOut
from app.services import onboarding
from app.services.documents import signing, upload
from app.services.documents.storage import get_storage

ALLOWED: dict[Role, frozenset[VerificationDocType]] = {
    Role.BUYER: frozenset(
        {
            VerificationDocType.TRADE_LICENSE,
            VerificationDocType.IRC,
            VerificationDocType.TIN_CERT,
            VerificationDocType.OTHER,
        }
    ),
    Role.SUPPLIER: frozenset(
        {
            VerificationDocType.BUSINESS_LICENSE,
            VerificationDocType.BANK_PROOF,
            VerificationDocType.OTHER,
        }
    ),
}
MAX_DOCS = 12


def add(
    db: Session, user: User, doc_type: VerificationDocType, filename: str | None, data: bytes
) -> VerificationDocumentOut:
    settings = get_settings()
    check_limit(
        "onboarding-upload", str(user.id), settings.rate_limit_onboarding_upload_per_hour, 3600
    )
    profile = onboarding.editable_profile(db, user)
    if doc_type not in ALLOWED.get(user.role, frozenset()):
        raise Forbidden(
            "this document type is not needed for your account type", "DOC_TYPE_NOT_ALLOWED"
        )
    limit = settings.document_max_bytes
    if len(data) > limit:
        raise PayloadTooLarge(f"file is larger than {limit // (1024 * 1024)} MB", "FILE_TOO_LARGE")
    if not data:
        raise DomainError("the file is empty", "EMPTY_FILE")
    mime = upload.sniff(data)
    if mime is None:
        raise UnsupportedMedia("only PDF, PNG and JPG files are accepted", "UNSUPPORTED_FILE_TYPE")
    sha = hashlib.sha256(data).hexdigest()
    mine = onboarding.documents_of(db, user)
    same = next((d for d in mine if d.sha256 == sha and d.type == doc_type), None)
    if same is not None:
        return onboarding.doc_out(same)
    if len(mine) >= MAX_DOCS:
        raise Conflict("too many documents; delete one first", "TOO_MANY_DOCUMENTS")
    key = get_storage().put(f"onboarding/{user.id}/{sha}{upload.EXTENSION[mime]}", data)
    doc = VerificationDocument(
        id=uuid.uuid4(),
        user_id=user.id,
        profile_id=profile.id,
        type=doc_type,
        storage_key=key,
        original_name=upload.sanitise_filename(filename, mime)[:160],
        mime=mime,
        size=len(data),
        sha256=sha,
        status=VerificationDocStatus.UPLOADED,
        created_at=datetime.now(UTC),
    )
    db.add(doc)
    profile.step = max(profile.step, 4)
    onboarding.audit(
        db,
        user,
        "onboarding.document_uploaded",
        {"document_id": str(doc.id), "doc_type": doc_type.value, "sha256": sha, "size": len(data)},
    )
    db.commit()
    return onboarding.doc_out(doc)


def remove(db: Session, user: User, doc_id: uuid.UUID) -> None:
    onboarding.editable_profile(db, user)
    doc = db.get(VerificationDocument, doc_id)
    if doc is None or doc.user_id != user.id:
        raise NotFound("document not found")
    shared = db.scalar(
        select(func.count())
        .select_from(VerificationDocument)
        .where(
            VerificationDocument.storage_key == doc.storage_key, VerificationDocument.id != doc.id
        )
    )
    key = doc.storage_key
    db.delete(doc)
    onboarding.audit(db, user, "onboarding.document_deleted", {"document_id": str(doc_id)})
    db.commit()
    if not shared:
        get_storage().delete(key)


def can_view(actor: CurrentUser) -> bool:
    return actor.role == Role.ADMIN and actor.privileged


def visible(db: Session, actor: CurrentUser, doc_id: uuid.UUID) -> VerificationDocument:
    doc = db.get(VerificationDocument, doc_id)
    if doc is None or not (doc.user_id == actor.id or can_view(actor)):
        raise NotFound("document not found")  # foreign documents look missing
    return doc


def signed_url(db: Session, actor: CurrentUser, doc_id: uuid.UUID) -> tuple[str, int]:
    doc = visible(db, actor, doc_id)
    token = signing.make_token(doc.id, actor.id)
    return f"/onboarding/documents/{doc.id}/file?token={signing.encode(token)}", token.expires_at


def fetch(
    db: Session, actor: CurrentUser, doc_id: uuid.UUID, token: str
) -> tuple[VerificationDocument, bytes]:
    parsed = signing.decode(token)
    if parsed is None or parsed.document_id != doc_id or parsed.user_id != actor.id:
        raise Forbidden("this download link is invalid or has expired")
    doc = visible(db, actor, doc_id)
    data = get_storage().get(doc.storage_key)
    if upload.sniff(data) != doc.mime:
        raise UnsupportedMedia("this file cannot be previewed", "NOT_PREVIEWABLE")
    if doc.user_id != actor.id:
        row = db.get(User, actor.id)
        if row is not None:
            onboarding.audit(db, row, "onboarding.document_viewed", {"document_id": str(doc.id)})
            db.commit()
    return doc, data
