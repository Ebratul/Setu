"""Deterministic label parser for trade-document text ("Label: value" lines).

Handles the layout variations of the synthetic renderer and typical real documents: four date
formats (day-first when `dd/mm/yyyy` is ambiguous, resolved by the whole document), thousands
separators, values wrapped over several lines, swapped or reordered blocks (labels are explicit),
and "name, address" party lines. Nothing here reads hidden text: callers pass visible text only.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from app.forensics.fields import FIELD_MODELS, REQUIRED, DocFields

DateOrder = Literal["DMY", "MDY"]
CURRENCIES = frozenset(
    [
        "USD",
        "CNY",
        "RMB",
        "BDT",
        "EUR",
        "GBP",
        "HKD",
        "JPY",
        "INR",
        "SGD",
        "AED",
        "CAD",
        "AUD",
        "CHF",
        "KRW",
        "MYR",
        "THB",
        "VND",
        "PKR",
        "LKR",
    ]
)
MAX_TEXT = 400
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠﻿]")

# label (casefolded) -> field; None = recognised but ignored
LABELS: dict[str, dict[str, str | None]] = {
    "INVOICE": {
        "invoice no.": "invoice_no",
        "invoice date": "date",
        "seller": "seller",
        "seller address": "seller_address",
        "seller licence no.": "seller_license_no",
        "buyer": "buyer",
        "buyer address": "buyer_address",
        "buyer licence no.": "buyer_license_no",
        "goods description": "goods_description",
        "hs code": "hs_code",
        "quantity": "quantity",
        "unit price": "unit_price",
        "total amount": "total",
        "incoterm": "incoterm",
        "payment terms": "payment_terms",
        "port of loading": "port_of_loading",
        "port of discharge": "port_of_discharge",
        "booked vessel / voyage": "vessel_voyage",
        "production completion": "production_complete",
        "estimated shipment date": "est_ship_date",
        "estimated arrival": "eta",
        "bank name": "bank_name",
        "account holder": "bank_holder",
        "account no.": "bank_account",
        "swift code": "bank_swift",
        "notes": "notes",
        "authorised signatory": None,
    },
    "PACKING_LIST": {
        "packing list no.": "pl_no",
        "date": "date",
        "invoice no.": "invoice_no",
        "seller": "seller",
        "seller address": "seller_address",
        "buyer": "buyer",
        "buyer address": "buyer_address",
        "goods description": "goods_description",
        "packages": "packages",
        "quantity": "quantity",
        "net weight": "net_weight_kg",
        "gross weight": "gross_weight_kg",
        "shipping marks": "marks",
        "notes": "notes",
        "authorised signatory": None,
    },
    "BILL_OF_LADING": {
        "b/l no.": "bl_no",
        "carrier": "carrier",
        "shipper": "shipper",
        "consignee": "consignee",
        "notify party": "notify_party",
        "vessel": "vessel",
        "voyage no.": "voyage",
        "port of loading": "port_of_loading",
        "port of discharge": "port_of_discharge",
        "on board date": "on_board_date",
        "container no.": "container_no",
        "description of goods": "description",
        "packages": "packages",
        "quantity": "quantity",
        "gross weight": "gross_weight_kg",
        "freight terms": "freight_terms",
        "notes": "notes",
        "authorised signatory": None,
    },
    "CERTIFICATE_OF_ORIGIN": {
        "certificate no.": "coo_no",
        "date of issue": "issue_date",
        "issued by": "issuing_body",
        "exporter": "exporter",
        "consignee": "consignee",
        "country of origin": "origin_country",
        "hs code": "hs_code",
        "description of goods": "description",
        "quantity": "quantity",
        "notes": "notes",
        "authorised signatory": None,
    },
    "BILL_OF_ENTRY": {
        "bill of entry no.": "boe_no",
        "date": "date",
        "port": "port",
        "b/l no.": "bl_no",
        "importer": "importer",
        "hs code": "hs_code",
        "description of goods": "description",
        "quantity": "quantity",
        "assessed value": "assessed_value_usd",
        "duty payable": "duty_usd",
        "exchange rate": "fx_usd_bdt",
        "assessed value (bdt)": "assessed_value_bdt",
        "duty payable (bdt)": "duty_bdt",
        "notes": "notes",
        "authorised signatory": None,
    },
}
FAMILY = {
    "PROFORMA_INVOICE": "INVOICE",
    "COMMERCIAL_INVOICE": "INVOICE",
    "PACKING_LIST": "PACKING_LIST",
    "BILL_OF_LADING": "BILL_OF_LADING",
    "CERTIFICATE_OF_ORIGIN": "CERTIFICATE_OF_ORIGIN",
    "BILL_OF_ENTRY": "BILL_OF_ENTRY",
}
# Fields whose value may continue on the next line(s).
WRAPPABLE = frozenset(
    {
        "seller", "seller_address", "buyer", "buyer_address", "goods_description", "payment_terms",
        "shipper", "consignee", "notify_party", "description", "marks", "notes", "importer",
        "bank_holder", "bank_name", "issuing_body", "carrier",
    }
)  # fmt: skip
PARTY_ADDRESS = {
    "shipper": "shipper_address",
    "consignee": "consignee_address",
    "exporter": "exporter_address",
    "importer": "importer_address",
}
_TITLES = {
    "PROFORMA INVOICE": "PROFORMA_INVOICE",
    "COMMERCIAL INVOICE": "COMMERCIAL_INVOICE",
    "PACKING LIST": "PACKING_LIST",
    "BILL OF LADING": "BILL_OF_LADING",
    "CERTIFICATE OF ORIGIN": "CERTIFICATE_OF_ORIGIN",
    "BILL OF ENTRY": "BILL_OF_ENTRY",
}
_SECTION = re.compile(r"^[A-Z][A-Z /&]{2,40}$")
_TABLE_HEAD = re.compile(r"^item\s+hs code\s+quantity\s+unit price\s+amount$", re.I)
_FOOTER = re.compile(r"^SIMULATED\b")
_SUFFIX_TOKEN = re.compile(r"^(ltd|limited|inc|llc|co|corp|plc|pvt ltd|pte ltd)\.?$", re.I)
_ADDRESS_START = re.compile(
    r"^(no\.?\s*\d|\d|plot|room|unit|building|block|floor|suite|p\.?o\.?)", re.I
)

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DMON = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$")
_LONG = re.compile(r"^([A-Za-z]{3,9})\.? (\d{1,2}), (\d{4})$")
_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_ANY_SLASH = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})/(\d{4})(?![\d/])")


def clean_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", _CONTROL.sub("", value))
    return " ".join(text.split())[:MAX_TEXT]


def detect_date_order(text: str, hint: DateOrder | None = None) -> tuple[DateOrder, bool]:
    """(order, assumed) for `dd/mm/yyyy`-style dates. Evidence from the whole document: a first
    component above 12 means day-first, a second above 12 month-first; otherwise `hint` (a sibling
    document of the same pack) or the Bangladesh/China default day-first, flagged as assumed."""
    dmy = mdy = False
    for a, b, _ in _ANY_SLASH.findall(text):
        if int(a) > 12:
            dmy = True
        if int(b) > 12:
            mdy = True
    if dmy and not mdy:
        return "DMY", False
    if mdy and not dmy:
        return "MDY", False
    return (hint or "DMY"), True


def parse_date(value: str, order: DateOrder = "DMY") -> date | None:
    v = value.strip()
    try:
        if m := _ISO.match(v):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if m := _DMON.match(v):
            return date(int(m[3]), _MONTHS[m[2].lower()[:3]], int(m[1]))
        if m := _LONG.match(v):
            return date(int(m[3]), _MONTHS[m[1].lower()[:3]], int(m[2]))
        if m := _SLASH.match(v):
            d, mo = (int(m[1]), int(m[2])) if order == "DMY" else (int(m[2]), int(m[1]))
            return date(int(m[3]), mo, d)
    except (ValueError, KeyError):
        return None
    return None


_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_number(text: str) -> Decimal | None:
    m = _NUM.search(text)
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def parse_money(text: str) -> tuple[str | None, Decimal | None]:
    """("USD", 9600.00) from "USD 9,600.00" (currency optional)."""
    m = re.match(r"^\s*([A-Za-z]{3})?\s*(-?\d[\d,]*(?:\.\d+)?)", text)
    if not m:
        return None, None
    return (m.group(1).upper() if m.group(1) else None), parse_number(m.group(2))


def split_party(value: str) -> tuple[str, str | None]:
    """ "Shaoxing Huaxin Textile Co., Ltd., No. 66 Jiangnan Road, ..." -> (name, address)."""
    parts = [p.strip() for p in value.split(",")]
    name = parts[0]
    i = 1
    while i < len(parts) and (_SUFFIX_TOKEN.match(parts[i]) and not _ADDRESS_START.match(parts[i])):
        name += ", " + parts[i]
        i += 1
    address = ", ".join(parts[i:]) or None
    return name, address


def title_doc_type(text: str) -> str | None:
    """Document type named by the title line, if any (e.g. to flag a mislabelled upload)."""
    for line in text.splitlines()[:8]:
        key = line.strip().upper()
        if key in _TITLES:
            return _TITLES[key]
    return None


@dataclass(slots=True)
class ParseResult:
    fields: DocFields
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    date_order: DateOrder = "DMY"
    date_order_assumed: bool = False
    raw: dict[str, str] = field(default_factory=dict)


def _collect(text: str, family: str) -> dict[str, str]:
    """Raw value per field name: first occurrence wins; wrapped lines are appended."""
    table = LABELS[family]
    out: dict[str, str] = {}
    current: str | None = None
    skip_row = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if skip_row:
            skip_row = False
            current = None
            continue
        if _TABLE_HEAD.match(line):
            skip_row, current = True, None
            continue
        if _FOOTER.match(line):
            current = None
            continue
        head, sep, rest = line.partition(":")
        label = head.strip().casefold()
        if sep and label in table:
            name = table[label]
            if name is None:
                current = None
            elif name in out:
                current = None  # repeated label: keep the first value
            else:
                out[name] = rest.strip()
                current = name
            continue
        if _SECTION.match(line):
            current = None
            continue
        if current in WRAPPABLE:
            out[current] = f"{out[current]} {line}"
    return out


def _text(raw: dict[str, str], name: str) -> str | None:
    value = clean_text(raw.get(name, ""))
    return value or None


def parse_document(
    text: str, doc_type: str, *, date_order_hint: DateOrder | None = None
) -> ParseResult:
    if doc_type not in FAMILY:
        raise ValueError(f"unsupported document type {doc_type}")
    family = FAMILY[doc_type]
    raw = _collect(text, family)
    order, assumed = detect_date_order(text, date_order_hint)
    warnings: list[str] = []
    data: dict[str, Any] = {"doc_type": doc_type}

    def bad(name: str) -> None:
        warnings.append(f"FIELD_INVALID:{name}")

    for name, value in raw.items():
        v = clean_text(value)
        if not v:
            continue
        if name in {"date", "production_complete", "est_ship_date", "eta", "on_board_date",
                    "issue_date"}:  # fmt: skip
            d = parse_date(v, order)
            if d is None:
                bad(name)
            else:
                data[name] = d
        elif name in {"quantity"}:
            n = parse_number(v)
            tail = re.sub(r"^-?\d[\d,]*(?:\.\d+)?\s*", "", v).strip()
            if n is None:
                bad(name)
            else:
                data["quantity"] = n
                if tail:
                    data["unit"] = tail.split()[0]
        elif name == "unit_price":
            cur, price = parse_money(v)
            if price is None:
                bad(name)
            else:
                data["unit_price"] = price
                if cur:
                    data["currency"] = cur
                m = re.search(r"\bper\s+(\S+)", v, re.I)
                if m and "unit" not in data:
                    data["unit"] = m.group(1)
        elif name == "total":
            cur, amount = parse_money(v)
            if amount is None:
                bad(name)
            else:
                data["total"] = amount
                if cur and "currency" not in data:
                    data["currency"] = cur
        elif name in {"net_weight_kg", "gross_weight_kg", "fx_usd_bdt"}:
            n = parse_number(v.split("/")[-1] if name == "fx_usd_bdt" else v)
            if n is None:
                bad(name)
            else:
                data[name] = n
        elif name in {"assessed_value_usd", "duty_usd", "assessed_value_bdt", "duty_bdt"}:
            _, amount = parse_money(v)
            if amount is None:
                bad(name)
            else:
                data[name] = amount
        elif name == "packages":
            m = re.match(r"^(\d[\d,]*)\s*(.*)$", v)
            if not m:
                bad(name)
            else:
                data["packages"] = int(m.group(1).replace(",", ""))
                if m.group(2):
                    data["package_type"] = m.group(2)[:60]
        elif name == "vessel_voyage":
            vessel, _, voyage = v.rpartition(" / ")
            if vessel and voyage:
                data["booked_vessel"], data["booked_voyage"] = vessel.strip(), voyage.strip()
            else:
                bad(name)
        elif name in PARTY_ADDRESS:
            party, address = split_party(v)
            data[name] = party
            if address:
                data[PARTY_ADDRESS[name]] = address
        elif name == "notify_party":
            data[name] = split_party(v)[0]
        elif name == "hs_code":
            data[name] = v
        else:
            data[name] = v
    model = FIELD_MODELS[doc_type]
    # Pydantic validates the types again; only keys the model knows are kept.
    known = {k: v for k, v in data.items() if k in model.model_fields}
    fields = model.model_validate(known)
    missing = [f for f in REQUIRED[doc_type] if getattr(fields, f, None) is None]
    return ParseResult(
        fields=fields,  # type: ignore[arg-type]
        warnings=warnings,
        missing=missing,
        date_order=order,
        date_order_assumed=assumed,
        raw=raw,
    )
