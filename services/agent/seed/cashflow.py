"""Cash-flow items for both buyers: 30 days of actuals and 90 days of projections from DEMO_TODAY.

Projected balance rule (used by the shortfall alert and scripts/verify_seed):
    balance_available(D) = party.cash_balance (opening balance at the start of DEMO_TODAY)
                           + sum(IN) - sum(OUT) over projected items with DEMO_TODAY <= date < D
    shortfall(D) = max(0, payment_due(D) - balance_available(D))
For Rahima, one local-purchase outflow is tuned so balance_available(milestone-2 date) is exactly
USD 4,200.00 against the USD 5,760.00 milestone-2 payment, i.e. a USD 1,560.00 shortfall.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.db.enums import CashflowKind, DealStatus, FlowDirection, MilestoneStatus
from app.db.models import CashflowItem
from seed.common import Ctx, Row, Rows, rng, sid
from seed.deals import DEALS, DEALS_BY_REF, MAIN_DEAL, cost_id, deal_id, milestone_id
from seed.parties import KARIM, PARTIES, RAHIMA

HORIZON_DAYS = 90
HISTORY_DAYS = 30
TARGET_BALANCE = Decimal("4200.00")
TUNED_KEY = f"cf:{RAHIMA}:local-purchase:10"
ACTIVE = (DealStatus.FUNDED, DealStatus.IN_PRODUCTION, DealStatus.SHIPPED)
IN, OUT = FlowDirection.IN, FlowDirection.OUT


@dataclass(frozen=True, slots=True)
class Recurring:
    label: str
    kind: CashflowKind
    direction: FlowDirection
    description: str
    first: int
    every: int
    base: int
    jitter_steps: int = 0
    step: int = 5


PLANS: dict[str, tuple[Recurring, ...]] = {
    RAHIMA: (
        Recurring(
            "sales",
            CashflowKind.SALES,
            IN,
            "Weekly wholesale receipts (knitwear)",
            -26,
            7,
            1250,
            30,
        ),
        Recurring("salary", CashflowKind.SALARY, OUT, "Staff salaries (12 staff)", -18, 30, 2600),
        Recurring("rent", CashflowKind.RENT, OUT, "Factory floor rent, Narayanganj", -16, 30, 720),
        Recurring(
            "utilities", CashflowKind.UTILITIES, OUT, "Electricity, gas and water", -23, 30, 185, 5
        ),
        Recurring(
            "loan",
            CashflowKind.LOAN_REPAYMENT,
            OUT,
            "Term-loan instalment, Meghna Commercial Bank",
            -25,
            30,
            450,
        ),
        Recurring(
            "local-purchase",
            CashflowKind.LOCAL_PURCHASE,
            OUT,
            "Local yarn, dyeing and trims",
            40,
            30,
            1100,
            40,
        ),
    ),
    KARIM: (
        Recurring(
            "sales", CashflowKind.SALES, IN, "Weekly receipts from buying houses", -30, 7, 3400, 60
        ),
        Recurring("salary", CashflowKind.SALARY, OUT, "Staff salaries (31 staff)", -19, 30, 5800),
        Recurring("rent", CashflowKind.RENT, OUT, "Factory rent, Mirpur", -15, 30, 1500),
        Recurring(
            "utilities", CashflowKind.UTILITIES, OUT, "Electricity, gas and water", -22, 30, 420, 8
        ),
        Recurring(
            "loan", CashflowKind.LOAN_REPAYMENT, OUT, "Equipment-loan instalment", -10, 30, 1100
        ),
        Recurring(
            "local-purchase",
            CashflowKind.LOCAL_PURCHASE,
            OUT,
            "Local trims and packaging",
            25,
            30,
            1800,
            40,
        ),
    ),
}

OPENING = {p.code: p.cash_balance for p in PARTIES if p.cash_balance is not None}


def _row(
    ctx: Ctx,
    party: str,
    key: str,
    offset: int,
    kind: CashflowKind,
    direction: FlowDirection,
    amount: Decimal,
    description: str,
    **links: object,
) -> Row:
    return {
        "id": sid("cashflow", key),
        "key": key,
        "party_id": sid("party", party),
        "on_date": ctx.day(offset),
        "kind": kind,
        "direction": direction,
        "amount": amount,
        "currency": "USD",
        "description": description,
        "is_projected": offset >= 0,
        "deal_id": links.get("deal_id"),
        "milestone_id": links.get("milestone_id"),
        "deal_cost_id": links.get("deal_cost_id"),
    }


def _recurring(ctx: Ctx, party: str, plan: Recurring) -> list[Row]:
    r = rng(f"cashflow:{party}:{plan.label}")
    rows = []
    for offset in range(plan.first, HORIZON_DAYS + 1, plan.every):
        if offset < -HISTORY_DAYS:
            continue
        jitter = r.randint(-plan.jitter_steps, plan.jitter_steps) * plan.step
        amount = Decimal(plan.base + jitter).quantize(Decimal("0.01"))
        key = f"cf:{party}:{plan.label}:{offset}"
        rows.append(
            _row(ctx, party, key, offset, plan.kind, plan.direction, amount, plan.description)
        )
    return rows


def _deal_flows(ctx: Ctx, party: str) -> list[Row]:
    """Outflows the buyer still has to pay (pending tranches, deal costs) plus recent actuals."""
    rows = []
    for spec in DEALS:
        if spec.buyer != party or spec.status not in ACTIVE:
            continue
        links = {"deal_id": deal_id(spec.ref)}
        for seq, (plan, amount) in enumerate(
            zip(spec.milestones, spec.milestone_amounts(), strict=True), start=1
        ):
            if plan.funded is not None:
                when = plan.funded  # already deposited: an actual, if recent
                include = -HISTORY_DAYS <= when < 0
            else:
                when = plan.due  # still to deposit on the due date
                include = plan.status == MilestoneStatus.PENDING and when >= 0
            if include:
                rows.append(
                    _row(
                        ctx,
                        party,
                        f"cf:{party}:{spec.ref}:m{seq}",
                        when,
                        CashflowKind.MILESTONE_PAYMENT,
                        OUT,
                        amount.amount,
                        f"Fund escrow milestone {seq} · {spec.ref}",
                        **links,
                        milestone_id=milestone_id(spec.ref, seq),
                    )
                )
        for kind, (amount, due, note) in spec.costs.items():
            if due >= -HISTORY_DAYS:
                rows.append(
                    _row(
                        ctx,
                        party,
                        f"cf:{party}:{spec.ref}:{kind.lower()}",
                        due,
                        CashflowKind.DEAL_COST,
                        OUT,
                        amount,
                        f"{note} · {spec.ref}",
                        **links,
                        deal_cost_id=cost_id(spec.ref, kind),
                    )
                )
    return rows


def signed(row: Row) -> Decimal:
    return row["amount"] if row["direction"] == FlowDirection.IN else -row["amount"]


def balance_available(rows: list[Row], opening: Decimal, today: date, on: date) -> Decimal:
    return opening + sum(
        (signed(r) for r in rows if r["is_projected"] and today <= r["on_date"] < on),
        Decimal("0"),
    )


def main_m2(ctx: Ctx) -> tuple[date, Decimal]:
    spec = DEALS_BY_REF[MAIN_DEAL]
    return ctx.day(spec.milestones[1].due), spec.milestone_amounts()[1].amount


def build_rows(ctx: Ctx) -> list[Row]:
    rows: list[Row] = []
    for party, plans in PLANS.items():
        for plan in plans:
            rows += _recurring(ctx, party, plan)
        rows += _deal_flows(ctx, party)

    m2_date, _ = main_m2(ctx)
    rahima = [r for r in rows if r["party_id"] == sid("party", RAHIMA)]
    clash = [
        r["key"] for r in rahima if r["on_date"] == m2_date and r["kind"] != "MILESTONE_PAYMENT"
    ]
    if clash:
        raise AssertionError(f"items on the milestone-2 date would blur the shortfall: {clash}")
    net = balance_available(rahima, OPENING[RAHIMA], ctx.today, m2_date) - OPENING[RAHIMA]
    tuned = OPENING[RAHIMA] + net - TARGET_BALANCE
    if not Decimal("500") <= tuned <= Decimal("2500"):
        raise AssertionError(f"tuned local purchase out of realistic range: {tuned}")
    rows.append(
        _row(
            ctx,
            RAHIMA,
            TUNED_KEY,
            10,
            CashflowKind.LOCAL_PURCHASE,
            OUT,
            tuned,
            "Local yarn, dyeing and trims",
        )
    )
    return rows


def build(ctx: Ctx) -> Rows:
    return [(CashflowItem, build_rows(ctx))]
