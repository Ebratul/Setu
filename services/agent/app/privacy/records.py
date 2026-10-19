"""Known values for the detectors and persistence of safe transparency records."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.models import BankAccount, Deal, PrivacyRecord
from app.privacy.detectors import ACCT, NAME
from app.privacy.gateway import PrivacyGateway


def load_known(db: Session | None, user: CurrentUser | None = None) -> dict[str, set[str]]:
    """Account holders and stored account numbers the caller may see, plus their own name:
    masked even when no context word ("A/C", "account") stands next to them. Scoped like every
    other read, so masking never reveals whether another tenant holds a value."""
    if db is None:
        return {}
    q = select(BankAccount.holder_name, BankAccount.account_number)
    if user is not None and not user.reads_all:
        mine = {user.party_id} if user.party_id else set()
        suppliers = (
            select(Deal.supplier_id).where(Deal.buyer_id == user.party_id)
            if user.party_id
            else select(Deal.supplier_id).where(False)
        )
        q = q.where(BankAccount.party_id.in_(suppliers) | BankAccount.party_id.in_(mine))
    try:
        rows = db.execute(q).all()
    except Exception:
        db.rollback()
        return {}
    names = {h for h, _ in rows if h and len(h.split()) >= 2}
    if user is not None and len(user.display_name) >= 4:
        names.add(user.display_name)
    return {NAME: names, ACCT: {n for _, n in rows if n}}


def new_gateway(db: Session | None, user: CurrentUser | None = None, **kw: Any) -> PrivacyGateway:
    return PrivacyGateway(known=load_known(db, user), **kw)


def persist_calls(
    db: Session,
    gw: PrivacyGateway,
    *,
    source: str,
    user_id: uuid.UUID | None,
    thread_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    run_id: str | None = None,
) -> int:
    """Store one row per not-yet-stored call: the masked payload and counters, never the vault."""
    n = 0
    for c in gw.calls:
        if c.persisted:
            continue
        db.add(
            PrivacyRecord(
                id=uuid.uuid4(),
                source=source,
                user_id=user_id,
                thread_id=thread_id,
                message_id=message_id,
                document_id=document_id,
                run_id=run_id,
                node=c.node,
                model=c.model,
                sent=c.sent,
                masked_payload=c.payload,
                masked_output=c.output,
                masked_by_type=dict(c.stats.masked_by_type),
                protected=c.stats.protected,
                leaked=c.stats.leaked_count,
                chars_sent=c.stats.chars_sent,
            )
        )
        c.persisted = True
        n += 1
    if n:
        db.flush()
    return n
