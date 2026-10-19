"""Judge-mode scam simulator: runs a scam through the REAL code path and returns the explanation.
Redirection e-mail -> the e-mail check; supplier account change -> the supplier-portal request
and its Tier 3 approval; large advance -> the real risk engine on a USD 22,000 release (dry run,
nothing is saved). Demo only (DEMO_MODE on, never in prod)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, to_current
from app.config import get_settings
from app.db.enums import Role
from app.db.models import Deal, User
from app.errors import Forbidden, NotFound
from app.schemas.approvals import AccountChangeIn, SimScenario, SimulateOut
from app.services import inbox, supplier_accounts
from app.services.risk import engine
from app.services.risk.engine import Action, RiskContext

MAIN_DEAL = "SETU-2026-0001"
SIM_ACCOUNT = {
    "bank_name": "Pacific Bridge Bank (HK)",
    "bank_country": "HK",
    "account_number": "HK-099-551200-007",
    "holder_name": "Huaxin Textile (HK) Trading Ltd",
    "account_type": "CORPORATE",
    "currency": "USD",
}


def _user_of(db: Session, party_id: object, role: Role) -> CurrentUser:
    row = db.scalars(select(User).where(User.party_id == party_id, User.role == role)).first()
    if row is None:
        raise NotFound("demo user not found")
    return to_current(row)


def run(db: Session, user: CurrentUser, scenario: SimScenario) -> SimulateOut:
    settings = get_settings()
    if not settings.demo_mode or settings.app_env == "prod":
        raise NotFound("not found")
    if user.role not in (Role.JUDGE, Role.ADMIN, Role.BUYER):
        raise Forbidden("the scam simulator is for judges, admins and buyers")
    deal = db.scalars(select(Deal).where(Deal.reference == MAIN_DEAL)).first()
    if deal is None:
        raise NotFound("demo deal not found")
    if user.role == Role.BUYER and user.party_id != deal.buyer_id:
        raise Forbidden("the simulator runs on the demo buyer's deal")

    if scenario == "redirect-email":
        buyer = _user_of(db, deal.buyer_id, Role.BUYER)
        out = inbox.check_email(db, buyer, inbox.demo_email_text(), MAIN_DEAL)
        return SimulateOut(
            scenario=scenario,
            title_en="Payment-redirection email",
            title_bn="পেমেন্ট-পরিবর্তনের ইমেইল",
            what_we_did_en="Pasted a fake email from the supplier asking you to pay the balance "
            "into a new Hong Kong account.",
            what_we_did_bn="সরবরাহকারীর নামে একটি ভুয়া ইমেইল দেওয়া হলো, যাতে বাকি টাকা নতুন হংকং "
            "অ্যাকাউন্টে পাঠাতে বলা হয়েছে।",
            how_setu_responded_en="Blocked. No account was changed, a FRAUD alert and a signed "
            "audit row were created, and you are told to verify by video call.",
            how_setu_responded_bn="আটকানো হয়েছে। কোনো অ্যাকাউন্ট বদলায়নি; প্রতারণা সতর্কবার্তা ও "
            "স্বাক্ষরিত অডিট এন্ট্রি তৈরি হয়েছে; ভিডিও কলে যাচাই করতে বলা হয়েছে।",
            outcome=out.verdict,
            tier=3,
            reasons=[s.code for s in out.signals],
            approval_id=out.related_approval_id,
            email=out,
        )

    if scenario == "supplier-account-change":
        supplier = _user_of(db, deal.supplier_id, Role.SUPPLIER)
        res = supplier_accounts.request_change(
            db,
            supplier,
            AccountChangeIn(deal_id=deal.id, **SIM_ACCOUNT),  # type: ignore[arg-type]
        )
        appr = supplier_accounts._approval_for(
            db, db.get(supplier_accounts.BankAccount, res.account_id)
        )  # type: ignore[arg-type]
        return SimulateOut(
            scenario=scenario,
            title_en="Supplier account change",
            title_bn="সরবরাহকারীর অ্যাকাউন্ট পরিবর্তন",
            what_we_did_en="The supplier asked, inside its portal, to be paid into a new account.",
            what_we_did_bn="সরবরাহকারী নিজের পোর্টালে নতুন অ্যাকাউন্টে পেমেন্টের অনুরোধ করেছে।",
            how_setu_responded_en="The account is parked as PENDING, KYB was re-run, and a Tier 3 "
            "request now waits for the buyer: a code plus a cooling-off pause. Nothing was paid.",
            how_setu_responded_bn="অ্যাকাউন্টটি অপেক্ষমাণ রাখা হয়েছে, KYB আবার চলেছে, এবং ক্রেতার জন্য "
            "টিয়ার ৩ অনুরোধ অপেক্ষা করছে: কোড ও বিরতি লাগবে। কোনো টাকা যায়নি।",
            outcome=res.stage,
            tier=res.tier,
            reasons=[str(r.get("code")) for r in (appr.reasons if appr else [])],
            approval_id=appr.id if appr else None,
        )

    ctx = RiskContext(
        action=Action.RELEASE_TRANCHE,
        amount=Decimal("22000"),
        amount_usd=Decimal("22000"),
        deal_ref=MAIN_DEAL,
    )
    d = engine.evaluate(ctx)
    return SimulateOut(
        scenario=scenario,
        title_en="Large advance (USD 22,000)",
        title_bn="বড় অগ্রিম (USD 22,000)",
        what_we_did_en="Asked the real risk engine about releasing USD 22,000 in one go "
        "(a what-if: nothing is saved).",
        what_we_did_bn="একবারে USD 22,000 ছাড়ের বিষয়ে আসল ঝুঁকি ইঞ্জিনকে জিজ্ঞাসা করা হলো (পরীক্ষামূলক; "
        "কিছু সংরক্ষিত হয়নি)।",
        how_setu_responded_en=d.explanation_en,
        how_setu_responded_bn=d.explanation_bn,
        outcome=d.decision.value,
        tier=d.tier,
        reasons=d.reason_codes,
        approval_id=None,
    )
