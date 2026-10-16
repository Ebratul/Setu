"""FR-2 alert engine: evaluates the pure rules in app/domain/alerts.py on a buyer's forecast and
upserts the results by stable key.

- New key → insert OPEN. Existing key → update content only when it changed (re-runs are no-ops).
- An OPEN/ACKNOWLEDGED engine alert whose key is no longer produced → RESOLVED
  (`resolved_by=engine`). If its condition comes back it reopens; a user-resolved one stays closed.
Only SHORTFALL, DEADLINE and FX_OPPORTUNITY are engine-owned; KYB/FRAUD/INFO alerts are untouched.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, can_read_party
from app.db.enums import AlertStatus, Role
from app.db.models import Alert, Deal, Milestone, Party
from app.domain.alerts import (
    ENGINE_TYPES,
    AlertDraft,
    deadline_alerts,
    fx_alerts,
    shortfall_alerts,
)
from app.domain.cashflow import Flow, Forecast
from app.domain.money import ZERO, Money
from app.errors import Forbidden, NotFound
from app.schemas.cashflow import AlertAction, AlertList, AlertOut, AlertPreview, RecomputeOut
from app.services.analysis import fmt
from app.services.cashflow import (
    DEFAULT_DAYS,
    BuyerBook,
    compute,
    deadlines,
    fx_payments,
    load_book,
)
from app.services.scope import require_buyer

ACTION_LABELS: dict[str, tuple[str, str]] = {
    "COMPARE_FINANCING": ("Compare financing options", "অর্থায়নের বিকল্প তুলনা করুন"),
    "FUND_MILESTONE": ("Review the deal", "চুক্তিটি দেখুন"),
    "PLAN_DUTY_PAYMENT": ("Plan the duty payment", "শুল্ক পরিশোধের পরিকল্পনা করুন"),
    "UPLOAD_BILL_OF_ENTRY": ("Upload bill of entry", "বিল অব এন্ট্রি আপলোড করুন"),
    "REVIEW_CASHFLOW": ("Open cash flow", "নগদ প্রবাহ দেখুন"),
    "REVIEW_FX_TIMING": ("Review payment timing", "পরিশোধের সময় দেখুন"),
}
SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def evaluate(
    db: Session, book: BuyerBook, fc: Forecast, buffer: Money, flows: Sequence[Flow] | None = None
) -> list[AlertDraft]:
    code = book.buyer.code
    view = book if flows is None else replace(book, flows=list(flows))
    shortfalls = shortfall_alerts(code, fc, buffer, book.today)
    covered = {(a.deal_ref, a.milestone_seq, a.due_on) for a in shortfalls if a.milestone_seq}
    drafts = [
        *shortfalls,
        *(
            d
            for d in deadline_alerts(code, deadlines(view), book.today)
            # the shortfall alert already covers this payment
            if (d.deal_ref, d.milestone_seq, d.due_on) not in covered
        ),
        *fx_alerts(code, fx_payments(db, view), book.today),
    ]
    return sorted(drafts, key=sort_key)


def sort_key(d: AlertDraft | Alert) -> tuple[int, str, str]:
    due = d.due_on.isoformat() if d.due_on else "9999"
    return (SEVERITY_ORDER.get(d.severity, 9), due, d.key)


def action_out(action: dict[str, Any] | None) -> AlertAction | None:
    if not action:
        return None
    en, bn = ACTION_LABELS.get(action["code"], (action["code"], action["code"]))
    return AlertAction(
        code=action["code"], label_en=en, label_bn=bn, route=action["route"], query=action["query"]
    )


def draft_action(d: AlertDraft) -> dict[str, Any]:
    return {"code": d.action.code, "route": d.action.route, "query": dict(d.action.query)}


def preview(d: AlertDraft) -> AlertPreview:
    return AlertPreview(
        key=d.key,
        type=d.type,  # type: ignore[arg-type]
        severity=d.severity,  # type: ignore[arg-type]
        title_en=d.title_en,
        title_bn=d.title_bn,
        message_en=d.message_en,
        message_bn=d.message_bn,
        amount=f"{d.amount.amount}" if d.amount else None,
        currency=d.amount.currency if d.amount else None,
        due_on=d.due_on,
        deal_ref=d.deal_ref,
        milestone_seq=d.milestone_seq,
        action=action_out(draft_action(d)),
        facts=dict(d.facts),
    )


def _ids(db: Session, d: AlertDraft) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if d.deal_ref is None:
        return None, None
    deal_id = db.scalar(select(Deal.id).where(Deal.reference == d.deal_ref))
    ms_id = None
    if deal_id is not None and d.milestone_seq is not None:
        ms_id = db.scalar(
            select(Milestone.id).where(
                Milestone.deal_id == deal_id, Milestone.seq == d.milestone_seq
            )
        )
    return deal_id, ms_id


def _values(db: Session, party: Party, d: AlertDraft) -> dict[str, Any]:
    deal_id, ms_id = _ids(db, d)
    return {
        "party_id": party.id,
        "deal_id": deal_id,
        "milestone_id": ms_id,
        "type": d.type,
        "severity": d.severity,
        "title_en": d.title_en,
        "title_bn": d.title_bn,
        "message_en": d.message_en,
        "message_bn": d.message_bn,
        "amount": d.amount.amount if d.amount else None,
        "currency": d.amount.currency if d.amount else None,
        "due_on": d.due_on,
        "facts": {**d.facts, "action": draft_action(d), "engine": "fr2-v1"},
    }


def recompute_book(db: Session, book: BuyerBook) -> RecomputeOut:
    """Run the engine for one buyer and upsert. Flushes; the caller commits."""
    buffer = Money(ZERO, book.currency)
    fc = compute(book, book.flows, DEFAULT_DAYS)
    drafts = evaluate(db, book, fc, buffer)
    existing = {
        a.key: a
        for a in db.scalars(
            select(Alert).where(Alert.party_id == book.buyer.id, Alert.type.in_(ENGINE_TYPES))
        ).all()
    }
    created = updated = reopened = resolved = 0
    keys = set()
    for d in drafts:
        keys.add(d.key)
        values = _values(db, book.buyer, d)
        row = existing.get(d.key)
        if row is None:
            db.add(
                Alert(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:{d.key}"),
                    key=d.key,
                    status=AlertStatus.OPEN,
                    **values,
                )
            )
            created += 1
            continue
        worse = _escalated(row, d)
        if row.status == AlertStatus.RESOLVED and (
            row.facts.get("resolved_by") == "engine" or worse
        ):
            row.status = AlertStatus.OPEN
            reopened += 1
        elif row.status == AlertStatus.ACKNOWLEDGED and worse:
            row.status = AlertStatus.OPEN
            reopened += 1
            values["facts"] = {**values["facts"], **_keep(row.facts)}
        else:
            values["facts"] = {**values["facts"], **_keep(row.facts)}
        changed = {k: v for k, v in values.items() if getattr(row, k) != v}
        if changed:
            for k, v in changed.items():
                setattr(row, k, v)
            updated += 1
    for k, row in existing.items():
        if k not in keys and row.status != AlertStatus.RESOLVED:
            row.status = AlertStatus.RESOLVED
            row.facts = {**row.facts, "resolved_by": "engine"}
            resolved += 1
    db.flush()
    open_count = sum(
        1
        for a in db.scalars(select(Alert).where(Alert.party_id == book.buyer.id)).all()
        if a.status != AlertStatus.RESOLVED
    )
    return RecomputeOut(
        party_id=book.buyer.id,
        created=created,
        updated=updated,
        reopened=reopened,
        resolved=resolved,
        open=open_count,
    )


def _escalated(row: Alert, d: AlertDraft) -> bool:
    """A closed or acknowledged alert reopens when its severity rises or its amount grows."""
    if SEVERITY_ORDER.get(d.severity, 9) < SEVERITY_ORDER.get(row.severity, 9):
        return True
    return d.amount is not None and row.amount is not None and d.amount.amount > row.amount


def _keep(facts: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in facts.items() if k == "resolved_by"}


def recompute(db: Session, user: CurrentUser, party_id: uuid.UUID | None) -> RecomputeOut:
    out = recompute_book(db, load_book(db, require_buyer(db, user, party_id)))
    db.commit()
    return out


def alert_out(db: Session, a: Alert) -> AlertOut:
    deal_ref = db.scalar(select(Deal.reference).where(Deal.id == a.deal_id)) if a.deal_id else None
    seq = (
        db.scalar(select(Milestone.seq).where(Milestone.id == a.milestone_id))
        if a.milestone_id
        else None
    )
    facts = {k: v for k, v in (a.facts or {}).items() if k not in ("action", "engine")}
    return AlertOut(
        id=a.id,
        key=a.key,
        type=a.type,  # type: ignore[arg-type]
        severity=a.severity,  # type: ignore[arg-type]
        status=a.status,  # type: ignore[arg-type]
        title_en=a.title_en,
        title_bn=a.title_bn,
        message_en=a.message_en,
        message_bn=a.message_bn,
        amount=fmt(a.amount) if a.amount is not None else None,
        currency=a.currency,
        due_on=a.due_on,
        deal_ref=deal_ref,
        milestone_seq=seq,
        action=action_out((a.facts or {}).get("action")),
        facts=facts,
        created_at=a.created_at,
    )


def party_alerts(
    db: Session, party: Party, statuses: Sequence[str] | None = None, limit: int | None = None
) -> list[Alert]:
    stmt = select(Alert).where(Alert.party_id == party.id)
    if statuses:
        stmt = stmt.where(Alert.status.in_(statuses))
    severity = case(SEVERITY_ORDER, value=Alert.severity, else_=9)
    stmt = stmt.order_by(severity, Alert.due_on.asc().nulls_last(), Alert.key)
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def list_alerts(
    db: Session, user: CurrentUser, party_id: uuid.UUID | None, status: str | None
) -> AlertList:
    buyer = require_buyer(db, user, party_id)
    rows = party_alerts(db, buyer, [status] if status else None)
    return AlertList(party_id=buyer.id, alerts=[alert_out(db, a) for a in rows])


def _own_alert(db: Session, user: CurrentUser, alert_id: uuid.UUID) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None:
        raise NotFound("alert not found")
    if not can_read_party(user, a.party_id):
        raise NotFound("alert not found")  # same answer as missing: ids are not an oracle
    return a


def set_status(
    db: Session, user: CurrentUser, alert_id: uuid.UUID, status: AlertStatus
) -> AlertOut:
    a = _own_alert(db, user, alert_id)
    if status == AlertStatus.ACKNOWLEDGED and a.status == AlertStatus.OPEN:
        a.status = AlertStatus.ACKNOWLEDGED
    elif status == AlertStatus.RESOLVED and a.status != AlertStatus.RESOLVED:
        if a.type not in ENGINE_TYPES and user.role != Role.ADMIN:
            raise Forbidden("KYB and fraud alerts close when the underlying check clears")
        a.status = AlertStatus.RESOLVED
        a.facts = {**(a.facts or {}), "resolved_by": "user"}
    db.commit()
    return alert_out(db, a)
