"""Cross-lender hash registry (FR-6.2, SR-6): the same trade document must not back two things.

Two fingerprints per document: `sha256` of the file bytes (exact) and a semantic fingerprint of
its identity fields (a re-saved or re-scanned copy keeps it): invoices use seller + invoice no. +
total + currency (`documents.canonical_hash`), bills of lading shipper + B/L no. + vessel. The
document type scopes the match. The date is deliberately not part of the key: a re-scan that
misreads it would escape detection, and the invoice number plus amount already identify it.

An entry lives in one context: purpose (ESCROW_EVIDENCE | FINANCING_COLLATERAL), deal, lender.
`evaluate` answers NEW | SAME_CONTEXT | EXACT_DUPLICATE | NEAR_DUPLICATE (ACTIVE entries only):

* a conflict is an ACTIVE entry in another context: another deal, or the same deal pledged to a
  different lender. The same deal in a different purpose (evidence, then collateral) is one context.
* conflicts win over a same-context entry (fail closed); a lender asking about its own collateral
  (no deal given) is SAME_CONTEXT, and without a deal only collateral entries count at all.

Privacy: only hashes and minimal metadata are stored and returned (purpose, lender label, date).
No document text, buyer, price or deal reference ever leaves this module toward a lender.
Writes use the caller's transaction; the caller commits. Every register and every hit is audited.
"""

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.db import tenancy
from app.db.enums import DocStatus, DocType, RegistryPurpose, RegistryStatus
from app.db.models import Deal, Document, HashRegistry, Party
from app.errors import NotFound
from app.forensics.canonical import canonical_bl_hash, canonical_invoice_hash

NEW = "NEW"
SAME_CONTEXT = "SAME_CONTEXT"
EXACT_DUPLICATE = "EXACT_DUPLICATE"
NEAR_DUPLICATE = "NEAR_DUPLICATE"
DUPLICATES = (EXACT_DUPLICATE, NEAR_DUPLICATE)

ESCROW = RegistryPurpose.ESCROW_EVIDENCE
COLLATERAL = RegistryPurpose.FINANCING_COLLATERAL
INVOICE_TYPES = (DocType.PROFORMA_INVOICE, DocType.COMMERCIAL_INVOICE)


@dataclass(frozen=True, slots=True)
class Subject:
    """What the registry knows about a document: hashes and its type, nothing else."""

    sha256: str | None
    doc_type: DocType
    semantic: str | None = None


@dataclass(frozen=True, slots=True)
class Context:
    purpose: RegistryPurpose
    deal_id: uuid.UUID | None = None
    lender_id: uuid.UUID | None = None

    @property
    def key(self) -> str:
        return f"{self.purpose.value}:{self.lender_id or '-'}:{self.deal_id or '-'}"


@dataclass(frozen=True, slots=True)
class Conflict:
    """The conflicting entry, reduced to what the asker may learn."""

    entry_id: uuid.UUID
    purpose: RegistryPurpose
    lender_name: str | None
    registered_on: date


@dataclass(frozen=True, slots=True)
class Verdict:
    result: str = NEW
    conflict: Conflict | None = None
    entry_id: uuid.UUID | None = None  # the same-context entry, when there is one

    @property
    def blocked(self) -> bool:
        return self.result in DUPLICATES


@dataclass(frozen=True, slots=True)
class RegistryResult:
    """What the document pipeline consumes: NEW, or DUPLICATE with codes and ids only."""

    status: str = "NEW"  # NEW | DUPLICATE
    detail: dict[str, Any] = field(default_factory=dict)


Checker = Callable[[Session, Document], RegistryResult]


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------- fingerprints ----------


def semantic_of(doc: Document) -> str | None:
    if doc.doc_type in INVOICE_TYPES:
        return doc.canonical_hash
    if doc.doc_type == DocType.BILL_OF_LADING:
        body = doc.extracted_json or {}
        shipper, bl_no = body.get("shipper"), body.get("bl_no")
        if isinstance(shipper, str) and isinstance(bl_no, str) and shipper and bl_no:
            vessel = body.get("vessel")
            return canonical_bl_hash(shipper, bl_no, vessel if isinstance(vessel, str) else None)
    return None


