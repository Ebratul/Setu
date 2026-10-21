"""FR-2 alert engine: evaluates the pure rules in app/domain/alerts.py on a buyer's forecast and
upserts the results by stable key.

- New key → insert OPEN. Existing key → update content only when it changed (re-runs are no-ops).
- An OPEN/ACKNOWLEDGED engine alert whose key is no longer produced → RESOLVED
  (`resolved_by=engine`). If its condition comes back it reopens; a user-resolved one stays closed.
Only SHORTFALL, DEADLINE and FX_OPPORTUNITY are recomputed here; FRAUD/INFO alerts are untouched.
KYB_WARNING alerts are owned by `sync_kyb_alerts` (called by the KYB service and the seed) with the
same lifecycle: one alert per (buyer, supplier) with open deals, key `alert:<buyer>:kyb-<supplier>`,
resolved by the engine when the supplier is VERIFIED or the buyer has no open deal left, reopened
when the problem returns (or got worse after a user resolved it).
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, can_read_party
from app.db.enums import AlertStatus, AlertType, DealStatus, Role, Severity
from app.db.models import Alert, Deal, Milestone, Party
from app.domain.alerts import (
    ENGINE_TYPES,
    AlertDraft,
    deadline_alerts,
    fx_alerts,
    shortfall_alerts,
)
from app.domain.cashflow import Flow, Forecast
from app.domain.kyb import CODE_LABELS
from app.domain.money import ZERO, Money
from app.domain.narrative import bn
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
    "REVIEW_SUPPLIER": ("Review the supplier", "সরবরাহকারীকে দেখুন"),
    "REVIEW_DOCUMENT": ("Review the document", "ডকুমেন্টটি দেখুন"),
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


# ---------- KYB alerts (FR-4) ----------

OPEN_DEAL_STATUSES = (
    DealStatus.DRAFT,
    DealStatus.PROPOSED,
    DealStatus.CONFIRMED,
    DealStatus.FUNDED,
    DealStatus.IN_PRODUCTION,
    DealStatus.SHIPPED,
    DealStatus.ARRIVED,
)
KYB_SEVERITY = {"WARNING": Severity.WARNING, "BLOCKED": Severity.CRITICAL}


def kyb_alert_key(buyer: Party, supplier: Party, deal: Deal | None = None) -> str:
    """alert:<buyer code>:kyb:<supplier code>[:<deal reference>]; hashed when it is too long."""
    raw = f"alert:{buyer.code}:kyb:{supplier.code}" + (f":{deal.reference}" if deal else "")
    return raw if len(raw) <= 80 else f"alert:kyb:{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex}"


def _kyb_row(
    db: Session, buyer: Party, supplier: Party, deal: Deal | None
) -> tuple[str, Alert | None]:
    """(key to use, existing row). A row on the readable key that is not this supplier's KYB alert
    (key collision) pushes us to a hashed key; the pre-P12 seed alert is adopted by re-keying."""
    key = kyb_alert_key(buyer, supplier, deal)
    ref = deal.reference if deal else None

    def mine(row: Alert) -> bool:
        f = row.facts or {}
        return (
            row.type == AlertType.KYB_WARNING
            and row.party_id == buyer.id
            and f.get("supplier_id") == str(supplier.id)
            and f.get("deal_ref") == ref
        )

    row = db.scalar(select(Alert).where(Alert.key == key))
    if row is None and deal is None:
        legacy = db.scalar(
            select(Alert).where(
                Alert.key == f"alert:{buyer.code}:kyb-{supplier.code.rsplit('-', 1)[-1]}",
                Alert.type == AlertType.KYB_WARNING,
                Alert.party_id == buyer.id,
            )
        )
        if legacy is not None and (legacy.facts or {}).get("supplier_id") in (
            None,
            str(supplier.id),
        ):
            legacy.key = key
            return key, legacy
    if row is None or mine(row):
        return key, row
    hashed = f"alert:kyb:{uuid.uuid5(uuid.NAMESPACE_URL, f'{buyer.id}:{supplier.id}:{ref}').hex}"
    return hashed, db.scalar(select(Alert).where(Alert.key == hashed))


def _kyb_text(
    supplier: Party, status: str, score: int | None, codes: Sequence[str]
) -> tuple[str, str]:
    """Alert text from codes and the supplier's own legal name only; no document text."""
    en = "; ".join(CODE_LABELS.get(c, (c, c))[0] for c in codes)
    bn_ = "; ".join(CODE_LABELS.get(c, (c, c))[1] for c in codes)
    tail = f" (score {score}/100)" if score is not None else ""
    word = "blocked" if status == "BLOCKED" else "warning"
    return (
        f"{supplier.legal_name}: KYB {word}{tail}. {en}. Review the supplier before any payment.",
        bn(
            f"{supplier.legal_name}: KYB "
            f"{'অবরুদ্ধ' if status == 'BLOCKED' else 'সতর্কতা'}"
            f"{f' (স্কোর {score}/100)' if score is not None else ''}। {bn_}। "
            "কোনো অর্থ প্রদানের আগে সরবরাহকারীকে পর্যালোচনা করুন।"
        ),
    )


