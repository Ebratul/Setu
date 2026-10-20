"""Pre-seeded alerts (English + Bangla) and the two pending approvals.

Alert numbers are derived from the cash-flow and FX seed modules (never typed in twice), so the
alert and the data it describes always agree.
"""

from datetime import timedelta
from decimal import Decimal

from app.db.enums import (
    Actor,
    ApprovalAction,
    ApprovalStatus,
)
from app.db.models import Alert, ApprovalRequest
from app.domain.money import q2
from app.security.approvals import approval_binding_hash
from seed.cashflow import OPENING, balance_available, build_rows, main_m2
from seed.common import Ctx, Row, Rows, sid
from seed.deals import DEALS_BY_REF, MAIN_DEAL, deal_id, milestone_id
from seed.parties import HUAXIN, HUAXIN_CNY, HUAXIN_HK_PENDING, RAHIMA

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


def alerts(ctx: Ctx) -> list[Row]:
    """No seeded alerts: every alert is owned by an engine. SHORTFALL, DEADLINE and FX_OPPORTUNITY
    come from app/services/alerts.py, and the KYB_WARNING for Karim / Huameng comes from the KYB
    alert sync (app/services/kyb.py `sync_all_alerts`); seed.cli runs both after every seed."""
    return []


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
    if ctx.profile == "demo":
        rows = [r for r in rows if r["action"] != ApprovalAction.CHANGE_BENEFICIARY]
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
