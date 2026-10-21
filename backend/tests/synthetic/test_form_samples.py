"""Every demo value set is accepted by the real request model of its form, every referenced file
exists and is a valid upload, and the committed documentation is current."""

import re
import uuid
from datetime import date, timedelta
from typing import Any

import pytest

from app.api.audit import TamperIn
from app.api.risk import DryRunRequest
from app.schemas.analysis import LandedCostRequest
from app.schemas.approvals import AccountChangeIn, EmailCheckIn
from app.schemas.cashflow import ScenarioRequest
from app.schemas.chat import ChatRequest
from app.schemas.deals import CreateDealRequest, FundRequest, ProposeRequest
from app.schemas.financing import MatchRequest
from app.schemas.injection import ConsoleRunIn
from app.schemas.onboarding import (
    BuyerBusinessIn,
    ContactIn,
    InviteIn,
    RejectIn,
    RequestChangesIn,
    RevealIn,
    SupplierBusinessIn,
)
from app.schemas.privacy import PrivacyDryRunIn
from app.services.documents import upload
from synthetic.form_samples import build
from synthetic.form_samples.forms import BY_KEY, FORMS, NEGATIVE, Form
from synthetic.form_samples.people import BUYERS, ORDERS, SUPPLIERS

OUT = build.OUT
VOLUME = {
    "Under 500K": "UNDER_500K_BDT",
    "500K to 2M": "500K_2M_BDT",
    "2M to 10M": "2M_10M_BDT",
    "Over 10M": "OVER_10M_BDT",
}
REVEAL = {
    "TIN": "tin",
    "Trade licence number": "trade_license_no",
    "IRC number": "irc_no",
    "USCC": "uscc",
    "Bank account number": "bank_account_no",
}
TODAY = date.today()


def col(key: str, n: int) -> dict[str, str]:
    """Field label -> value for set `n` (0 based) of a form."""
    return {label: values[n] for label, values in BY_KEY[key].rows}


def buyer_business(c: dict[str, str]) -> dict[str, Any]:
    return {
        "legal_name": c["Legal company name"],
        "trade_name": c["Trade name"],
        "trade_license_no": c["Trade licence number"],
        "license_authority": c["Issuing authority"],
        "license_expiry": c["Licence expiry date"],
        "irc_no": c["Import Registration Certificate (IRC) number"],
        "tin": c["TIN"],
        "address": {
            "division": c["Division"],
            "district": c["District"],
            "upazila": c["Upazila"],
            "street": c["Street address"],
        },
        "business_type": c["Business type"].upper(),
        "main_import_goods": c["Main goods you import"],
        "monthly_import_volume": VOLUME[c["Monthly import volume (BDT)"]],
    }


def supplier_business(c: dict[str, str]) -> dict[str, Any]:
    return {
        "legal_name_en": c["Company name (English)"],
        "legal_name_zh": c["Company name (Chinese)"],
        "uscc": c["Unified Social Credit Code (USCC)"],
        "address": {
            "province": c["Province"],
            "city": c["City"],
            "district": c["District"],
            "street": c["Street address"],
        },
        "business_scope": c["Business scope"],
        "export_experience_years": int(c["Years of export experience"]),
        "wechat_id": c["WeChat ID"],
        "contact_phone": c["Contact phone"],
        "bank": {
            "bank_name": c["Bank name"],
            "holder_name": c["Account holder name"],
            "account_no": c["Account number"],
            "currency": c["Account currency"],
            "swift": c["SWIFT/BIC code"],
        },
    }


def contact(c: dict[str, str]) -> dict[str, str]:
    return {
        "full_name": c["Full name"],
        "designation": c["Job title"],
        "mobile": c["Mobile number"],
        "language": c["Language"],
    }


def cost_lines(c: dict[str, str]) -> list[dict[str, str]]:
    lines = []
    for label, kind in (
        ("Freight", "FREIGHT"),
        ("Insurance", "INSURANCE"),
        ("Duty", "DUTY"),
        ("Bank charges", "BANK_CHARGES"),
    ):
        if c[label]:
            lines.append({"kind": kind, "amount": c[label]})
    if c["Other (label)"]:
        amount, label = c["Other (label)"].split(" ", 1)
        lines.append({"kind": "OTHER", "amount": amount, "label": label.strip("()")})
    return lines


def landed_cost(c: dict[str, str]) -> dict[str, Any]:
    return {
        "currency": c["Input currency"],
        "goods_value": c["Goods value"],
        "quantity": c["Quantity"],
        "unit": c["Unit"],
        "selling_price_per_unit": c["Selling price per unit"],
        "cost_lines": cost_lines(c),
    }


