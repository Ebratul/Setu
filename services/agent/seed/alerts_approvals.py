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
    Severity,
)
from app.db.models import Alert, ApprovalRequest
from app.domain.money import q2
from app.security.approvals import approval_binding_hash
from seed.cashflow import OPENING, balance_available, build_rows, main_m2
from seed.common import Ctx, Row, Rows, sid
from seed.deals import DEALS_BY_REF, MAIN_DEAL, deal_id, milestone_id
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
    """Seeded alerts the FR-2 engine does not own. SHORTFALL, DEADLINE and FX_OPPORTUNITY alerts
    are produced by app/services/alerts.py, which seed.cli runs after every seed."""
    return [
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
