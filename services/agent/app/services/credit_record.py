"""FR-8: the signed completed-deal credit record. Issued once, when the last tranche of a deal is
released (escrow COMPLETED): parties, amounts, milestones, on-time flag, disputes and the sha256 of
the evidence files. `payload_hash = sha256(canonical_json(payload))`, signed with the audit key
(Ed25519), so a lender can verify it with the public key alone. Simulated data only."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.audit.keys import key_id, load_signing_key, sign_hash, verify_signature
from app.auth.deps import CurrentUser
from app.db.enums import DocStatus, MilestoneStatus
from app.db.models import CreditRecord, Deal, Document, Milestone, Party
from app.errors import Forbidden, NotFound
from app.security.audit import canonical_json, sha256_hex

RECORD_TYPE = "setu.completed_deal.v1"


def _payload(
    db: Session, deal: Deal, milestones: list[Milestone], completed_on: str, on_time: bool
) -> dict[str, Any]:
    buyer, supplier = db.get(Party, deal.buyer_id), db.get(Party, deal.supplier_id)
    assert buyer is not None and supplier is not None
    docs = db.scalars(
        select(Document)
        .where(Document.deal_id == deal.id, Document.status == DocStatus.UPLOADED)
        .order_by(Document.doc_type, Document.sha256)
    ).all()
    return {
        "record_type": RECORD_TYPE,
        "simulated": True,
        "deal_ref": deal.reference,
        "buyer": buyer.legal_name,
        "supplier": supplier.legal_name,
        "amount": str(Decimal(deal.goods_value).quantize(Decimal("0.01"))),
        "currency": deal.currency,
        "milestones": [str(Decimal(m.amount).quantize(Decimal("0.01"))) for m in milestones],
        "opened_on": deal.opened_on.isoformat(),
        "completed_on": completed_on,
        "on_time": on_time,
        "disputes": deal.dispute_count,
        "evidence": [{"doc_type": d.doc_type.value, "sha256": d.sha256} for d in docs if d.sha256],
    }


def issue(
    db: Session, deal: Deal, milestones: list[Milestone], completed_on: str, now: datetime
) -> CreditRecord:
    """Idempotent: one record per deal. Caller commits."""
    existing = db.scalar(select(CreditRecord).where(CreditRecord.deal_id == deal.id))
    if existing is not None:
        return existing
    released = [m for m in milestones if m.status == MilestoneStatus.RELEASED]
    on_time = all(m.released_at is not None and m.released_at.date() <= m.due_on for m in released)
    deal.on_time = on_time
    payload = _payload(db, deal, milestones, completed_on, on_time)
    digest = sha256_hex(canonical_json(payload))
    key = load_signing_key()
    row = CreditRecord(
        id=uuid.uuid4(),
        deal_id=deal.id,
        buyer_id=deal.buyer_id,
        supplier_id=deal.supplier_id,
        amount=deal.goods_value,
        currency=deal.currency,
        on_time=on_time,
        dispute_count=deal.dispute_count,
        completed_on=deal.completed_on,
        payload=payload,
        payload_hash=digest,
        signature=sign_hash(key, digest),
        key_id=key_id(key.public_key()),
        issued_at=now,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        actor="system",
        action="CREDIT_RECORD_ISSUED",
        tier=0,
        params={
            "deal_ref": deal.reference,
            "record_id": str(row.id),
            "payload_hash": digest,
            "on_time": on_time,
            "key_id": row.key_id,
        },
        result="ISSUED",
        deal_id=deal.id,
        ts=now,
    )
    return row


def verify(row: CreditRecord) -> tuple[bool, bool]:
    """(payload hash matches the stored payload, signature verifies against the signing key)."""
    digest = sha256_hex(canonical_json(row.payload))
    hash_ok = digest == row.payload_hash
    sig_ok = hash_ok and verify_signature(
        load_signing_key().public_key(), row.payload_hash, row.signature
    )
    return hash_ok, sig_ok


def for_deal(db: Session, user: CurrentUser, deal_ref: str) -> CreditRecord:
    """The record of a deal the caller may see (buyer, supplier, admin, judge); else 404."""
    deal = db.scalar(select(Deal).where(Deal.reference == deal_ref))
    if deal is None and len(deal_ref) == 36:
        try:
            deal = db.get(Deal, uuid.UUID(deal_ref))
        except ValueError:
            deal = None
    if deal is None:
        raise NotFound("credit record not found")
    from app.services import escrow as escrow_service

    try:
        escrow_service.require_view(user, deal)
    except (NotFound, Forbidden):
        raise NotFound("credit record not found") from None
    row = db.scalar(select(CreditRecord).where(CreditRecord.deal_id == deal.id))
    if row is None:
        raise NotFound("this deal has no credit record yet; it is issued when the deal completes")
    return row
