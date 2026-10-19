"""Approval plumbing shared by the request creators (risk gate, escrow release) and the human
approval service: expiry, the simulated OTP and the readable event feed.

The OTP is a 6-digit code kept only as an HMAC (with the approval id). The clear code exists in one
place: the buyer's simulated "Demo phone" inbox, and only while DEMO_MODE is on. Nothing in an
ordinary API response ever carries it."""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ApprovalEvent, ApprovalRequest, Deal, DemoPhoneMessage

DEV_SECRET = b"setu-dev-otp-secret-not-secret"


def _secret() -> bytes:
    s = get_settings()
    for candidate in (s.otp_secret_seed, s.demo_session_secret):
        if candidate is not None and candidate.get_secret_value().strip():
            return candidate.get_secret_value().encode()
    return DEV_SECRET


def hash_code(approval_id: uuid.UUID, code: str) -> str:
    return hmac.new(_secret(), f"{approval_id}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(approval: ApprovalRequest, code: str) -> bool:
    if approval.otp_hash is None:
        return False
    return hmac.compare_digest(hash_code(approval.id, code), approval.otp_hash.strip())


def cooling_off_until(now: datetime, tier: int) -> datetime | None:
    if tier < 3:
        return None
    return now + timedelta(seconds=get_settings().cooling_off_seconds)


def expiry(now: datetime) -> datetime:
    return now + timedelta(minutes=get_settings().approval_expiry_minutes)


def issue_otp(db: Session, approval: ApprovalRequest, deal: Deal | None, now: datetime) -> None:
    """New code for a Tier 3 approval (also the "resend"). The attempt counter is NOT reset: three
    wrong codes lock the request however often a new code is sent."""
    code = f"{secrets.randbelow(10**6):06d}"
    approval.otp_hash = hash_code(approval.id, code)
    approval.otp_expires_at = now + timedelta(seconds=get_settings().otp_ttl_seconds)
    if get_settings().demo_mode and get_settings().app_env != "prod" and deal is not None:
        minutes = max(1, get_settings().otp_ttl_seconds // 60)
        db.add(
            DemoPhoneMessage(
                id=uuid.uuid4(),
                party_id=deal.buyer_id,
                approval_id=approval.id,
                body=(
                    f"Setu (Simulated SMS): your approval code is {code} for deal "
                    f"{deal.reference}. It expires in {minutes} min. Never share it."
                ),
                code=code,
                created_at=now,
            )
        )


def emit(
    db: Session,
    *,
    kind: str,
    now: datetime,
    deal: Deal | None,
    approval: ApprovalRequest | None,
    parties: list[uuid.UUID | None],
    tier: int,
    actor: str,
    title: tuple[str, str],
    detail: tuple[str, str] = ("", ""),
    audit_seq: int | None = None,
) -> None:
    for party in dict.fromkeys(parties):
        db.add(
            ApprovalEvent(
                id=uuid.uuid4(),
                ts=now,
                party_id=party,
                deal_id=deal.id if deal else None,
                approval_id=approval.id if approval else None,
                kind=kind,
                tier=tier,
                actor=actor,
                title_en=title[0][:200],
                title_bn=title[1][:200],
                detail_en=detail[0][:600],
                detail_bn=detail[1][:900],
                audit_seq=audit_seq,
            )
        )


def on_created(
    db: Session,
    approval: ApprovalRequest,
    deal: Deal,
    *,
    context_hash: str,
    now: datetime,
    actor: str,
    audit_seq: int | None,
    summary: tuple[str, str],
) -> None:
    """Called by every creator right after the row exists (same transaction)."""
    approval.context_hash = context_hash or None
    approval.expires_at = expiry(now)
    if approval.tier == 3:
        issue_otp(db, approval, deal, now)
    emit(
        db,
        kind="CREATED",
        now=now,
        deal=deal,
        approval=approval,
        parties=[deal.buyer_id],
        tier=approval.tier,
        actor=actor,
        title=(f"Approval needed (Tier {approval.tier})", f"অনুমোদন প্রয়োজন (টিয়ার {approval.tier})"),
        detail=summary,
        audit_seq=audit_seq,
    )


def latest_message(db: Session, approval_id: uuid.UUID) -> DemoPhoneMessage | None:
    return db.scalars(
        select(DemoPhoneMessage)
        .where(DemoPhoneMessage.approval_id == approval_id)
        .order_by(DemoPhoneMessage.created_at.desc())
    ).first()
