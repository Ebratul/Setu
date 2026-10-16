"""Pre-seeded alerts (English + Bangla) and the two pending approvals.

Alert numbers are derived from the cash-flow and FX seed modules (never typed in twice), so the
alert and the data it describes always agree.
"""

from datetime import timedelta
from decimal import Decimal

from app.db.enums import (
    Actor,
    AlertStatus,
    AlertType,
    ApprovalAction,
    ApprovalStatus,
    CostKind,
    Severity,
)
from app.db.models import Alert, ApprovalRequest
from app.domain.money import q2
from app.security.approvals import approval_binding_hash
from seed.cashflow import OPENING, balance_available, build_rows, main_m2
from seed.common import Ctx, Row, Rows, sid
from seed.deals import DEALS_BY_REF, MAIN_DEAL, deal_id, milestone_id
from seed.fx import good_cny_day
from seed.parties import HUAXIN, HUAXIN_CNY, HUAXIN_HK_PENDING, KARIM, RAHIMA

HUAMENG_DEAL = "SETU-2026-0005"
APPROVAL_T2 = f"approval:{MAIN_DEAL}:release-m1"
APPROVAL_T3 = f"approval:{HUAXIN}:beneficiary-change-hk"
COOLING_OFF_MINUTES = 10


def usd(amount: Decimal) -> str:
    return f"USD {q2(amount):,.2f}"


def shortfall_facts(ctx: Ctx) -> Row:
    m2_date, m2_amount = main_m2(ctx)
    rahima = [r for r in build_rows(ctx) if r["party_id"] == sid("party", RAHIMA)]
    balance = balance_available(rahima, OPENING[RAHIMA], ctx.today, m2_date)
    return {
        "date": m2_date,
        "balance": q2(balance),
        "due": q2(m2_amount),
        "shortfall": q2(max(Decimal("0"), m2_amount - balance)),
    }


def alert(
    key: str,
    party: str,
    type_: AlertType,
    severity: Severity,
    title: tuple[str, str],
    message: tuple[str, str],
    *,
    deal: str | None = None,
    milestone: int | None = None,
    amount: Decimal | None = None,
    due_on: object = None,
    facts: Row | None = None,
    created: object,
) -> Row:
    return {
        "id": sid("alert", key),
        "key": key,
        "party_id": sid("party", party),
        "deal_id": deal_id(deal) if deal else None,
        "milestone_id": milestone_id(deal, milestone) if deal and milestone else None,
        "type": type_,
        "severity": severity,
        "status": AlertStatus.OPEN,
        "title_en": title[0],
        "title_bn": title[1],
        "message_en": message[0],
        "message_bn": message[1],
        "amount": amount,
        "currency": "USD" if amount else None,
        "due_on": due_on,
        "facts": facts or {},
        "created_at": created,
    }