def subject_of(doc: Document) -> Subject | None:
    if not doc.sha256:
        return None
    return Subject(doc.sha256, doc.doc_type, semantic_of(doc))


def invoice_semantic(seller: str, invoice_no: str, total: str, currency: str) -> str:
    return canonical_invoice_hash(seller, invoice_no, total, currency)


# ---------- lookup ----------


def lender_label(db: Session, lender_id: uuid.UUID | None) -> str | None:
    if lender_id is None:
        return None
    p = db.get(Party, lender_id)
    return (p.alias or p.legal_name) if p else None


def resolve_lender(db: Session, ref: str) -> Party:
    """A lender party by code or id. Anything else looks missing."""
    try:
        row = db.get(Party, uuid.UUID(ref))
    except ValueError:
        row = db.scalar(select(Party).where(Party.code == ref))
    if row is None or row.kind.value != "LENDER":
        raise NotFound("lender not found")
    return row


def _same_context(entry: HashRegistry, ctx: Context) -> bool:
    if ctx.deal_id is not None and entry.deal_id == ctx.deal_id:
        pledged_elsewhere = (
            entry.purpose == COLLATERAL
            and ctx.purpose == COLLATERAL
            and entry.lender_party_id != ctx.lender_id
        )
        return not pledged_elsewhere
    return (
        ctx.deal_id is None
        and ctx.purpose == COLLATERAL
        and entry.purpose == COLLATERAL
        and ctx.lender_id is not None
        and entry.lender_party_id == ctx.lender_id
    )


def _family(t: DocType) -> tuple[DocType, ...]:
    """Invoices match across proforma and commercial: the uploader picks the type freely."""
    return INVOICE_TYPES if t in INVOICE_TYPES else (t,)


def _candidates(db: Session, subject: Subject) -> list[HashRegistry]:
    parts = []
    if subject.sha256:
        parts.append(HashRegistry.sha256 == subject.sha256)
    if subject.semantic:
        parts.append(
            and_(
                HashRegistry.semantic_fingerprint == subject.semantic,
                HashRegistry.doc_type.in_(_family(subject.doc_type)),
            )
        )
    if not parts:
        return []
    return list(
        db.scalars(
            select(HashRegistry)
            .where(HashRegistry.status == RegistryStatus.ACTIVE, or_(*parts))
            .order_by(HashRegistry.registered_at, HashRegistry.id)
        ).all()
    )


def evaluate(db: Session, subject: Subject, ctx: Context) -> Verdict:
    """Read-only. Conflicts first (earliest financing collateral first), then same context."""
    rows = _candidates(db, subject)
    if ctx.deal_id is None:  # an outside lender only meets other lenders' collateral claims
        rows = [r for r in rows if r.purpose == COLLATERAL]
    conflicts = [r for r in rows if not _same_context(r, ctx)]
    if conflicts:
        conflicts.sort(key=lambda r: (r.purpose != COLLATERAL, r.registered_at))
        hit = conflicts[0]
        exact = subject.sha256 is not None and any(r.sha256 == subject.sha256 for r in conflicts)
        return Verdict(
            EXACT_DUPLICATE if exact else NEAR_DUPLICATE,
            Conflict(
                hit.id, hit.purpose, lender_label(db, hit.lender_party_id), hit.registered_at.date()
            ),
        )
    if rows:
        return Verdict(SAME_CONTEXT, entry_id=rows[0].id)
    return Verdict()


# ---------- writes ----------