def _kyb_resolve(row: Alert | None, counts: dict[str, int]) -> None:
    if row is not None and row.status != AlertStatus.RESOLVED:
        row.status = AlertStatus.RESOLVED
        row.facts = {**(row.facts or {}), "resolved_by": "engine"}
        counts["resolved"] += 1


def _kyb_upsert(
    db: Session, key: str, row: Alert | None, values: dict[str, Any], counts: dict[str, int]
) -> None:
    if row is None:
        db.add(
            Alert(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:{key}"),
                key=key,
                status=AlertStatus.OPEN,
                **values,
            )
        )
        counts["created"] += 1
        return
    worse = SEVERITY_ORDER[values["severity"].value] < SEVERITY_ORDER.get(row.severity.value, 9)
    engine_closed = (row.facts or {}).get("resolved_by") == "engine"
    reopen = (row.status == AlertStatus.RESOLVED and (engine_closed or worse)) or (
        row.status == AlertStatus.ACKNOWLEDGED and worse
    )
    if reopen:
        row.status = AlertStatus.OPEN
        counts["reopened"] += 1
    else:
        values["facts"] = {**values["facts"], **_keep(row.facts or {})}
    changed = {k: v for k, v in values.items() if getattr(row, k) != v}
    if changed:
        for k, v in changed.items():
            setattr(row, k, v)
        counts["updated"] += 1


def _kyb_values(
    buyer: Party,
    supplier: Party,
    deal: Deal,
    *,
    status: str,
    score: int | None,
    codes: Sequence[str],
    deal_level: bool,
) -> dict[str, Any]:
    en, bn_ = _kyb_text(supplier, status, score, codes)
    label = "blocked" if status == "BLOCKED" else "warning"
    prefix = "Invoice check" if deal_level else "Supplier KYB"
    return {
        "party_id": buyer.id,
        "deal_id": deal.id,
        "milestone_id": None,
        "type": AlertType.KYB_WARNING,
        "severity": KYB_SEVERITY[status],
        "title_en": f"{prefix} {label}: {supplier.legal_name}"[:200],
        "title_bn": f"{'ইনভয়েস যাচাই' if deal_level else 'সরবরাহকারী KYB'} "
        f"{'অবরুদ্ধ' if status == 'BLOCKED' else 'সতর্কতা'}: {supplier.legal_name}"[:200],
        "message_en": en,
        "message_bn": bn_,
        "amount": None,
        "currency": None,
        "due_on": None,
        "facts": {
            "kyb_status": status,
            "score": score,
            "reasons": list(codes),
            "supplier_id": str(supplier.id),
            "deal_ref": deal.reference if deal_level else None,
            "action": {
                "code": "REVIEW_SUPPLIER",
                "route": f"/app/suppliers/{supplier.id}",
                "query": {},
            },
            "engine": "kyb-v2",
        },
    }


