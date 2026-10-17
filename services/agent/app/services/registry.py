"""Registry API logic: the lender-facing check, the admin listing and stats, and the per-document
box. The lender check is the simulated external institution: it answers with the minimum and never
registers anything. When it is asked about a document of a Setu deal and finds a duplicate, the
attempt is also raised as a FRAUD alert on that deal, so the buyer and admin see it."""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import DocType, RegistryPurpose, RegistryStatus, Role
from app.db.models import Deal, Document, HashRegistry
from app.errors import DomainError, Forbidden
from app.forensics.parse_fields import parse_document, title_doc_type
from app.schemas.registry import (
    DocumentRegistryOut,
    LenderCheckIn,
    LenderCheckOut,
    RegistryEntryOut,
    RegistryList,
    RegistryStatsOut,
    SemanticFields,
)
from app.security.audit import write_audit
from app.services import alerts, hash_registry
from app.services.documents import read
from app.services.documents.extract_text import extract_text

SEMANTIC_TYPES = {
    DocType.PROFORMA_INVOICE,
    DocType.COMMERCIAL_INVOICE,
    DocType.BILL_OF_LADING,
}


@dataclass(frozen=True, slots=True)
class FileCheck:
    sha256: str
    subject: hash_registry.Subject


def subject_from_fields(f: SemanticFields) -> hash_registry.Subject:
    doc_type = DocType(f.doc_type)
    if doc_type == DocType.BILL_OF_LADING:
        semantic = hash_registry.canonical_bl_hash(f.seller, f.number, f.vessel)
    else:
        if f.total is None or f.currency is None:
            raise DomainError("an invoice needs total and currency", "FIELDS_INCOMPLETE")
        semantic = hash_registry.invoice_semantic(f.seller, f.number, f.total, f.currency)
    return hash_registry.Subject(None, doc_type, semantic)


def subject_from_file(data: bytes) -> hash_registry.Subject:
    """sha256 plus, when the PDF reads cleanly, the semantic fingerprint (no LLM involved)."""
    sha = hashlib.sha256(data).hexdigest()
    doc_type, semantic = DocType.OTHER, None
    try:
        pdf = extract_text(data, "application/pdf") if data[:5] == b"%PDF-" else None
        kind = title_doc_type(pdf.visible_text) if pdf is not None else None
        if pdf is not None and kind in {t.value for t in SEMANTIC_TYPES}:
            doc_type = DocType(kind)
            fields = parse_document(pdf.visible_text, kind).fields
            semantic = _semantic_of_fields(doc_type, fields.model_dump(mode="json"))
    except Exception:  # an unreadable file is still checked by its bytes
        semantic = None
    return hash_registry.Subject(sha, doc_type, semantic)


def _semantic_of_fields(doc_type: DocType, f: dict) -> str | None:  # type: ignore[type-arg]
    if doc_type == DocType.BILL_OF_LADING:
        if f.get("shipper") and f.get("bl_no"):
            return hash_registry.canonical_bl_hash(f["shipper"], f["bl_no"], f.get("vessel"))
        return None
    if f.get("seller") and f.get("invoice_no") and f.get("total") is not None:
        return hash_registry.invoice_semantic(
            f["seller"], f["invoice_no"], str(f["total"]), f.get("currency") or "USD"
        )
    return None


def _no_supplier(user: CurrentUser) -> None:
    if user.role == Role.SUPPLIER:
        raise Forbidden("the registry check is not available to suppliers")


def lender_check(
    db: Session, user: CurrentUser, body: LenderCheckIn, file: bytes | None = None
) -> LenderCheckOut:
    """Would `lender_id` be financing a document that is already registered elsewhere?"""
    _no_supplier(user)
    lender = hash_registry.resolve_lender(db, body.lender_id)
    if body.document_id is None and user.role not in (Role.ADMIN, Role.JUDGE):
        raise Forbidden("buyers can check their own documents only")
    given = [x for x in (body.sha256, body.document_id, body.fields, file) if x is not None]
    if len(given) != 1:
        raise DomainError("give exactly one of sha256, document_id, fields or a file", "BAD_QUERY")
    deal: Deal | None = None
    doc: Document | None = None
    if body.document_id is not None:
        doc, deal = read.find_document(db, user, body.document_id)
        subject = hash_registry.subject_of(doc)
        if subject is None:
            raise DomainError("this document has no stored file to check", "NOT_CHECKABLE")
    elif body.sha256 is not None:
        subject = hash_registry.Subject(body.sha256.lower(), DocType.OTHER)
    elif body.fields is not None:
        subject = subject_from_fields(body.fields)
    else:
        assert file is not None
        subject = subject_from_file(file)
    ctx = hash_registry.Context(
        RegistryPurpose.FINANCING_COLLATERAL,
        deal_id=deal.id if deal else None,
        lender_id=lender.id,
    )
    verdict = hash_registry.evaluate(db, subject, ctx)
    if verdict.conflict is not None:
        c = verdict.conflict
        hash_registry.record_hit(
            db, verdict, subject, source="LENDER_CHECK", deal_id=deal.id if deal else None,
            user_id=user.id,
        )  # fmt: skip
        if deal is not None and doc is not None:
            alerts.raise_registry_alert(
                db, deal, scope=f"lender:{lender.code}", result=verdict.result,
                purpose=c.purpose.value, holder=c.lender_name, registered_on=c.registered_on,
                doc_type=doc.doc_type.value,
            )  # fmt: skip
        db.commit()
        return LenderCheckOut(
            result=verdict.result,  # type: ignore[arg-type]
            already_registered_for=c.purpose.value,  # type: ignore[arg-type]
            registered_on=c.registered_on,
            held_by=c.lender_name if c.purpose == RegistryPurpose.FINANCING_COLLATERAL else None,
        )
    write_audit(
        db, actor="user", action="REGISTRY_LENDER_CHECK", tier=0,
        params={"lender_id": str(lender.id), "sha256": subject.sha256, "user_id": str(user.id)},
        result=verdict.result, deal_id=deal.id if deal else None,
    )  # fmt: skip
    db.commit()
    return LenderCheckOut(result=verdict.result)  # type: ignore[arg-type]