def register(
    db: Session,
    subject: Subject,
    ctx: Context,
    *,
    document_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    external_ref: str | None = None,
    touch: bool = False,
    now: datetime | None = None,
) -> HashRegistry:
    """Idempotent per (sha256, context). A RELEASED entry of the same context is reactivated; an
    existing ACTIVE one only has `seen_count` raised when `touch`. Audited when created."""
    now = now or utcnow()
    assert subject.sha256 is not None, "only a stored document can be registered"
    row = db.scalar(
        select(HashRegistry).where(
            HashRegistry.sha256 == subject.sha256, HashRegistry.context_key == ctx.key
        )
    )
    created = row is None
    if row is None:
        row = HashRegistry(
            id=uuid.uuid4(),
            sha256=subject.sha256,
            context_key=ctx.key,
            purpose=ctx.purpose,
            doc_type=subject.doc_type,
            lender_party_id=ctx.lender_id,
            deal_id=ctx.deal_id,
            registered_at=now,
            seen_count=1,
            status=RegistryStatus.ACTIVE,
            exact_hits=0,
            near_hits=0,
        )
        db.add(row)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:  # a concurrent registration won: use it
            db.expunge(row)
            row = db.scalars(
                select(HashRegistry).where(
                    HashRegistry.sha256 == subject.sha256, HashRegistry.context_key == ctx.key
                )
            ).one()
            created = False
    reactivated = row.status == RegistryStatus.RELEASED
    if reactivated:
        row.status, row.released_at = RegistryStatus.ACTIVE, None
    if not created and touch:
        row.seen_count += 1
        row.last_seen_at = now
    row.semantic_fingerprint = subject.semantic or row.semantic_fingerprint
    row.document_id = document_id or row.document_id
    row.registered_by_user_id = row.registered_by_user_id or user_id
    row.external_ref = external_ref or row.external_ref
    db.flush()
    if created or reactivated:
        write_audit(
            db,
            actor="user" if user_id else "system",
            action="REGISTRY_REGISTERED",
            tier=0,
            params={
                "entry_id": str(row.id),
                "sha256": subject.sha256,
                "purpose": ctx.purpose.value,
                "doc_type": subject.doc_type.value,
                "deal_id": str(ctx.deal_id) if ctx.deal_id else None,
                "lender_id": str(ctx.lender_id) if ctx.lender_id else None,
            },
            result="REGISTERED" if created else "REACTIVATED",
            ts=now,
            deal_id=ctx.deal_id,
        )
    return row


