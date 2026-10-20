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
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.enums import ApprovalAction, MemberRole, UserStatus
from app.db.models import (
    ApprovalEvent,
    ApprovalRequest,
    Deal,
    DemoPhoneMessage,
    PartyMember,
    User,
)
from app.domain.money import q2
from app.errors import ServiceUnavailable
from app.services import mail

log = structlog.get_logger("setu.approval_otp")
DEV_SECRET = b"setu-dev-otp-secret-not-secret"
COOLING_OFF_FLOOR_PROD = 600  # SR-9: never shorter in production, whatever the settings say
APPROVER_ROLES = (MemberRole.OWNER, MemberRole.FINANCE)

ACTION_LABELS: dict[ApprovalAction, tuple[str, str]] = {
    ApprovalAction.RELEASE_MILESTONE: ("Release a payment tranche", "পেমেন্ট কিস্তি ছাড় করা"),
    ApprovalAction.CHANGE_BENEFICIARY: (
        "Change the supplier's receiving account",
        "সরবরাহকারীর প্রাপক অ্যাকাউন্ট বদল",
    ),
    ApprovalAction.LOCK_FX_RATE: ("Lock the FX rate", "বিনিময় হার লক করা"),
    ApprovalAction.CHANGE_MILESTONE_SCHEDULE: (
        "Set the milestone schedule",
        "মাইলস্টোন সূচি নির্ধারণ",
    ),
    ApprovalAction.CONFIRM_MILESTONES: (
        "Confirm the milestone schedule",
        "মাইলস্টোন সূচি নিশ্চিত করা",
    ),
    ApprovalAction.FUND_ESCROW: ("Deposit into escrow", "এসক্রোতে জমা"),
    ApprovalAction.ACCEPT_FINANCING: ("Accept a financing offer", "অর্থায়ন প্রস্তাব গ্রহণ"),
}


def _secret() -> bytes:
    """HMAC key for OTP and step-up codes. In prod only OTP_SECRET_SEED counts (the startup guard
    makes a missing one unreachable; this keeps the code safe if the guard is bypassed)."""
    s = get_settings()
    if s.app_env == "prod":
        seed = s.otp_secret_seed
        if seed is None or len(seed.get_secret_value()) < 32:
            raise RuntimeError("OTP_SECRET_SEED (>= 32 chars) is required when APP_ENV=prod")
        return seed.get_secret_value().encode()
    for candidate in (s.otp_secret_seed, s.demo_session_secret):
        if candidate is not None and candidate.get_secret_value().strip():
            return candidate.get_secret_value().encode()
    return DEV_SECRET


def secret_key() -> bytes:
    return _secret()


def hash_code(approval_id: uuid.UUID, code: str) -> str:
    return hmac.new(_secret(), f"{approval_id}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(approval: ApprovalRequest, code: str) -> bool:
    if approval.otp_hash is None:
        return False
    return hmac.compare_digest(hash_code(approval.id, code), approval.otp_hash.strip())


def cooling_off_until(now: datetime, tier: int) -> datetime | None:
    if tier < 3:
        return None
    settings = get_settings()
    seconds = settings.cooling_off_seconds
    if settings.app_env == "prod":
        seconds = max(seconds, COOLING_OFF_FLOOR_PROD)
    return now + timedelta(seconds=seconds)


def expiry(now: datetime) -> datetime:
    return now + timedelta(minutes=get_settings().approval_expiry_minutes)


def _signable(user: User) -> bool:
    """Demo accounts cannot sign in when AUTH_MODE=neon, so they are never approvers there."""
    return not user.is_demo or get_settings().auth_mode == "demo"


def approvers(db: Session, party_id: uuid.UUID) -> list[User]:
    """Active OWNER and FINANCE members of a party: the people who may approve for it. A user with a
    party and no `party_members` row is the OWNER (seeded demo users). VIEWERs never appear."""
    rows = db.execute(
        select(User, PartyMember.member_role)
        .outerjoin(
            PartyMember,
            (PartyMember.user_id == User.id) & (PartyMember.party_id == party_id),
        )
        .where(User.party_id == party_id, User.status == UserStatus.ACTIVE)
        .order_by(User.created_at, User.email)
    ).all()
    return [u for u, role in rows if (role or MemberRole.OWNER) in APPROVER_ROLES and _signable(u)]


def _what(approval: ApprovalRequest) -> tuple[str, str]:
    label = ACTION_LABELS[approval.action]
    if approval.action in (ApprovalAction.CHANGE_BENEFICIARY, ApprovalAction.CONFIRM_MILESTONES):
        return label
    amount = approval.params.get("amount")
    currency = approval.params.get("currency") or approval.params.get("base") or ""
    try:
        text = f"{currency} {q2(Decimal(str(amount))):,.2f}".strip() if amount else ""
    except (InvalidOperation, ValueError):
        text = ""
    return (f"{label[0]} ({text})", f"{label[1]} ({text})") if text else label


def _email_code(
    db: Session, approval: ApprovalRequest, deal: Deal, code: str, minutes: int
) -> None:
    """Mail the code to each approver of the buyer party (AUTH_MODE=neon). Delivery to at least
    one of them is enough; if none works, raise without any trace of the code."""
    recipients = approvers(db, deal.buyer_id)
    delivered = 0
    for user in recipients:
        message = mail.code_mail(
            user.email,
            code,
            subject=(f"Setu approval code for {deal.reference}", "সেতু অনুমোদন কোড"),
            what=_what(approval),
            reference=deal.reference,
            minutes=minutes,
        )
        try:
            mail.deliver(message)
            delivered += 1
        except ServiceUnavailable:
            log.warning("otp_mail_failed", approval_id=str(approval.id))
    if delivered == 0:
        raise ServiceUnavailable("could not send the code")


def issue_otp(db: Session, approval: ApprovalRequest, deal: Deal | None, now: datetime) -> None:
    """New code for a Tier 3 approval (also the "resend"). The attempt counter is NOT reset: three
    wrong codes lock the request however often a new code is sent. With AUTH_MODE=neon the code is
    emailed to the party's approvers (raises ServiceUnavailable if no mail went out); in the demo
    it goes to the simulated phone. It is in no response and no audit row."""
    code = f"{secrets.randbelow(10**6):06d}"
    approval.otp_hash = hash_code(approval.id, code)
    approval.otp_expires_at = now + timedelta(seconds=get_settings().otp_ttl_seconds)
    minutes = max(1, get_settings().otp_ttl_seconds // 60)
    if get_settings().demo_mode and get_settings().app_env != "prod" and deal is not None:
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
    if get_settings().auth_mode == "neon" and deal is not None:
        _email_code(db, approval, deal, code, minutes)


def issue_otp_quietly(
    db: Session, approval: ApprovalRequest, deal: Deal | None, now: datetime
) -> bool:
    """issue_otp for paths that must not fail (creating a request, opening the inbox): a delivery
    problem is logged and the approval stays usable through "resend"."""
    try:
        issue_otp(db, approval, deal, now)
    except ServiceUnavailable:
        log.warning("otp_not_delivered", approval_id=str(approval.id))
        return False
    return True


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
        issue_otp_quietly(db, approval, deal, now)
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
