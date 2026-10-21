"""Check a suspicious e-mail (SR-3, SR-6). E-mail text is data: this reads it with the
deterministic `email_guard`, never executes anything in it, never changes an account, and stores
only a hash of the text. A request to pay a different account is always BLOCKED."""

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth.deps import CurrentUser
from app.config import REPO_ROOT, get_settings
from app.db.enums import (
    AlertStatus,
    AlertType,
    ApprovalAction,
    ApprovalStatus,
    Role,
    Severity,
)
from app.db.models import Alert, ApprovalRequest, Deal
from app.errors import Forbidden, NotFound
from app.schemas.approvals import EmailCheckOut, SignalOut
from app.security.email_guard import EmailReading, read_email
from app.services import approval_otp
from app.services import escrow as escrow_service

DEMO_EMAIL = REPO_ROOT / "data" / "demo" / "SETU-2026-0001" / "email_beneficiary_change.txt"
SIGNALS: dict[str, tuple[str, str]] = {
    "ACCOUNT_CHANGE_REQUEST": (
        "Asks you to pay a different bank account",
        "অন্য একটি ব্যাংক অ্যাকাউন্টে পেমেন্ট করতে বলছে",
    ),
    "NEW_ACCOUNT_DETAILS": (
        "Contains new bank or SWIFT details",
        "নতুন ব্যাংক বা SWIFT তথ্য আছে",
    ),
    "URGENCY_PRESSURE": ("Pushes you to act today", "আজই কাজ করতে চাপ দিচ্ছে"),
    "DISCOURAGES_VERIFICATION": (
        "Tells you not to call or verify",
        "ফোন বা যাচাই করতে নিষেধ করছে",
    ),
}
NEXT_STEPS = (
    [
        "Do not pay into the account in the email.",
        "Verify by video call with the supplier, using contact details you already know.",
        "Ask the supplier to submit the change in the supplier portal. You will then approve it "
        "with a code after a cooling-off period.",
    ],
    [
        "ইমেইলের অ্যাকাউন্টে পেমেন্ট করবেন না।",
        "আপনার আগে থেকে জানা যোগাযোগ নম্বরে সরবরাহকারীর সঙ্গে ভিডিও কলে যাচাই করুন।",
        "সরবরাহকারীকে সাপ্লায়ার পোর্টালে পরিবর্তনের অনুরোধ করতে বলুন। পরে বিরতির শেষে কোড দিয়ে আপনি "
        "অনুমোদন করবেন।",
    ],
)


def demo_email_text() -> str:
    if not get_settings().demo_mode or get_settings().app_env == "prod":
        raise NotFound("not found")
    return DEMO_EMAIL.read_text(encoding="utf-8")


def _open_email_approval(db: Session, deal: Deal | None) -> uuid.UUID | None:
    if deal is None:
        return None
    for appr in db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.deal_id == deal.id,
            ApprovalRequest.action == ApprovalAction.CHANGE_BENEFICIARY,
            ApprovalRequest.status.in_((ApprovalStatus.PENDING, ApprovalStatus.APPROVED)),
        )
    ):
        if appr.params.get("requested_via") == "email":
            return appr.id
    return None


def _find_deal(
    db: Session, user: CurrentUser, reading: EmailReading, deal_reference: str | None
) -> Deal | None:
    refs = ([deal_reference] if deal_reference else []) + reading.deal_refs
    for ref in refs:
        deal = db.scalars(select(Deal).where(Deal.reference == ref)).first()
        if deal is None:
            continue
        if user.role == Role.ADMIN or (user.role == Role.BUYER and deal.buyer_id == user.party_id):
            return deal
    return None


