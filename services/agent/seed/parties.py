"""Buyers, suppliers and lenders (all fictional), their receiving accounts and KYB results.
Account numbers are fake and prefixed 'SIM-'."""

from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import AccountStatus, AccountType, KybStatus, PartyKind
from app.db.models import BankAccount, KybCheck, Party
from seed.common import Ctx, Row, Rows, sid

RAHIMA = "rahima-knitwear"
KARIM = "dhaka-stitch-works"
HUAXIN = "shaoxing-huaxin"
BRIGHTLINE = "ningbo-brightline"
HUAMENG = "guangzhou-huameng"
LENDER_A = "meghna-commercial-bank"
LENDER_B = "setu-partner-finance"
INSURER = "silk-route-credit-cover"
NBFI = "shitalakshya-capital"

HUAXIN_CNY = "huaxin-cny-corporate"
HUAXIN_HK_PENDING = "huaxin-hk-pending"
BRIGHTLINE_USD = "brightline-usd-corporate"
HUAMENG_PERSONAL = "huameng-personal"


@dataclass(frozen=True, slots=True)
class PartySpec:
    code: str
    kind: PartyKind
    legal_name: str
    city: str
    country: str
    first_seen: int
    license_no: str | None = None
    alias: str | None = None
    cash_balance: Decimal | None = None
    kyb: KybStatus = KybStatus.VERIFIED


PARTIES: tuple[PartySpec, ...] = (
    PartySpec(
        RAHIMA,
        PartyKind.BUYER,
        "Rahima Knitwear",
        "Narayanganj",
        "BD",
        -720,
        "NCC-TL-SIM-2019-0412",
        cash_balance=Decimal("6000.00"),
    ),
    PartySpec(
        KARIM,
        PartyKind.BUYER,
        "Dhaka Stitch Works",
        "Mirpur, Dhaka",
        "BD",
        -540,
        "DNCC-TL-SIM-2020-1187",
        cash_balance=Decimal("18500.00"),
    ),
    PartySpec(
        HUAXIN,
        PartyKind.SUPPLIER,
        "Shaoxing Huaxin Textile Co., Ltd.",
        "Shaoxing",
        "CN",
        -400,
        "USCC-SIM-91330602HX0001",
    ),
    PartySpec(
        BRIGHTLINE,
        PartyKind.SUPPLIER,
        "Ningbo Brightline Accessories Co., Ltd.",
        "Ningbo",
        "CN",
        -300,
        "USCC-SIM-91330201BL0002",
    ),
    PartySpec(
        HUAMENG,
        PartyKind.SUPPLIER,
        "Guangzhou Huameng Trading Co., Ltd.",
        "Guangzhou",
        "CN",
        -200,
        "USCC-SIM-91440101HM0003",
        kyb=KybStatus.WARNING,
    ),
    PartySpec(
        LENDER_A, PartyKind.LENDER, "Meghna Commercial Bank", "Dhaka", "BD", -900, alias="Lender A"
    ),
    PartySpec(
        LENDER_B, PartyKind.LENDER, "Setu Partner Finance", "Dhaka", "BD", -900, alias="Lender B"
    ),
    PartySpec(INSURER, PartyKind.LENDER, "Silk Route Export Credit Cover", "Shanghai", "CN", -900),
    PartySpec(
        NBFI, PartyKind.LENDER, "Shitalakshya Capital Finance PLC", "Narayanganj", "BD", -900
    ),
)

PARTY_NAMES = {p.code: p.legal_name for p in PARTIES}


@dataclass(frozen=True, slots=True)
class AccountSpec:
    key: str
    party: str
    bank_name: str
    bank_country: str
    number: str
    holder: str
    account_type: AccountType
    currency: str
    status: AccountStatus
    opened: int
    first_seen: int
    verified: bool
    via: str | None = None


ACCOUNTS: tuple[AccountSpec, ...] = (
    AccountSpec(
        "rahima-bdt",
        RAHIMA,
        "Meghna Commercial Bank",
        "BD",
        "SIM-BD-0112-004521",
        "Rahima Knitwear",
        AccountType.CORPORATE,
        "BDT",
        AccountStatus.ACTIVE,
        -700,
        -700,
        True,
    ),
    AccountSpec(
        "karim-bdt",
        KARIM,
        "Meghna Commercial Bank",
        "BD",
        "SIM-BD-0145-009876",
        "Dhaka Stitch Works",
        AccountType.CORPORATE,
        "BDT",
        AccountStatus.ACTIVE,
        -530,
        -530,
        True,
    ),
    AccountSpec(
        HUAXIN_CNY,
        HUAXIN,
        "Shaoxing Riverside Commercial Bank",
        "CN",
        "SIM-CN-6222-0400-1188",
        "Shaoxing Huaxin Textile Co., Ltd.",
        AccountType.CORPORATE,
        "CNY",
        AccountStatus.ACTIVE,
        -1500,
        -400,
        True,
    ),
    AccountSpec(
        HUAXIN_HK_PENDING,
        HUAXIN,
        "Victoria Harbour Trade Bank",
        "HK",
        "SIM-HK-012-884213-001",
        "Huaxin Textile (HK) Trading Ltd",
        AccountType.CORPORATE,
        "USD",
        AccountStatus.PENDING_CHANGE,
        -6,
        -1,
        False,
        via="email",
    ),
    AccountSpec(
        BRIGHTLINE_USD,
        BRIGHTLINE,
        "Ningbo Harbour Bank",
        "CN",
        "SIM-CN-3301-2290-5521",
        "Ningbo Brightline Accessories Co., Ltd.",
        AccountType.CORPORATE,
        "USD",
        AccountStatus.ACTIVE,
        -1100,
        -300,
        True,
    ),
    AccountSpec(
        HUAMENG_PERSONAL,
        HUAMENG,
        "Pearl River Savings Bank",
        "CN",
        "SIM-CN-6217-0003-7731",
        "Chen Wei",
        AccountType.PERSONAL,
        "CNY",
        AccountStatus.ACTIVE,
        -9,
        -3,
        False,
    ),
)


