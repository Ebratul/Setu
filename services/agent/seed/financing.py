"""Mock financing catalogue (all providers fictional).

Eligibility rule tree, evaluated by the FR-1 matcher:
    {"all": [{"fact": <name>, "op": "eq|gte|lte|in", "value": <json>}, ...]}
Facts the matcher must supply per (buyer, deal):
    supplier_code, supplier_kyb_status, buyer_kyb_status, completed_deals_with_supplier,
    completed_deals_total, escrow_funded (bool), amount_usd (string decimal), tenor_days,
    months_trading
"""

from decimal import Decimal

from app.db.enums import FinancingKind
from app.db.models import FinancingOption
from seed.common import Ctx, Row, Rows, sid
from seed.parties import HUAXIN, INSURER, LENDER_A, LENDER_B, NBFI


def rule(fact: str, op: str, value: object) -> Row:
    return {"fact": fact, "op": op, "value": value}


def option(
    code: str,
    name: str,
    kind: FinancingKind,
    provider: str,
    *,
    collateral: str,
    conditions: str,
    eligibility: list[Row],
    **terms: object,
) -> Row:
    row: Row = {
        "id": sid("financing", code),
        "code": code,
        "name": name,
        "kind": kind,
        "provider_party_id": sid("party", provider),
        "currency": "USD",
        "annual_rate": None,
        "flat_cost_rate": None,
        "price_uplift_rate": None,
        "fee_rate": None,
        "fee_fixed": None,
        "tenor_days_min": None,
        "tenor_days_max": None,
        "tenor_rule": None,
        "min_amount": None,
        "max_amount": None,
        "collateral": collateral,
        "conditions": conditions,
        "eligibility": {"all": eligibility},
        "active": True,
    }
    row.update(terms)
    return row


def build(ctx: Ctx) -> Rows:
    D = Decimal
    rows = [
        option(
            "supplier-credit-huaxin",
            "Supplier credit — Shaoxing Huaxin (60 days)",
            FinancingKind.SUPPLIER_CREDIT,
            HUAXIN,
            price_uplift_rate=D("0.020000"),
            annual_rate=D("0"),
            tenor_days_min=60,
            tenor_days_max=60,
            collateral="None",
            conditions="0% interest, but goods are priced 2% higher; pay 60 days after shipment.",
            eligibility=[
                rule("supplier_code", "eq", HUAXIN),
                rule("supplier_kyb_status", "eq", "VERIFIED"),
                rule("completed_deals_with_supplier", "gte", 1),
            ],
        ),
        option(
            "import-loan-meghna",
            "Import loan — Meghna Commercial Bank (Lender A)",
            FinancingKind.BANK_IMPORT_LOAN,
            LENDER_A,
            annual_rate=D("0.115000"),
            fee_rate=D("0.005000"),
            tenor_days_min=90,
            tenor_days_max=90,
            min_amount=D("2000.00"),
            max_amount=D("50000.00"),
            collateral="Lien on imported goods + post-dated cheque",
            conditions="11.5% p.a., 0.5% processing fee, 90-day tenor, minimum USD 2,000.",
            eligibility=[
                rule("buyer_kyb_status", "eq", "VERIFIED"),
                rule("amount_usd", "gte", "2000.00"),
                rule("months_trading", "gte", 12),
            ],
        ),
        option(
            "escrow-order-loan-setu-partner",
            "Escrow-backed order loan — Setu Partner Finance (Lender B)",
            FinancingKind.ESCROW_BACKED_LOAN,
            LENDER_B,
            annual_rate=D("0.090000"),
            fee_fixed=D("40.00"),
            tenor_rule="UNTIL_MILESTONE_3",
            tenor_days_max=120,
            min_amount=D("500.00"),
            max_amount=D("30000.00"),
            collateral="Assignment of the funded escrow tranches",
            conditions="9.0% p.a., USD 40 flat fee, repaid when milestone 3 is released.",
            eligibility=[
                rule("escrow_funded", "eq", True),
                rule("supplier_kyb_status", "eq", "VERIFIED"),
            ],
        ),
        option(
            "insured-supplier-terms",
            "Export-credit-insured supplier terms — Silk Route Cover",
            FinancingKind.INSURED_SUPPLIER_TERMS,
            INSURER,
            flat_cost_rate=D("0.012000"),
            tenor_days_min=90,
            tenor_days_max=90,
            min_amount=D("3000.00"),
            collateral="Supplier's export-credit insurance policy",
            conditions="Supplier ships on 90-day open account; about 1.2% flat cost passed on.",
            eligibility=[
                rule("completed_deals_with_supplier", "gte", 2),
                rule("supplier_kyb_status", "eq", "VERIFIED"),
            ],
        ),
        option(
            "working-capital-shitalakshya",
            "Working-capital line — Shitalakshya Capital (NBFI)",
            FinancingKind.WORKING_CAPITAL_LINE,
            NBFI,
            annual_rate=D("0.140000"),
            tenor_days_min=30,
            tenor_days_max=120,
            min_amount=D("1000.00"),
            max_amount=D("25000.00"),
            collateral="Personal guarantee of the proprietor",
            conditions="14% p.a. on the drawn amount, 30 to 120 days, no invoice needed.",
            eligibility=[
                rule("buyer_kyb_status", "eq", "VERIFIED"),
                rule("months_trading", "gte", 12),
            ],
        ),
    ]
    return [(FinancingOption, rows)]