def check_email(
    db: Session,
    user: CurrentUser,
    text: str,
    deal_reference: str | None = None,
    *,
    now: datetime | None = None,
) -> EmailCheckOut:
    if user.role not in (Role.BUYER, Role.ADMIN) or (
        user.role == Role.BUYER and user.party_id is None
    ):
        raise Forbidden("only a buyer (or an admin) can check an e-mail")
    now = now or escrow_service.utcnow()
    reading = read_email(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    deal = _find_deal(db, user, reading, deal_reference)
    party = user.party_id if user.role == Role.BUYER else (deal.buyer_id if deal else None)
    blocked = reading.verdict == "BLOCKED"
    codes = list(reading.signals) + [f.code for f in reading.findings]

    seq = write_audit(
        db,
        actor="user",
        action="EMAIL_BENEFICIARY_CHANGE_BLOCKED"
        if blocked
        else "EMAIL_INSTRUCTION_DETECTED"
        if reading.findings
        else "EMAIL_CHECKED",
        tier=3 if blocked or reading.findings else 0,
        params={
            "text_sha256": digest,
            "verdict": reading.verdict,
            "codes": codes,
            "deal_ref": deal.reference if deal else None,
            "user_id": str(user.id),
        },
        result=reading.verdict,
        ts=now,
        deal_id=deal.id if deal else None,
    )

    alert_id: uuid.UUID | None = None
    if blocked and party is not None:
        key = f"email-block:{str(party)[:8]}:{digest[:20]}"
        alert = db.scalars(select(Alert).where(Alert.key == key)).first()
        if alert is None:
            alert = Alert(
                id=uuid.uuid4(),
                key=key,
                party_id=party,
                deal_id=deal.id if deal else None,
                milestone_id=None,
                type=AlertType.FRAUD,
                severity=Severity.CRITICAL,
                status=AlertStatus.OPEN,
                title_en="Blocked: an email asked to change a payment account",
                title_bn="আটকানো হয়েছে: ইমেইলে পেমেন্ট অ্যাকাউন্ট বদলাতে বলা হয়েছে",
                message_en="Setu never changes payment accounts based on email. "
                "Verify by video call.",
                message_bn="ইমেইলের ভিত্তিতে সেতু কখনো পেমেন্ট অ্যাকাউন্ট বদলায় না। ভিডিও কলে যাচাই করুন।",
                facts={"text_sha256": digest, "signals": codes, "audit_seq": seq},
            )
            db.add(alert)
        alert_id = alert.id
        approval_otp.emit(
            db,
            kind="BLOCKED",
            now=now,
            deal=deal,
            approval=None,
            parties=[party],
            tier=3,
            actor="system",
            title=("Blocked a payment-redirection email", "পেমেন্ট বদলের ইমেইল আটকানো হয়েছে"),
            detail=(
                "Setu never changes payment accounts based on email.",
                "ইমেইলের ভিত্তিতে সেতু কখনো পেমেন্ট অ্যাকাউন্ট বদলায় না।",
            ),
            audit_seq=seq,
        )
    related = _open_email_approval(db, deal)
    db.commit()

    if blocked:
        title = (
            "Blocked: this email asks to change a payment account",
            "আটকানো হয়েছে: এই ইমেইল পেমেন্ট অ্যাকাউন্ট বদলাতে বলছে",
        )
        message = (
            "Setu never changes payment accounts based on email. Verify by video call.",
            "ইমেইলের ভিত্তিতে সেতু কখনো পেমেন্ট অ্যাকাউন্ট বদলায় না। ভিডিও কলে যাচাই করুন।",
        )
    elif reading.verdict == "SUSPICIOUS":
        title = ("Suspicious wording found", "সন্দেহজনক ভাষা পাওয়া গেছে")
        message = (
            "The email contains instructions or pressure. Setu ignored them; nothing was changed.",
            "ইমেইলে নির্দেশ বা চাপ আছে। সেতু তা উপেক্ষা করেছে; কিছুই বদলায়নি।",
        )
    else:
        title = ("No payment change requested", "পেমেন্ট বদলের অনুরোধ পাওয়া যায়নি")
        message = (
            "No request to change a payment account was found. Setu still never acts on email.",
            "পেমেন্ট অ্যাকাউন্ট বদলের অনুরোধ পাওয়া যায়নি। তবুও সেতু ইমেইলের ভিত্তিতে কিছু করে না।",
        )
    return EmailCheckOut(
        verdict=reading.verdict,  # type: ignore[arg-type]
        blocked=blocked,
        title_en=title[0],
        title_bn=title[1],
        message_en=message[0],
        message_bn=message[1],
        next_steps_en=NEXT_STEPS[0] if blocked else [],
        next_steps_bn=NEXT_STEPS[1] if blocked else [],
        signals=[
            SignalOut(code=c, label_en=SIGNALS[c][0], label_bn=SIGNALS[c][1])
            for c in reading.signals
            if c in SIGNALS
        ],
        deal_reference=deal.reference if deal else None,
        alert_id=alert_id,
        audit_seq=seq,
        related_approval_id=related,
        text_sha256=digest,
    )