def sync_kyb_alerts(
    db: Session,
    supplier: Party,
    *,
    base_status: str,
    base_score: int,
    base_reasons: Sequence[str],
    deal: Deal | None = None,
    deal_codes: Sequence[str] = (),
    scope: set[uuid.UUID] | None = None,
) -> dict[str, int]:
    """Two kinds of KYB_WARNING alert, both idempotent:

    - supplier-level, per buyer with open deals, from party/account facts only (`base_*`);
    - deal-level, only for `deal` (a run with a deal), from the invoice-specific `deal_codes`.
    Alerts are created / updated for every buyer, but only buyers in `scope` (None = all) have
    supplier-level alerts resolved, and a run without a deal never touches a deal-level alert.
    Flushes; the caller commits."""
    counts = {"created": 0, "updated": 0, "reopened": 0, "resolved": 0}
    deals = db.scalars(
        select(Deal)
        .where(Deal.supplier_id == supplier.id)
        .order_by(Deal.opened_on.desc(), Deal.reference)
    ).all()
    for buyer_id in sorted({d.buyer_id for d in deals}, key=str):
        buyer = db.get(Party, buyer_id)
        if buyer is None:
            continue
        key, row = _kyb_row(db, buyer, supplier, None)
        open_deal = next(
            (d for d in deals if d.buyer_id == buyer_id and d.status in OPEN_DEAL_STATUSES), None
        )
        if base_status in KYB_SEVERITY and open_deal is not None:
            values = _kyb_values(
                buyer, supplier, open_deal, status=base_status, score=base_score,
                codes=base_reasons, deal_level=False,
            )  # fmt: skip
            _kyb_upsert(db, key, row, values, counts)
        elif scope is None or buyer_id in scope:
            _kyb_resolve(row, counts)
    if deal is not None:
        buyer = db.get(Party, deal.buyer_id)
        if buyer is not None:
            key, row = _kyb_row(db, buyer, supplier, deal)
            if deal_codes and deal.status in OPEN_DEAL_STATUSES:
                values = _kyb_values(
                    buyer, supplier, deal, status="WARNING", score=None,
                    codes=deal_codes, deal_level=True,
                )  # fmt: skip
                _kyb_upsert(db, key, row, values, counts)
            else:
                _kyb_resolve(row, counts)
    db.flush()
    return counts


DOC_TYPE_LABELS: dict[str, tuple[str, str]] = {
    "PROFORMA_INVOICE": ("Proforma invoice", "প্রফর্মা ইনভয়েস"),
    "COMMERCIAL_INVOICE": ("Commercial invoice", "কমার্শিয়াল ইনভয়েস"),
    "PACKING_LIST": ("Packing list", "প্যাকিং লিস্ট"),
    "BILL_OF_LADING": ("Bill of lading", "বিল অব লেডিং"),
    "CERTIFICATE_OF_ORIGIN": ("Certificate of origin", "সার্টিফিকেট অব অরিজিন"),
    "BILL_OF_ENTRY": ("Bill of entry", "বিল অব এন্ট্রি"),
    "PRODUCTION_PHOTO": ("Production photo", "উৎপাদনের ছবি"),
    "OTHER": ("Document", "ডকুমেন্ট"),
}


def document_alert_key(document_id: uuid.UUID) -> str:
    return f"alert:fraud:doc:{document_id}"