def find_visible(db: Session, user: CurrentUser, document_id: uuid.UUID) -> tuple[Document, Deal]:
    """A document of a deal the caller may see, who is not the supplier of that deal."""
    doc, deal = read.find_document(db, user, document_id)
    if read.role_of(user, deal) == "SUPPLIER":
        raise Forbidden("the registry box is for the buyer of the deal")
    return doc, deal


def document_registry(
    db: Session, user: CurrentUser, document_id: uuid.UUID
) -> DocumentRegistryOut:
    doc, _deal = find_visible(db, user, document_id)
    return state_of(db, doc)


def state_of(db: Session, doc: Document) -> DocumentRegistryOut:
    """Registry state of one stored document: duplicate of another context, registered, or not."""
    subject = hash_registry.subject_of(doc)
    if subject is None:
        return DocumentRegistryOut(document_id=doc.id, state="NOT_REGISTERED", result="NEW")
    ctx = hash_registry.Context(RegistryPurpose.ESCROW_EVIDENCE, deal_id=doc.deal_id)
    verdict = hash_registry.evaluate(db, subject, ctx)
    if verdict.conflict is not None:
        c = verdict.conflict
        return DocumentRegistryOut(
            document_id=doc.id,
            state="DUPLICATE",
            result=verdict.result,  # type: ignore[arg-type]
            purpose=c.purpose.value,  # type: ignore[arg-type]
            registered_on=c.registered_on,
            lender_name=c.lender_name,
        )
    own = db.scalars(
        select(HashRegistry)
        .where(
            HashRegistry.sha256 == subject.sha256,
            HashRegistry.deal_id == doc.deal_id,
            HashRegistry.status == RegistryStatus.ACTIVE,
        )
        .order_by(HashRegistry.purpose, HashRegistry.registered_at)
    ).first()
    if own is None:
        return DocumentRegistryOut(document_id=doc.id, state="NOT_REGISTERED", result="NEW")
    return DocumentRegistryOut(
        document_id=doc.id,
        state="REGISTERED",
        result="SAME_CONTEXT",
        purpose=own.purpose.value,  # type: ignore[arg-type]
        registered_on=own.registered_at.date(),
        lender_name=hash_registry.lender_label(db, own.lender_party_id),
        seen_count=own.seen_count,
    )


def _entry(db: Session, r: HashRegistry) -> RegistryEntryOut:
    ref = db.scalar(select(Deal.reference).where(Deal.id == r.deal_id)) if r.deal_id else None
    return RegistryEntryOut(
        id=r.id,
        sha256_prefix=r.sha256[:12],
        semantic_prefix=r.semantic_fingerprint[:12] if r.semantic_fingerprint else None,
        doc_type=r.doc_type.value,
        purpose=r.purpose.value,  # type: ignore[arg-type]
        lender_name=hash_registry.lender_label(db, r.lender_party_id),
        deal_ref=ref,
        registered_on=r.registered_at.date(),
        last_seen_at=r.last_seen_at,
        seen_count=r.seen_count,
        exact_hits=r.exact_hits,
        near_hits=r.near_hits,
        status=r.status.value,  # type: ignore[arg-type]
    )


def list_entries(
    db: Session,
    status: RegistryStatus | None,
    result: str | None,
    purpose: RegistryPurpose | None,
    limit: int,
    offset: int,
) -> RegistryList:
    q = select(HashRegistry)
    if status is not None:
        q = q.where(HashRegistry.status == status)
    if purpose is not None:
        q = q.where(HashRegistry.purpose == purpose)
    if result == hash_registry.EXACT_DUPLICATE:
        q = q.where(HashRegistry.exact_hits > 0)
    elif result == hash_registry.NEAR_DUPLICATE:
        q = q.where(HashRegistry.near_hits > 0)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(HashRegistry.registered_at.desc(), HashRegistry.id).limit(limit).offset(offset)
    ).all()
    return RegistryList(items=[_entry(db, r) for r in rows], total=total)


def stats(db: Session) -> RegistryStatsOut:
    by_status = dict(
        db.execute(select(HashRegistry.status, func.count()).group_by(HashRegistry.status)).all()
    )
    by_purpose = dict(
        db.execute(select(HashRegistry.purpose, func.count()).group_by(HashRegistry.purpose)).all()
    )
    exact, near = db.execute(
        select(
            func.coalesce(func.sum(HashRegistry.exact_hits), 0),
            func.coalesce(func.sum(HashRegistry.near_hits), 0),
        )
    ).one()
    active = by_status.get(RegistryStatus.ACTIVE, 0)
    released = by_status.get(RegistryStatus.RELEASED, 0)
    return RegistryStatsOut(
        entries=active + released,
        active=active,
        released=released,
        by_purpose={p.value: by_purpose.get(p, 0) for p in RegistryPurpose},
        duplicates_blocked=int(exact) + int(near),
        exact_blocked=int(exact),
        near_blocked=int(near),
    )
