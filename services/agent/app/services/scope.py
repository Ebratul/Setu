"""Shared lookups for buyer-scoped reads (analysis, cash flow, alerts, dashboard)."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, can_read_party
from app.config import get_settings
from app.db.enums import PartyKind
from app.db.models import DemoState, Party
from app.errors import DomainError, Forbidden, NotFound


def demo_today(db: Session) -> date:
    anchor = db.scalar(select(DemoState.anchor_date).where(DemoState.id == 1))
    return anchor or get_settings().demo_today


def party(db: Session, party_id: uuid.UUID) -> Party:
    p = db.get(Party, party_id)
    if p is None:
        raise NotFound("party not found")
    return p


def scope_party(db: Session, user: CurrentUser, party_id: uuid.UUID | None) -> Party | None:
    """Buyers default to (and may only read) their own party; admin/judge may pass any buyer."""
    pid = party_id or (None if user.reads_all else user.party_id)
    if pid is None:
        return None
    if not can_read_party(user, pid):
        raise Forbidden("you can only read your own business")
    p = party(db, pid)
    if p.kind != PartyKind.BUYER:
        raise DomainError("party_id must be a buyer")
    return p


def require_buyer(db: Session, user: CurrentUser, party_id: uuid.UUID | None) -> Party:
    buyer = scope_party(db, user, party_id)
    if buyer is None:
        raise DomainError("party_id is required for admin and judge users")
    return buyer