def sync_document_alert(
    db: Session,
    deal: Deal,
    *,
    document_id: uuid.UUID,
    doc_type: str,
    failed: bool,
    score: int | None,
    reason_codes: Sequence[str],
    labels: dict[str, tuple[str, str]],
    instruction: bool,
    milestone_id: uuid.UUID | None = None,
    allow_resolve: bool = False,
) -> str | None:
    """FRAUD alert for a document that failed forensics (one per document, idempotent; resolved
    when a re-check no longer fails). The text is built from codes and fixed labels only, never
    from document text. Returns "created" | "updated" | "resolved" | None. The caller commits."""
    key = document_alert_key(document_id)
    row = db.scalar(select(Alert).where(Alert.key == key))
    if not failed:
        # never auto-resolved: a re-check by an admin (allow_resolve) clears it
        if allow_resolve and row is not None and row.status != AlertStatus.RESOLVED:
            row.status = AlertStatus.RESOLVED
            row.facts = {**(row.facts or {}), "resolved_by": "engine"}
            return "resolved"
        return None
    name_en, name_bn = DOC_TYPE_LABELS.get(doc_type, DOC_TYPE_LABELS["OTHER"])
    why_en = "; ".join(labels[c][0] for c in reason_codes[:3] if c in labels)
    why_bn = "; ".join(labels[c][1] for c in reason_codes[:3] if c in labels)
    tail_score = f" (score {score}/100)" if score is not None else ""
    values: dict[str, Any] = {
        "party_id": deal.buyer_id,
        "deal_id": deal.id,
        "milestone_id": milestone_id,
        "type": AlertType.FRAUD,
        "severity": Severity.CRITICAL,
        "title_en": f"{name_en} failed document checks: {deal.reference}"[:200],
        "title_bn": f"{name_bn} যাচাইয়ে ব্যর্থ: {deal.reference}"[:200],
        "message_en": f"{name_en} for {deal.reference} failed forensic checks{tail_score}. "
        f"{why_en}. Hold any payment until it has been reviewed."
        + (" It contains a hidden instruction that Setu ignored." if instruction else ""),
        "message_bn": bn(
            f"{deal.reference}-এর {name_bn} ডকুমেন্ট যাচাইয়ে ব্যর্থ"
            f"{f' (স্কোর {score}/100)' if score is not None else ''}। {why_bn}। "
            "এই ডকুমেন্টের ভিত্তিতে অর্থ ছাড় করা যাবে না।"
            + (" এতে একটি লুকানো নির্দেশ ছিল যা Setu উপেক্ষা করেছে।" if instruction else "")
        ),
        "amount": None,
        "currency": None,
        "due_on": None,
        "facts": {
            "document_id": str(document_id),
            "doc_type": doc_type,
            "deal_ref": deal.reference,
            "score": score,
            "reasons": list(reason_codes),
            "instruction_from_document": instruction,
            "action": {
                "code": "REVIEW_DOCUMENT",
                "route": f"/app/documents/{document_id}",
                "query": {},
            },
            "engine": "forensics-v1",
        },
    }
    if row is None:
        db.add(
            Alert(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:{key}"),
                key=key,
                status=AlertStatus.OPEN,
                **values,
            )
        )
        db.flush()
        return "created"
    if row.status == AlertStatus.RESOLVED:
        row.status = AlertStatus.OPEN
    for k, v in values.items():
        if getattr(row, k) != v:
            setattr(row, k, v)
    db.flush()
    return "updated"


PURPOSE_LABELS = {
    "FINANCING_COLLATERAL": ("financing collateral", "ঋণের জামানত"),
    "ESCROW_EVIDENCE": ("escrow evidence", "এসক্রো প্রমাণ"),
}


def registry_alert_key(deal_id: uuid.UUID, scope: str) -> str:
    return f"alert:fraud:registry:{deal_id}:{scope}"[:80]


def raise_registry_alert(
    db: Session,
    deal: Deal,
    *,
    scope: str,
    result: str,
    purpose: str,
    holder: str | None,
    registered_on: date,
    doc_type: str,
) -> str:
    """FRAUD alert for an attempt to finance an invoice the hash registry already holds elsewhere
    (one per deal and target, idempotent, reopened by a repeat). Codes and labels only, no
    document text. Returns "created" | "updated". The caller commits."""
    key = registry_alert_key(deal.id, scope)
    row = db.scalar(select(Alert).where(Alert.key == key))
    doc_en, doc_bn = DOC_TYPE_LABELS.get(doc_type, DOC_TYPE_LABELS["OTHER"])
    use_en, use_bn = PURPOSE_LABELS.get(purpose, PURPOSE_LABELS["ESCROW_EVIDENCE"])
    who_en = f" with {holder}" if holder else ""
    who_bn = f" ({holder})" if holder else ""
    kind_en = "copy" if result == "NEAR_DUPLICATE" else "exact copy"
    values: dict[str, Any] = {
        "party_id": deal.buyer_id,
        "deal_id": deal.id,
        "milestone_id": None,
        "type": AlertType.FRAUD,
        "severity": Severity.CRITICAL,
        "title_en": f"Duplicate financing blocked: {deal.reference}"[:200],
        "title_bn": f"দ্বৈত অর্থায়ন আটকানো হয়েছে: {deal.reference}"[:200],
        "message_en": f"The {doc_en} of {deal.reference} is a {kind_en} of a document already "
        f"registered as {use_en}{who_en} on {registered_on.isoformat()}. It cannot back a second "
        "financing. Review before any further action.",
        "message_bn": bn(
            f"{deal.reference}-এর {doc_bn} ইতিমধ্যে {registered_on.isoformat()} তারিখে "
            f"{use_bn}{who_bn} হিসেবে নিবন্ধিত নথির প্রতিলিপি। এটি দ্বিতীয় অর্থায়নের "
            "জামানত হতে পারে না। পরবর্তী পদক্ষেপের আগে পর্যালোচনা করুন।"
        ),
        "amount": None,
        "currency": None,
        "due_on": None,
        "facts": {
            "deal_ref": deal.reference,
            "result": result,
            "purpose": purpose,
            "registered_on": registered_on.isoformat(),
            "action": {"code": "REVIEW_DEAL", "route": f"/app/deals/{deal.id}", "query": {}},
            "engine": "registry-v1",
        },
    }
    if row is None:
        db.add(
            Alert(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:{key}"),
                key=key,
                status=AlertStatus.OPEN,
                **values,
            )
        )
        db.flush()
        return "created"
    if row.status == AlertStatus.RESOLVED:
        row.status = AlertStatus.OPEN
    for k, v in values.items():
        if getattr(row, k) != v:
            setattr(row, k, v)
    db.flush()
    return "updated"


