"""Supplier directory and profile for the KYB UI: reuses the FR-3 scorecard and the FR-4 result.
Read-only. Buyers see only suppliers they have deals with."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import AccountStatus, KybStatus, PartyKind
from app.db.models import BankAccount, Deal, KybCheck, Party
from app.schemas.analysis import SupplierScoreOut
from app.schemas.kyb import (
    SupplierCompany,
    SupplierDealItem,
    SupplierList,
    SupplierListItem,
    SupplierProfile,
)
from app.services import analysis, kyb
from app.services.analysis import fmt
from app.services.scope import demo_today, scope_party

BADGE = {
    KybStatus.VERIFIED: "VERIFIED",
    KybStatus.WARNING: "WARNING",
    KybStatus.FAILED: "BLOCKED",
    KybStatus.PENDING: "PENDING",
}


def _latest_check(db: Session, supplier: Party) -> KybCheck | None:
    """Newest KYB result for the supplier's active receiving account."""
    return db.scalars(
        select(KybCheck)
        .join(BankAccount, BankAccount.id == KybCheck.bank_account_id)
        .where(KybCheck.party_id == supplier.id, BankAccount.status == AccountStatus.ACTIVE)
        .order_by(KybCheck.checked_at.desc())
    ).first()


def list_suppliers(db: Session, user: CurrentUser, buyer_id: uuid.UUID | None) -> SupplierList:
    buyer = scope_party(db, user, buyer_id)
    cards: dict[uuid.UUID, SupplierScoreOut] = {
        s.supplier_id: s
        for s in analysis.suppliers(db, user, buyer.id if buyer else None).suppliers
    }
    stmt = select(Party).where(Party.kind == PartyKind.SUPPLIER).order_by(Party.legal_name)
    if buyer is not None:
        stmt = stmt.where(Party.id.in_(select(Deal.supplier_id).where(Deal.buyer_id == buyer.id)))
    items = []
    for sup in db.scalars(stmt).all():
        card = cards.get(sup.id)
        check = _latest_check(db, sup)
        pending = db.scalar(
            select(BankAccount.id)
            .where(
                BankAccount.party_id == sup.id, BankAccount.status == AccountStatus.PENDING_CHANGE
            )
            .limit(1)
        )
        items.append(
            SupplierListItem(
                supplier_id=sup.id,
                code=sup.code,
                name=sup.legal_name,
                city=sup.city,
                country=sup.country,
                kyb_status=sup.kyb_status.value,
                kyb_badge=BADGE[sup.kyb_status],  # type: ignore[arg-type]
                kyb_score=int(check.score * 100) if check else None,
                has_pending_change=pending is not None,
                last_checked=check.checked_at if check else None,
                completed_deals=card.completed_deals_count if card else 0,
                your_deals_count=card.your_deals_count if card else 0,
                on_time_rate_pct=card.on_time_rate_pct if card else None,
                scorecard_score=card.score if card else None,
                weak=card.weak if card else False,
            )
        )
    return SupplierList(buyer_id=buyer.id if buyer else None, suppliers=items)


def profile(
    db: Session, user: CurrentUser, supplier_id: uuid.UUID, buyer_id: uuid.UUID | None
) -> SupplierProfile:
    supplier = kyb.find_supplier(db, user, supplier_id)
    buyer = scope_party(db, user, buyer_id)
    today = demo_today(db)
    card = next(
        (
            s
            for s in analysis.suppliers(db, user, buyer.id if buyer else None).suppliers
            if s.supplier_id == supplier.id
        ),
        None,
    )
    deal_stmt = select(Deal).where(Deal.supplier_id == supplier.id).order_by(Deal.opened_on.desc())
    if buyer is not None:
        deal_stmt = deal_stmt.where(Deal.buyer_id == buyer.id)
    accounts = db.scalars(
        select(BankAccount)
        .where(BankAccount.party_id == supplier.id)
        .order_by(BankAccount.first_seen_on.desc(), BankAccount.id)
    ).all()
    result, source = kyb.latest_result(db, user, supplier)
    check = _latest_check(db, supplier)
    return SupplierProfile(
        supplier_id=supplier.id,
        code=supplier.code,
        company=SupplierCompany(
            legal_name=supplier.legal_name,
            license_name=supplier.license_name,
            license_no=supplier.license_no,
            city=supplier.city,
            country=supplier.country,
            first_seen_on=supplier.first_seen_on,
        ),
        kyb_status=supplier.kyb_status.value,
        kyb=result,
        kyb_source=source,  # type: ignore[arg-type]
        last_checked=result.checked_at
        if source == "stored"
        else (check.checked_at if check else None),
        accounts=[
            kyb.account_summary(a, today) for a in accounts if a.status != AccountStatus.RETIRED
        ],
        deals=[
            SupplierDealItem(
                deal_id=d.id,
                reference=d.reference,
                title=d.title,
                status=d.status.value,
                currency=d.currency,
                goods_value=fmt(d.goods_value),
                opened_on=d.opened_on,
                on_time=d.on_time,
                dispute_count=d.dispute_count,
            )
            for d in db.scalars(deal_stmt).all()
        ],
        score=card.score if card else None,
        score_trend=card.score_trend if card else [],
        on_time_rate_pct=card.on_time_rate_pct if card else None,
        dispute_rate_pct=card.dispute_rate_pct if card else None,
        completed_deals=card.completed_deals_count if card else 0,
        history=kyb.history_items(db, user, supplier),
    )