def alerts(ctx: Ctx) -> list[Row]:
    sf = shortfall_facts(ctx)
    main = DEALS_BY_REF[MAIN_DEAL]
    duty_amount, duty_due, _ = main.costs[CostKind.DUTY]
    arrival = ctx.day(main.milestones[2].due)
    boe_due = ctx.day(main.milestones[2].due + 1)
    fx = good_cny_day(ctx)
    pct = q2(-fx.change * 100)
    d = sf["date"].isoformat()
    return [
        alert(
            f"alert:{RAHIMA}:shortfall-m2",
            RAHIMA,
            AlertType.SHORTFALL,
            Severity.CRITICAL,
            (
                f"Cash shortfall of {usd(sf['shortfall'])} on {d}",
                f"{d} তারিখে {usd(sf['shortfall'])} নগদ ঘাটতি",
            ),
            (
                f"On {d} milestone 2 of {MAIN_DEAL} needs {usd(sf['due'])}, but your projected "
                f"balance is {usd(sf['balance'])}. Shortfall: {usd(sf['shortfall'])}.",
                f"{d} তারিখে {MAIN_DEAL}-এর মাইলস্টোন ২-এর জন্য {usd(sf['due'])} লাগবে, কিন্তু "
                f"আপনার আনুমানিক ব্যালেন্স {usd(sf['balance'])}। ঘাটতি: {usd(sf['shortfall'])}।",
            ),
            deal=MAIN_DEAL,
            milestone=2,
            amount=sf["shortfall"],
            due_on=sf["date"],
            facts={k: (str(v) if not isinstance(v, str) else v) for k, v in sf.items()},
            created=ctx.at(0, 8, 0),
        ),
        alert(
            f"alert:{RAHIMA}:deadline-duty",
            RAHIMA,
            AlertType.DEADLINE,
            Severity.WARNING,
            (
                f"Customs duty {usd(duty_amount)} due {ctx.day(duty_due).isoformat()}",
                f"শুল্ক {usd(duty_amount)} পরিশোধের শেষ তারিখ {ctx.day(duty_due).isoformat()}",
            ),
            (
                f"Import duty for {MAIN_DEAL} is due 5 days after arrival ({arrival.isoformat()}).",
                f"{MAIN_DEAL}-এর আমদানি শুল্ক পণ্য পৌঁছানোর ({arrival.isoformat()}) ৫ দিনের মধ্যে "
                f"পরিশোধ করতে হবে।",
            ),
            deal=MAIN_DEAL,
            amount=duty_amount,
            due_on=ctx.day(duty_due),
            facts={"arrival": arrival.isoformat(), "duty": str(duty_amount)},
            created=ctx.at(0, 8, 0),
        ),
        alert(
            f"alert:{RAHIMA}:deadline-bill-of-entry",
            RAHIMA,
            AlertType.DEADLINE,
            Severity.INFO,
            (
                f"File the bill of entry by {boe_due.isoformat()}",
                f"{boe_due.isoformat()}-এর মধ্যে বিল অব এন্ট্রি জমা দিন",
            ),
            (
                f"The bill of entry for {MAIN_DEAL} is the evidence for milestone 3 "
                f"({usd(main.milestone_amounts()[2].amount)}). Lodge it the day after arrival.",
                f"{MAIN_DEAL}-এর বিল অব এন্ট্রি মাইলস্টোন ৩ "
                f"({usd(main.milestone_amounts()[2].amount)})-এর প্রমাণপত্র। পণ্য পৌঁছানোর পরের দিন "
                f"জমা দিন।",
            ),
            deal=MAIN_DEAL,
            milestone=3,
            due_on=boe_due,
            created=ctx.at(0, 8, 0),
        ),
        alert(
            f"alert:{RAHIMA}:fx-good-cny-day",
            RAHIMA,
            AlertType.FX_OPPORTUNITY,
            Severity.INFO,
            (f"Good day to buy CNY: {fx.on.isoformat()}", f"CNY কেনার ভালো দিন: {fx.on.isoformat()}"),
            (
                f"Mock forecast: CNY/BDT {fx.rate} on {fx.on.isoformat()}, {pct}% below the 30-day "
                f"average of {q2(fx.mean_30d)}. Consider locking a rate for milestone 2.",
                f"মক পূর্বাভাস: {fx.on.isoformat()} তারিখে CNY/BDT {fx.rate}, যা ৩০ দিনের গড় "
                f"{q2(fx.mean_30d)}-এর চেয়ে {pct}% কম। মাইলস্টোন ২-এর জন্য রেট লক করার কথা ভাবুন।",
            ),
            deal=MAIN_DEAL,
            due_on=fx.on,
            facts={
                "pair": "CNY/BDT",
                "rate": str(fx.rate),
                "mean_30d": str(q2(fx.mean_30d)),
                "change_pct": str(-pct),
                "source": "MOCK",
            },
            created=ctx.at(0, 8, 5),
        ),
        alert(
            f"alert:{KARIM}:kyb-huameng",
            KARIM,
            AlertType.KYB_WARNING,
            Severity.WARNING,
            (
                "Supplier KYB warning: Guangzhou Huameng Trading",
                "সরবরাহকারী KYB সতর্কতা: Guangzhou Huameng Trading",
            ),
            (
                "The receiving account is a PERSONAL account held by 'Chen Wei', which does not "
                "match the licence name, and was first seen 3 days ago. Milestone 1 stays on hold.",
                "গ্রহীতা অ্যাকাউন্টটি 'Chen Wei'-এর ব্যক্তিগত অ্যাকাউন্ট, যা লাইসেন্সের নামের সাথে "
                "মেলে না, এবং মাত্র ৩ দিন আগে প্রথম দেখা গেছে। মাইলস্টোন ১ আটকে রাখা হয়েছে।",
            ),
            deal=HUAMENG_DEAL,
            milestone=1,
            facts={
                "kyb_status": "WARNING",
                "reasons": ["PERSONAL_ACCOUNT", "HOLDER_NAME_MISMATCH", "NEW_ACCOUNT"],
            },
            created=ctx.at(-3, 16, 0),
        ),
    ]