def _ok(code: str, message: str) -> Row:
    return {"code": code, "ok": True, "message": message}


def _flag(code: str, message: str) -> Row:
    return {"code": code, "ok": False, "message": message}


def kyb_rows(ctx: Ctx) -> list[Row]:
    def check(
        key: str, party: str, account: str | None, status: KybStatus, score: str, reasons: list[Row]
    ) -> Row:
        return {
            "id": sid("kyb", key),
            "party_id": sid("party", party),
            "bank_account_id": sid("account", account) if account else None,
            "status": status,
            "score": Decimal(score),
            "reasons": reasons,
            "notes": None,
            "checked_at": ctx.at(-1, 9, 0),
        }

    return [
        check(
            "huaxin",
            HUAXIN,
            HUAXIN_CNY,
            KybStatus.VERIFIED,
            "0.97",
            [
                _ok("LICENSE_NAME_MATCH", "Licence name matches invoice name"),
                _ok("ACCOUNT_HOLDER_MATCH", "Account holder name is identical to the licence name"),
                _ok("CORPORATE_ACCOUNT", "Receiving account is a corporate CNY account"),
                _ok("ESTABLISHED_ACCOUNT", "Account first seen 400 days ago"),
            ],
        ),
        check(
            "huaxin-hk",
            HUAXIN,
            HUAXIN_HK_PENDING,
            KybStatus.WARNING,
            "0.35",
            [
                _flag(
                    "BENEFICIARY_CHANGE", "New receiving account requested for an existing supplier"
                ),
                _flag(
                    "CHANGE_VIA_EMAIL", "Change requested by email, not through the supplier portal"
                ),
                _flag(
                    "HOLDER_NAME_MISMATCH",
                    "Holder 'Huaxin Textile (HK) Trading Ltd' differs from licence name "
                    "'Shaoxing Huaxin Textile Co., Ltd.'",
                ),
                _flag("NEW_ACCOUNT", "Account first seen 1 day ago (< 90 days)"),
                _flag("JURISDICTION_CHANGE", "Account country HK differs from licence country CN"),
            ],
        ),
        check(
            "brightline",
            BRIGHTLINE,
            BRIGHTLINE_USD,
            KybStatus.VERIFIED,
            "0.94",
            [
                _ok("LICENSE_NAME_MATCH", "Licence name matches invoice name"),
                _ok("ACCOUNT_HOLDER_MATCH", "Account holder name is identical to the licence name"),
                _ok("CORPORATE_ACCOUNT", "Receiving account is a corporate USD account"),
                _ok("ESTABLISHED_ACCOUNT", "Account first seen 300 days ago"),
            ],
        ),
        check(
            "huameng",
            HUAMENG,
            HUAMENG_PERSONAL,
            KybStatus.WARNING,
            "0.42",
            [
                _ok("LICENSE_NAME_MATCH", "Licence name matches invoice name"),
                _flag(
                    "PERSONAL_ACCOUNT", "Receiving account is a PERSONAL account held by 'Chen Wei'"
                ),
                _flag(
                    "HOLDER_NAME_MISMATCH",
                    "Holder 'Chen Wei' differs from licence name "
                    "'Guangzhou Huameng Trading Co., Ltd.'",
                ),
                _flag("NEW_ACCOUNT", "Account first seen 3 days ago (< 90 days)"),
            ],
        ),
    ]


def build(ctx: Ctx) -> Rows:
    parties = [
        {
            "id": sid("party", p.code),
            "code": p.code,
            "kind": p.kind,
            "legal_name": p.legal_name,
            "license_name": p.legal_name if p.license_no else None,
            "license_no": p.license_no,
            "alias": p.alias,
            "city": p.city,
            "country": p.country,
            "first_seen_on": ctx.day(p.first_seen),
            "cash_balance": p.cash_balance,
            "cash_currency": "USD" if p.cash_balance is not None else None,
            "kyb_status": p.kyb,
        }
        for p in PARTIES
    ]
    accounts = [
        {
            "id": sid("account", a.key),
            "party_id": sid("party", a.party),
            "bank_name": a.bank_name,
            "bank_country": a.bank_country,
            "account_number": a.number,
            "holder_name": a.holder,
            "account_type": a.account_type,
            "currency": a.currency,
            "status": a.status,
            "opened_on": ctx.day(a.opened),
            "first_seen_on": ctx.day(a.first_seen),
            "verified": a.verified,
            "change_requested_via": a.via,
            "change_requested_at": ctx.at(-1, 21, 40) if a.via else None,
        }
        for a in ACCOUNTS
    ]
    return [(Party, parties), (BankAccount, accounts), (KybCheck, kyb_rows(ctx))]
