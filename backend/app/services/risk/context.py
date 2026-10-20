"""Build a `RiskContext` from the database. The only place facts are gathered for the non-release
actions (the release path builds its richer `ReleaseContext` inside the escrow service). Nothing
here reads a request body, a model answer or a document's text."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import DealStatus, KybStatus
from app.db.models import BankAccount, Deal, Party
from app.domain.money import Money
from app.security.injection.events import deal_flagged
from app.security.policy import load_policy
from app.services import kyb as kyb_service
from app.services.analysis import fx_table
from app.services.risk.engine import Action, Origin, RiskContext
from app.services.scope import demo_today

# KYB checks about the receiving account: a WARNING caused by one of these is a Tier 3 trigger.
ACCOUNT_KYB_CHECKS = frozenset(
    {
        "LICENSE_VS_ACCOUNT_HOLDER",
        "ACCOUNT_TYPE",
        "ACCOUNT_AGE",
        "ACCOUNT_COUNTRY",
        "RECEIVING_ACCOUNT",
        "PENDING_BENEFICIARY_CHANGE",
    }
)


def prior_deal_count(db: Session, deal: Deal) -> int:
    """Earlier funded deals between this buyer and supplier (0 = first deal)."""
    live = (
        DealStatus.FUNDED,
        DealStatus.IN_PRODUCTION,
        DealStatus.SHIPPED,
        DealStatus.ARRIVED,
        DealStatus.COMPLETED,
    )
    return (
        db.scalar(
            select(func.count())
            .select_from(Deal)
            .where(
                Deal.buyer_id == deal.buyer_id,
                Deal.supplier_id == deal.supplier_id,
                Deal.id != deal.id,
                Deal.status.in_(live),
            )
        )
        or 0
    )


def deal_context(
    db: Session,
    deal: Deal,
    action: Action,
    origin: Origin,
    *,
    amount: Decimal,
    currency: str,
    beneficiary: BankAccount | None = None,
    now: datetime | None = None,
) -> RiskContext:
    """Facts about the deal's supplier and receiving account (or `beneficiary`, for a change)."""
    supplier = db.get(Party, deal.supplier_id)
    if supplier is None:
        raise ValueError("deal without supplier")
    today = demo_today(db)
    kyb = kyb_service.evaluate(db, supplier, deal=deal)
    failing = {c.code for c in kyb.checks if c.status != "PASS"}
    kyb_status = "BLOCKED" if supplier.kyb_status == KybStatus.FAILED else kyb.status
    acct = beneficiary or (
        db.get(BankAccount, deal.beneficiary_account_id) if deal.beneficiary_account_id else None
    )
    fx = fx_table(db, today)
    return RiskContext(
        action=action,
        origin=origin,
        amount=amount,
        currency=currency,
        amount_usd=fx.convert(Money(amount, currency), "USD").amount,  # type: ignore[arg-type]
        buyer_id=str(deal.buyer_id),
        supplier_id=str(deal.supplier_id),
        is_first_deal_with_supplier=prior_deal_count(db, deal) == 0,
        beneficiary_changed_recently=acct is not None
        and (today - acct.first_seen_on).days < load_policy().new_beneficiary_days,
        beneficiary_status=acct.status.value if acct else "ACTIVE",
        beneficiary_verified=acct.verified if acct else True,
        kyb_status=kyb_status,
        kyb_account_warning=bool(failing & ACCOUNT_KYB_CHECKS),
        sanctions_hit="SANCTIONS_SCREEN" in failing,
        instruction_from_document=deal_flagged(db, deal.id),  # P19 layer 3: never switchable
        deal_ref=deal.reference,
    )
