"""Deals, landed-cost lines, 30/60/10 milestones, simulated escrow and its double-entry ledger.

Escrow is funded tranche by tranche: the buyer deposits each milestone amount on/before its due
date, and a tranche is released to the supplier once its evidence checks pass.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.db.enums import (
    ConfirmRole,
    CostKind,
    DealStatus,
    DocType,
    EscrowStatus,
    EvidenceStatus,
    LedgerDirection,
    LedgerKind,
    MilestoneStatus,
    MilestoneTrigger,
)
from app.db.models import (
    Deal,
    DealCost,
    EscrowAccount,
    LedgerEntry,
    Milestone,
    MilestoneConfirmation,
)
from app.domain.escrow import CONDITIONS
from app.domain.money import Money, money_sum, split_by_ratios
from seed.common import Ctx, Row, Rows, sid
from seed.parties import (
    BRIGHTLINE,
    BRIGHTLINE_USD,
    HUAMENG,
    HUAMENG_PERSONAL,
    HUAXIN,
    HUAXIN_CNY,
    KARIM,
    RAHIMA,
)

MAIN_DEAL = "SETU-2026-0001"
RATIOS = (Decimal("0.30"), Decimal("0.60"), Decimal("0.10"))
TRIGGERS = (MilestoneTrigger.PRODUCTION_START, MilestoneTrigger.SHIPMENT, MilestoneTrigger.ARRIVAL)
EVIDENCE: dict[MilestoneTrigger, list[str]] = {
    MilestoneTrigger.PRODUCTION_START: [DocType.PROFORMA_INVOICE, DocType.PRODUCTION_PHOTO],
    MilestoneTrigger.SHIPMENT: [
        DocType.BILL_OF_LADING,
        DocType.PACKING_LIST,
        DocType.COMMERCIAL_INVOICE,
    ],
    MilestoneTrigger.ARRIVAL: [DocType.BILL_OF_ENTRY],
}


@dataclass(frozen=True, slots=True)
class MS:
    """Milestone plan: due offset, status, and when (day offset) it was funded / released."""

    due: int
    status: MilestoneStatus
    funded: int | None = None
    released: int | None = None


@dataclass(frozen=True, slots=True)
class DealSpec:
    ref: str
    buyer: str
    supplier: str
    account: str
    title: str
    hs_code: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    opened: int
    status: DealStatus
    expected_sale: Decimal
    milestones: tuple[MS, MS, MS]
    costs: dict[CostKind, tuple[Decimal, int, str]] = field(default_factory=dict)
    funded_on: int | None = None
    completed_on: int | None = None
    on_time: bool | None = None
    disputes: int = 0
    dispute_reason: str | None = None
    port_of_loading: str = "Ningbo"

    @property
    def goods_value(self) -> Money:
        return Money(self.quantity * self.unit_price, "USD").quantized()

    def milestone_amounts(self) -> list[Money]:
        return split_by_ratios(self.goods_value, list(RATIOS))

    def landed_cost(self) -> Money:
        lines = [Money(amount, "USD") for amount, _, _ in self.costs.values()]
        return self.goods_value + money_sum(lines, "USD")


R, P, RD, F, X = (
    MilestoneStatus.RELEASED,
    MilestoneStatus.PENDING,
    MilestoneStatus.READY,
    MilestoneStatus.FROZEN,
    MilestoneStatus.CANCELLED,
)
D = Decimal

DEALS: tuple[DealSpec, ...] = (
    DealSpec(
        MAIN_DEAL,
        RAHIMA,
        HUAXIN,
        HUAXIN_CNY,
        "Dyed cotton jersey fabric",
        "6006.22",
        D("8000"),
        "m",
        D("1.20"),
        -9,
        DealStatus.FUNDED,
        D("13660.00"),
        (MS(0, RD, funded=-2), MS(18, P), MS(40, P)),
        {
            CostKind.FREIGHT: (
                D("600.00"),
                19,
                "Ocean freight Ningbo → Chittagong (FOB, buyer pays)",
            ),
            CostKind.INSURANCE: (D("50.00"), 14, "Marine cargo insurance"),
            CostKind.DUTY: (D("800.00"), 45, "Customs duty, due 5 days after arrival"),
            CostKind.BANK_CHARGES: (D("150.00"), 2, "Remittance and escrow bank charges"),
        },
        funded_on=-2,
    ),
    DealSpec(
        "SETU-2025-0011",
        RAHIMA,
        HUAXIN,
        HUAXIN_CNY,
        "Combed cotton single jersey fabric",
        "6006.22",
        D("6000"),
        "m",
        D("1.15"),
        -380,
        DealStatus.COMPLETED,
        D("9850.00"),
        (MS(-372, R, -376, -372), MS(-340, R, -342, -340), MS(-312, R, -313, -312)),
        {
            CostKind.FREIGHT: (D("450.00"), -339, "Ocean freight"),
            CostKind.INSURANCE: (D("35.00"), -345, "Marine cargo insurance"),
            CostKind.DUTY: (D("575.00"), -314, "Customs duty"),
            CostKind.BANK_CHARGES: (D("120.00"), -376, "Bank charges"),
        },
        funded_on=-376,
        completed_on=-310,
        on_time=True,
    ),
    DealSpec(
        "SETU-2025-0019",
        RAHIMA,
        HUAXIN,
        HUAXIN_CNY,
        "Dyed cotton rib fabric",
        "6006.22",
        D("5000"),
        "m",
        D("1.32"),
        -305,
        DealStatus.COMPLETED,
        D("9420.00"),
        (MS(-298, R, -301, -298), MS(-268, R, -270, -268), MS(-241, R, -242, -241)),
        {
            CostKind.FREIGHT: (D("420.00"), -265, "Ocean freight"),
            CostKind.INSURANCE: (D("33.00"), -270, "Marine cargo insurance"),
            CostKind.DUTY: (D("550.00"), -243, "Customs duty"),
            CostKind.BANK_CHARGES: (D("115.00"), -301, "Bank charges"),
        },
        funded_on=-301,
        completed_on=-238,
        on_time=True,
    ),
    DealSpec(
        "SETU-2026-0006",
        RAHIMA,
        BRIGHTLINE,
        BRIGHTLINE_USD,
        "Metal snap buttons and nylon zippers",
        "9606.10",
        D("37000"),
        "pcs",
        D("0.05"),
        -1,
        DealStatus.DRAFT,
        D("2600.00"),
        (MS(10, P), MS(30, P), MS(47, P)),
        {
            CostKind.FREIGHT: (D("90.00"), 31, "Ocean freight (LCL)"),
            CostKind.INSURANCE: (D("10.00"), 28, "Marine cargo insurance"),
            CostKind.DUTY: (D("260.00"), 52, "Customs duty"),
            CostKind.BANK_CHARGES: (D("40.00"), 10, "Bank charges"),
        },
    ),
    DealSpec(
        "SETU-2026-0004",
        KARIM,
        BRIGHTLINE,
        BRIGHTLINE_USD,
        "Woven polyester labels and plastic buttons",
        "5807.10",
        D("185000"),
        "pcs",
        D("0.04"),
        -48,
        DealStatus.SHIPPED,
        D("10650.00"),
        (MS(-41, R, -45, -41), MS(-12, R, -14, -12), MS(9, P)),
        {
            CostKind.FREIGHT: (D("380.00"), -10, "Ocean freight"),
            CostKind.INSURANCE: (D("40.00"), -14, "Marine cargo insurance"),
            CostKind.DUTY: (D("1480.00"), 14, "Customs duty, due 5 days after arrival"),
            CostKind.BANK_CHARGES: (D("110.00"), -45, "Bank charges"),
        },
        funded_on=-45,
    ),
    DealSpec(
        "SETU-2026-0005",
        KARIM,
        HUAMENG,
        HUAMENG_PERSONAL,
        "Poly-cotton poplin fabric",
        "5513.21",
        D("3440"),
        "m",
        D("1.25"),
        -30,
        DealStatus.IN_PRODUCTION,
        D("6050.00"),
        (MS(-1, RD, funded=-2), MS(15, P), MS(38, P)),
        {
            CostKind.FREIGHT: (D("260.00"), 17, "Ocean freight Guangzhou → Chittagong"),
            CostKind.INSURANCE: (D("25.00"), 12, "Marine cargo insurance"),
            CostKind.DUTY: (D("520.00"), 43, "Customs duty, due 5 days after arrival"),
            CostKind.BANK_CHARGES: (D("80.00"), -2, "Bank charges"),
        },
        funded_on=-2,
        port_of_loading="Guangzhou (Nansha)",
    ),
    DealSpec(
        "SETU-2026-0002",
        KARIM,
        BRIGHTLINE,
        BRIGHTLINE_USD,
        "Dyed plastic buttons",
        "9606.21",
        D("80000"),
        "pcs",
        D("0.04"),
        -140,
        DealStatus.DISPUTED,
        D("4500.00"),
        (MS(-133, R, -137, -133), MS(-105, R, -107, -105), MS(-80, F, -82)),
        {
            CostKind.FREIGHT: (D("200.00"), -100, "Ocean freight"),
            CostKind.INSURANCE: (D("20.00"), -104, "Marine cargo insurance"),
            CostKind.DUTY: (D("640.00"), -82, "Customs duty"),
            CostKind.BANK_CHARGES: (D("60.00"), -137, "Bank charges"),
        },
        funded_on=-137,
        on_time=False,
        disputes=1,
        dispute_reason="Quality: wrong shade on about 30% of dyed buttons (lot BL-0617); "
        "final 10% tranche frozen pending resolution",
    ),
    DealSpec(
        "SETU-2026-0003",
        KARIM,
        HUAXIN,
        HUAXIN_CNY,
        "Cotton fleece fabric",
        "6001.21",
        D("4000"),
        "m",
        D("1.45"),
        -75,
        DealStatus.CANCELLED,
        D("8100.00"),
        (MS(-68, X), MS(-40, X), MS(-15, X)),
    ),
)

DEALS_BY_REF = {d.ref: d for d in DEALS}


def deal_id(ref: str) -> uuid.UUID:
    return sid("deal", ref)


def milestone_id(ref: str, seq: int) -> uuid.UUID:
    return sid("milestone", f"{ref}:{seq}")


def cost_id(ref: str, kind: CostKind) -> uuid.UUID:
    return sid("deal_cost", f"{ref}:{kind}")


def _escrow_status(spec: DealSpec, funded: Decimal, released: Decimal) -> EscrowStatus:
    if spec.status == DealStatus.CANCELLED:
        return EscrowStatus.CANCELLED
    if spec.status == DealStatus.DISPUTED:
        return EscrowStatus.FROZEN
    if spec.status == DealStatus.COMPLETED:
        return EscrowStatus.COMPLETED
    if funded == 0:
        return EscrowStatus.DRAFT
    return EscrowStatus.TRANCHE_RELEASED if released > 0 else EscrowStatus.FUNDED


def _ledger_pair(
    ctx: Ctx,
    spec: DealSpec,
    txn: str,
    debit: str,
    credit: str,
    amount: Money,
    day: int,
    memo: str,
    kind: LedgerKind,
    seq: int,
) -> list[Row]:
    base = {
        "txn_ref": f"{spec.ref}:{txn}",
        "deal_id": deal_id(spec.ref),
        "amount": amount.amount,
        "currency": amount.currency,
        "memo": f"Simulated · {memo}",
        "posted_at": ctx.at(day, 11, 0),
        "simulated": True,
        "kind": kind,
        "milestone_id": milestone_id(spec.ref, seq),
        "fx_rate": None,
        "counter_amount": None,
        "counter_currency": None,
    }
    return [
        {
            **base,
            "id": sid("ledger", f"{spec.ref}:{txn}:dr"),
            "account": debit,
            "direction": LedgerDirection.DEBIT,
        },
        {
            **base,
            "id": sid("ledger", f"{spec.ref}:{txn}:cr"),
            "account": credit,
            "direction": LedgerDirection.CREDIT,
        },
    ]


def _evidence_status(spec: DealSpec, seq: int, status: MilestoneStatus) -> EvidenceStatus:
    """Released tranches were verified; the main deal's M1 evidence (PI + photos) passed its checks;
    the frozen disputed tranche is flagged; everything else is still waiting for evidence."""
    if status == MilestoneStatus.RELEASED or (spec.ref == MAIN_DEAL and seq == 1):
        return EvidenceStatus.VERIFIED
    return EvidenceStatus.FLAGGED if status == MilestoneStatus.FROZEN else EvidenceStatus.PENDING


def _confirmers(spec: DealSpec) -> list[tuple[ConfirmRole, str | None]]:
    """Both sides confirmed the schedule of every deal that got past DRAFT (demo users only)."""
    from seed.users import USERS

    by_party = {party: email for email, _, _, _, party in USERS if party}
    return [
        (ConfirmRole.BUYER, by_party.get(spec.buyer)),
        (ConfirmRole.SUPPLIER, by_party.get(spec.supplier)),
    ]


def build(ctx: Ctx) -> Rows:
    deals: list[Row] = []
    costs: list[Row] = []
    milestones: list[Row] = []
    escrows: list[Row] = []
    ledger: list[Row] = []
    confirmations: list[Row] = []
    for spec in DEALS:
        deals.append(
            {
                "id": deal_id(spec.ref),
                "reference": spec.ref,
                "buyer_id": sid("party", spec.buyer),
                "supplier_id": sid("party", spec.supplier),
                "beneficiary_account_id": sid("account", spec.account),
                "title": spec.title,
                "hs_code": spec.hs_code,
                "quantity": spec.quantity,
                "unit": spec.unit,
                "unit_price": spec.unit_price,
                "currency": "USD",
                "goods_value": spec.goods_value.amount,
                "incoterm": "FOB",
                "port_of_loading": spec.port_of_loading,
                "port_of_discharge": "Chittagong",
                "expected_sale_value": spec.expected_sale,
                "status": spec.status,
                "opened_on": ctx.day(spec.opened),
                "funded_on": ctx.day(spec.funded_on) if spec.funded_on is not None else None,
                "completed_on": ctx.day(spec.completed_on)
                if spec.completed_on is not None
                else None,
                "on_time": spec.on_time,
                "dispute_count": spec.disputes,
                "dispute_reason": spec.dispute_reason,
            }
        )
        for kind, (amount, due, note) in spec.costs.items():
            costs.append(
                {
                    "id": cost_id(spec.ref, kind),
                    "deal_id": deal_id(spec.ref),
                    "kind": kind,
                    "amount": amount,
                    "currency": "USD",
                    "due_on": ctx.day(due),
                    "note": note,
                }
            )
        funded = released = Decimal("0")
        buyer_cash = f"buyer:{spec.buyer}:cash"
        escrow_acct = f"escrow:{spec.ref}"
        supplier_acct = f"supplier:{spec.supplier}:settlement"
        for seq, (plan, trigger, ratio, amount) in enumerate(
            zip(spec.milestones, TRIGGERS, RATIOS, spec.milestone_amounts(), strict=True), start=1
        ):
            milestones.append(
                {
                    "id": milestone_id(spec.ref, seq),
                    "deal_id": deal_id(spec.ref),
                    "seq": seq,
                    "trigger": trigger,
                    "percent": ratio,
                    "amount": amount.amount,
                    "currency": "USD",
                    "due_on": ctx.day(plan.due),
                    "status": plan.status,
                    "required_evidence": [str(e) for e in EVIDENCE[trigger]],
                    "released_at": ctx.at(plan.released, 11, 0)
                    if plan.released is not None
                    else None,
                    "condition_text": CONDITIONS[trigger],
                    "evidence_status": _evidence_status(spec, seq, plan.status),
                    "release_idempotency_key": None,
                }
            )
            if plan.funded is not None:
                funded += amount.amount
                ledger += _ledger_pair(
                    ctx,
                    spec,
                    f"fund:m{seq}",
                    escrow_acct,
                    buyer_cash,
                    amount,
                    plan.funded,
                    f"buyer funds milestone {seq} into escrow",
                    LedgerKind.FUND,
                    seq,
                )
            if plan.released is not None:
                released += amount.amount
                ledger += _ledger_pair(
                    ctx,
                    spec,
                    f"release:m{seq}",
                    supplier_acct,
                    escrow_acct,
                    amount,
                    plan.released,
                    f"release milestone {seq} to supplier",
                    LedgerKind.RELEASE,
                    seq,
                )
        escrows.append(
            {
                "id": sid("escrow", spec.ref),
                "deal_id": deal_id(spec.ref),
                "currency": "USD",
                "funded_total": funded,
                "released_total": released,
                "balance": funded - released,
                "status": _escrow_status(spec, funded, released),
                "simulated": True,
                "refunded_total": Decimal("0"),
                "partner": "Simulated Escrow Partner",
                "advance_over_20k": False,
            }
        )
        if spec.status not in (DealStatus.DRAFT, DealStatus.CANCELLED):
            for role, user_email in _confirmers(spec):
                confirmations.append(
                    {
                        "id": sid("confirmation", f"{spec.ref}:{role}"),
                        "deal_id": deal_id(spec.ref),
                        "party_role": role,
                        "user_id": sid("user", user_email) if user_email else None,
                        "confirmed_at": ctx.at(spec.opened + 1, 10, 0),
                    }
                )
    return [
        (Deal, deals),
        (DealCost, costs),
        (Milestone, milestones),
        (EscrowAccount, escrows),
        (LedgerEntry, ledger),
        (MilestoneConfirmation, confirmations),
    ]