def injection_alert_key(deal_id: uuid.UUID, source: str) -> str:
    return f"alert:fraud:injection:{deal_id}:{source}"[:80]


def raise_injection_alert(db: Session, deal: Deal, *, source: str, rules: Sequence[str]) -> str:
    """FRAUD alert: instruction-like text reached Setu from untrusted content linked to the deal.
    One per deal and placement (idempotent, reopened by a repeat); rule codes only, no text.
    Returns "created" | "updated". The caller commits."""
    key = injection_alert_key(deal.id, source)
    row = db.scalar(select(Alert).where(Alert.key == key))
    where_en = {
        "hidden_text": "hidden text in a document",
        "metadata": "a document's metadata",
        "email": "a pasted e-mail",
        "kb": "a knowledge-base passage",
    }.get(source, "untrusted content")
    where_bn = {
        "hidden_text": "নথির লুকানো লেখা",
        "metadata": "নথির মেটাডেটা",
        "email": "পেস্ট করা ইমেইল",
        "kb": "জ্ঞানভান্ডারের একটি অংশ",
    }.get(source, "অবিশ্বস্ত বিষয়বস্তু")
    values: dict[str, Any] = {
        "party_id": deal.buyer_id,
        "deal_id": deal.id,
        "milestone_id": None,
        "type": AlertType.FRAUD,
        "severity": Severity.CRITICAL,
        "title_en": f"Hidden instruction ignored: {deal.reference}"[:200],
        "title_bn": f"লুকানো নির্দেশ উপেক্ষা করা হয়েছে: {deal.reference}"[:200],
        "message_en": f"Setu found an instruction in {where_en} linked to {deal.reference} and "
        "ignored it. The deal's next money action needs extra verification (Tier 3).",
        "message_bn": bn(
            f"{deal.reference}-এর সাথে যুক্ত {where_bn}-এ Setu একটি নির্দেশ পেয়েছে এবং তা উপেক্ষা "
            "করেছে। ডিলের পরবর্তী অর্থ-সংক্রান্ত কাজে অতিরিক্ত যাচাই (টিয়ার ৩) লাগবে।"
        ),
        "amount": None,
        "currency": None,
        "due_on": None,
        "facts": {
            "deal_ref": deal.reference,
            "source": source,
            "rules": list(rules)[:8],
            "action": {"code": "REVIEW_DEAL", "route": f"/app/deals/{deal.id}", "query": {}},
            "engine": "injection-v1",
        },
    }
    if row is None:
        db.add(
            Alert(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:{key}"),
                key=key,
                status=AlertStatus.OPEN,
                **values,
            )
        )
        db.flush()
        return "created"
    if row.status == AlertStatus.RESOLVED:
        row.status = AlertStatus.OPEN
    for k, v in values.items():
        if getattr(row, k) != v:
            setattr(row, k, v)
    db.flush()
    return "updated"