def rel(spec: str) -> str:
    """'today + 3 days' -> ISO date."""
    days = int(re.search(r"\+ (\d+) day", spec).group(1))  # type: ignore[union-attr]
    return (TODAY + timedelta(days=days)).isoformat()


def whatif(c: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {"days": 90}
    if c["Add a loan inflow"] == "yes":
        loan: dict[str, str] = {"amount": c["Loan amount (USD)"], "on": rel(c["Loan arrives on"])}
        if c["Repay on (optional)"]:
            loan["repay_on"] = rel(c["Repay on (optional)"])
            loan["repay_amount"] = c["Repayment amount (optional)"]
        body["loans"] = [loan]
    return body


def email_text(c: dict[str, str]) -> str:
    path = c["Email text"].removeprefix("paste the file ")
    return (OUT / path).read_text(encoding="utf-8")


def percents(c: dict[str, str]) -> dict[str, Any]:
    if c["Schedule"] != "Custom":
        return {"template": "30/60/10"}
    return {
        "template": "custom",
        "percents": [
            c[k] for k in ("Tranche 1 %", "Tranche 2 %", "Tranche 3 %", "Tranche 4 %") if c[k]
        ],
    }


def deal_create(c: dict[str, str]) -> dict[str, Any]:
    return {
        "supplier_id": str(uuid.uuid4()),
        "title": c["Goods"],
        "hs_code": c["HS code"],
        "quantity": c["Quantity"],
        "unit": c["Unit"],
        "unit_price": c["Unit price"],
        "currency": c["Input currency"],
        "incoterm": c["Incoterm"],
        "port_of_loading": c["Port of loading"],
        "port_of_discharge": c["Port of discharge"],
        "expected_sale_value": c["Expected sale value"],
        "costs": [
            {"kind": "FREIGHT", "amount": c["Freight"]},
            {"kind": "INSURANCE", "amount": c["Insurance"]},
            {"kind": "DUTY", "amount": c["Duty & taxes"]},
            {"kind": "BANK_CHARGES", "amount": c["Bank charges"]},
        ],
    }


def payout(c: dict[str, str]) -> dict[str, Any]:
    return {
        "deal_id": str(uuid.uuid4()),
        "bank_name": c["Bank name"],
        "bank_country": c["Bank country (2 letters)"],
        "account_number": c["Account number"],
        "holder_name": c["Account holder name"],
        "account_type": c["Account type"].upper(),
        "currency": c["Currency"],
    }


def match(c: dict[str, str]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "mode": "shortfall" if c["What to finance"] == "Cover shortfall" else "order"
    }
    if c["Deal (whole order only)"]:
        body["deal_id"] = c["Deal (whole order only)"]
    if c["Amount to finance"]:
        body["amount"] = c["Amount to finance"]
    return body


def risk(c: dict[str, str]) -> dict[str, Any]:
    return {
        "amount_usd": c["Amount (USD)"],
        "fraud_score": int(c["Document fraud score (0-100)"]),
        "first_deal": c["First deal with this supplier"] == "yes",
        "hidden_instruction": c["Hidden instruction found in a document"] == "yes",
        "sanctions_hit": c["Sanctions hit"] == "yes",
    }


def tamper(c: dict[str, str]) -> dict[str, Any]:
    mode = {
        "Edit a value": "edit",
        "Delete the entry": "delete",
        "Swap with the next entry": "reorder",
    }[c["Change"]]
    body: dict[str, Any] = {"mode": mode, "seq": int(c["Entry (seq)"])}
    if mode == "edit":
        body |= {"field": c["Field"], "value": c["New value"]}
    if mode == "reorder":
        body["other_seq"] = body["seq"] + 1
    return body


BUILDERS: dict[str, tuple[type, Any]] = {
    "ob-contact-buyer": (ContactIn, contact),
    "ob-contact-supplier": (ContactIn, contact),
    "ob-business-buyer": (BuyerBusinessIn, buyer_business),
    "ob-business-supplier": (SupplierBusinessIn, supplier_business),
    "team-invite": (
        InviteIn,
        lambda c: {
            "email": c["Email address"],
            "display_name": c["Name"],
            "member_role": c["Role"].upper(),
        },
    ),
    "deal-create": (CreateDealRequest, deal_create),
    "milestone-propose": (ProposeRequest, percents),
    "escrow-fund": (FundRequest, lambda c: {"amount": c["Amount (USD)"]}),
    "payout-account": (AccountChangeIn, payout),
    "email-check": (EmailCheckIn, lambda c: {"text": email_text(c)}),
    "landed-cost": (LandedCostRequest, landed_cost),
    "target-margin": (
        LandedCostRequest,
        lambda c: {
            "goods_value": "100",
            "quantity": "1",
            "target_margin_pct": c["Target margin (%)"],
        },
    ),
    "financing-match": (MatchRequest, match),
    "cashflow-whatif": (ScenarioRequest, whatif),
    "chat": (
        ChatRequest,
        lambda c: {
            "message": c["Message to Setu"],
            "language": c["Language"],
            **({"deal_id": c["About deal"]} if c["About deal"] != "No specific deal" else {}),
        },
    ),
    "admin-reject": (RejectIn, lambda c: {"reason": c["Reason (10 to 500 characters)"]}),
    "admin-suspend": (RejectIn, lambda c: {"reason": c["Reason (10 to 500 characters)"]}),
    "admin-request-changes": (
        RequestChangesIn,
        lambda c: {
            "items": [{"target": c["Item to fix"], "note": c["Note (3 to 300 characters)"]}]
        },
    ),
    "admin-reveal": (
        RevealIn,
        lambda c: {"field": REVEAL[c["Field"]], "reason": c["Reason (10 to 300 characters)"]},
    ),
    "risk-playground": (DryRunRequest, risk),
    "privacy-playground": (
        PrivacyDryRunIn,
        lambda c: {"text": c["Text to protect"], "mask_amounts": c["Mask amounts"] == "yes"},
    ),
    "injection-console": (ConsoleRunIn, lambda c: {"attack_id": c["Attack gallery item"]}),
    "audit-tamper": (TamperIn, tamper),
}


def test_every_form_has_five_complete_sets() -> None:
    assert len({f.key for f in FORMS}) == len(FORMS)
    for f in FORMS:
        assert len(f.heads) == 5, f.key
        for label, values in f.rows:
            assert len(values) == 5, (f.key, label)


@pytest.mark.parametrize("key", sorted(BUILDERS))
@pytest.mark.parametrize("n", range(5))
def test_set_is_accepted_by_the_request_model(key: str, n: int) -> None:
    model, build_payload = BUILDERS[key]
    model.model_validate(build_payload(col(key, n)))


@pytest.mark.parametrize("n", range(5))
def test_account_forms_follow_the_password_and_email_rules(n: int) -> None:
    reg, reset = col("register", n), col("reset-password", n)
    assert (
        re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", reg["Email"])
        and len(reg["Password (min 8)"]) >= 8
    )
    assert (
        reset["New password"] == reset["Confirm new password"] and len(reset["New password"]) >= 8
    )
    assert reg["Email"] == col("sign-in", n)["Email"] == col("forgot-password", n)["Email"]
    assert col("verify-email", n)["Verification code"].isdigit()


def referenced_files() -> list[str]:
    found: list[str] = []
    for form in FORMS:
        for _, values in form.rows:
            for v in values:
                if v.startswith(build.LINK_PREFIXES):
                    found.append(v.removeprefix("paste the file "))
    found += [p for p, _ in NEGATIVE]
    return found


def test_every_referenced_file_exists() -> None:
    missing = [p for p in referenced_files() if not (OUT / p).exists()]
    assert not missing, missing


def test_onboarding_and_order_files_are_valid_uploads_with_unique_content() -> None:
    seen: dict[str, str] = {}
    for p in sorted((OUT / "onboarding").rglob("*.*")) + sorted((OUT / "orders").rglob("*.*")):
        data = p.read_bytes()
        assert 0 < len(data) <= 4 * 1024 * 1024, p
        assert upload.sniff(data) is not None, p
        key = build.files.sha(data)
        assert key not in seen, f"{p} duplicates {seen[key]}"
        seen[key] = str(p)


def test_every_set_has_all_its_files() -> None:
    for b in BUYERS:
        names = {p.name for p in (OUT / f"onboarding/buyer-{b.n}").iterdir()}
        assert len(names) == 5, names
    for s in SUPPLIERS:
        assert len(list((OUT / f"onboarding/supplier-{s.n}").iterdir())) == 4
    for o in ORDERS:
        assert len(list((OUT / f"orders/order-{o.n}").iterdir())) == 8


def test_documentation_is_up_to_date() -> None:
    assert build.DOC.read_text(encoding="utf-8") == build.render_doc(), (
        "run: uv run --directory backend python -m synthetic.form_samples.build"
    )


def test_form_objects_are_forms() -> None:
    assert all(isinstance(f, Form) for f in FORMS)