def approvals(ctx: Ctx) -> list[Row]:
    main = DEALS_BY_REF[MAIN_DEAL]
    m1 = main.milestone_amounts()[0]
    t2_params = {
        "deal_ref": MAIN_DEAL,
        "milestone_seq": 1,
        "amount": str(m1.amount),
        "currency": "USD",
        "beneficiary_account_id": str(sid("account", HUAXIN_CNY)),
        "pay_currency": "CNY",
    }
    t3_params = {
        "supplier_code": HUAXIN,
        "deal_ref": MAIN_DEAL,
        "from_account_id": str(sid("account", HUAXIN_CNY)),
        "to_account_id": str(sid("account", HUAXIN_HK_PENDING)),
        "requested_via": "email",
    }
    # Demo shortcut: timestamps are DEMO_TODAY-relative, so on the real demo day the 10-minute
    # cooling-off may already have elapsed; 5.1 restarts it when the OTP flow begins.
    t3_created = ctx.at(0, 9, 45)
    rows = [
        {
            "id": sid("approval", APPROVAL_T2),
            "key": APPROVAL_T2,
            "deal_id": deal_id(MAIN_DEAL),
            "milestone_id": milestone_id(MAIN_DEAL, 1),
            "bank_account_id": sid("account", HUAXIN_CNY),
            "action": ApprovalAction.RELEASE_MILESTONE,
            "tier": 2,
            "params": t2_params,
            "reasons": [
                {
                    "code": "FX_RATE_LOCK",
                    "message": f"Release converts {usd(m1.amount)} to CNY for Huaxin's verified "
                    "CNY "
                    "account; the USD/CNY rate must be locked (one-tap approval).",
                }
            ],
            "status": ApprovalStatus.PENDING,
            "requested_by": Actor.SYSTEM,
            "otp_required": False,
            "cooling_off_until": None,
            "created_at": ctx.at(0, 9, 30),
            "decided_at": None,
            "decided_by_user_id": None,
        },
        {
            "id": sid("approval", APPROVAL_T3),
            "key": APPROVAL_T3,
            "deal_id": deal_id(MAIN_DEAL),
            "milestone_id": None,
            "bank_account_id": sid("account", HUAXIN_HK_PENDING),
            "action": ApprovalAction.CHANGE_BENEFICIARY,
            "tier": 3,
            "params": t3_params,
            "reasons": [
                {
                    "code": "BENEFICIARY_CHANGE",
                    "message": "Supplier asked to switch the "
                    "receiving account from the verified CNY account to a new Hong Kong account.",
                },
                {
                    "code": "CHANGE_VIA_EMAIL",
                    "message": "Request arrived by email, outside the supplier portal.",
                },
                {
                    "code": "DOC_INSTRUCTION",
                    "message": "The instruction to change the account originates from email text.",
                },
                {
                    "code": "HOLDER_NAME_MISMATCH",
                    "message": "New holder 'Huaxin Textile (HK) "
                    "Trading Ltd' differs from the licence name.",
                },
                {"code": "NEW_ACCOUNT", "message": "Account first seen 1 day ago."},
            ],
            "status": ApprovalStatus.PENDING,
            "requested_by": Actor.SYSTEM,
            "otp_required": True,
            "cooling_off_until": t3_created + timedelta(minutes=COOLING_OFF_MINUTES),
            "created_at": t3_created,
            "decided_at": None,
            "decided_by_user_id": None,
        },
    ]
    for row in rows:
        row["params_hash"] = binding_hash(row)
    return rows


def binding_hash(row: Row) -> str:
    return approval_binding_hash(
        action=row["action"],
        tier=row["tier"],
        deal_id=row["deal_id"],
        milestone_id=row["milestone_id"],
        bank_account_id=row["bank_account_id"],
        params=row["params"],
    )


def build(ctx: Ctx) -> Rows:
    return [(ApprovalRequest, approvals(ctx)), (Alert, alerts(ctx))]