def record_hit(
    db: Session,
    verdict: Verdict,
    subject: Subject,
    *,
    source: str,
    deal_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> None:
    """Count a blocked attempt on the entry it hit and write the Tier 3 audit row."""
    if verdict.conflict is None:
        return
    now = now or utcnow()
    row = db.get(HashRegistry, verdict.conflict.entry_id, with_for_update=True)
    if row is not None:
        if verdict.result == EXACT_DUPLICATE:
            row.exact_hits += 1
        else:
            row.near_hits += 1
        row.last_seen_at = now
    write_audit(
        db,
        actor="user" if user_id else "system",
        action="REGISTRY_DUPLICATE_HIT",
        tier=3,
        params={
            "entry_id": str(verdict.conflict.entry_id),
            "sha256": subject.sha256,
            "doc_type": subject.doc_type.value,
            "source": source,
            "deal_id": str(deal_id) if deal_id else None,
        },
        result=verdict.result,
        ts=now,
        deal_id=deal_id,
    )


def release_for_deal(
    db: Session,
    deal_id: uuid.UUID,
    *,
    purposes: tuple[RegistryPurpose, ...] = (ESCROW, COLLATERAL),
    now: datetime | None = None,
) -> int:
    """Deal COMPLETED or loan repaid: entries stay for history but stop blocking. Audited."""
    now = now or utcnow()
    rows = db.scalars(
        select(HashRegistry).where(
            HashRegistry.deal_id == deal_id,
            HashRegistry.purpose.in_(purposes),
            HashRegistry.status == RegistryStatus.ACTIVE,
        )
    ).all()
    for r in rows:
        r.status, r.released_at = RegistryStatus.RELEASED, now
    if rows:
        write_audit(
            db,
            actor="system",
            action="REGISTRY_RELEASED",
            tier=0,
            params={"deal_id": str(deal_id), "entries": sorted(str(r.id) for r in rows)},
            result="RELEASED",
            ts=now,
            deal_id=deal_id,
        )
    return len(rows)


# ---------- the document pipeline seam ----------


def _default_check(db: Session, doc: Document) -> RegistryResult:
    subject = subject_of(doc)
    if subject is None:
        return RegistryResult()
    # Checks of different deals run under different deal locks: serialise the lookup and the
    # registration that follows (same transaction) so two copies cannot both pass.
    lock_registry(db)
    verdict = evaluate(db, subject, Context(ESCROW, deal_id=doc.deal_id))
    if verdict.conflict is None:
        return RegistryResult()
    c = verdict.conflict
    return RegistryResult(
        "DUPLICATE",
        {
            "scope": "registry",
            "result": verdict.result,
            "purpose": c.purpose.value,
            "lender": c.lender_name,
            "registered_on": c.registered_on.isoformat(),
            "entry_id": str(c.entry_id),
        },
    )


_checker: Checker = _default_check


def check(db: Session, doc: Document) -> RegistryResult:
    return _checker(db, doc)


def set_checker(fn: Checker | None) -> None:
    global _checker
    _checker = fn or _default_check


@contextmanager
def use_checker(fn: Checker) -> Iterator[None]:
    previous = _checker
    set_checker(fn)
    try:
        yield
    finally:
        set_checker(previous)


def after_document_check(
    db: Session,
    doc: Document,
    *,
    duplicate: dict[str, Any] | None,
    failed: bool,
    primary: bool,
    user_id: uuid.UUID | None,
    now: datetime,
) -> None:
    """Called by the pipeline once a document has its verdict. A registry duplicate is counted and
    audited (primary document only, so sibling re-runs do not inflate it); a document that is not
    FAILED is registered as escrow evidence of its deal; a FAILED one stops holding its entry."""
    subject = subject_of(doc)
    if subject is None:
        return
    if duplicate is not None and duplicate.get("scope") == "registry":
        if primary and duplicate.get("entry_id"):
            row = db.get(HashRegistry, uuid.UUID(str(duplicate["entry_id"])))
            if row is not None:
                verdict = Verdict(
                    str(duplicate.get("result") or EXACT_DUPLICATE),
                    Conflict(row.id, row.purpose, None, row.registered_at.date()),
                )
                record_hit(
                    db,
                    verdict,
                    subject,
                    source="UPLOAD",
                    deal_id=doc.deal_id,
                    user_id=user_id,
                    now=now,
                )
        return
    if failed:  # fail closed: an entry registered earlier keeps blocking
        return
    if duplicate is None and doc.status == DocStatus.UPLOADED:
        register(
            db,
            subject,
            Context(ESCROW, deal_id=doc.deal_id),
            document_id=doc.id,
            user_id=user_id,
            touch=primary,
            now=now,
        )


# ---------- financing ----------


def invoice_subjects(db: Session, deal: Deal) -> list[tuple[Document, Subject]]:
    docs = db.scalars(
        select(Document).where(
            Document.deal_id == deal.id,
            Document.status == DocStatus.UPLOADED,
            Document.doc_type.in_(INVOICE_TYPES),
            Document.sha256.is_not(None),
        )
    ).all()
    out = []
    for d in docs:
        s = subject_of(d)
        if s is not None:
            out.append((d, s))
    return out


def lock_registry(db: Session) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"registry:{tenancy.current_schema() or ''}"},
    )


def invoice_gate(db: Session, deal: Deal, lender_id: uuid.UUID) -> tuple[Verdict, Subject | None]:
    """First blocking verdict among the deal's invoices if it were pledged to `lender_id`."""
    ctx = Context(COLLATERAL, deal_id=deal.id, lender_id=lender_id)
    for _doc, subject in invoice_subjects(db, deal):
        verdict = evaluate(db, subject, ctx)
        if verdict.blocked:
            return verdict, subject
    return Verdict(), None


def register_collateral(
    db: Session,
    deal: Deal,
    lender_id: uuid.UUID,
    *,
    external_ref: str | None,
    user_id: uuid.UUID | None,
    now: datetime | None = None,
) -> int:
    ctx = Context(COLLATERAL, deal_id=deal.id, lender_id=lender_id)
    rows = invoice_subjects(db, deal)
    for doc, subject in rows:
        register(
            db,
            subject,
            ctx,
            document_id=doc.id,
            user_id=user_id,
            external_ref=external_ref,
            touch=True,
            now=now,
        )
    return len(rows)
