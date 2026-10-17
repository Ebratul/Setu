"""Code-side validation of extracted values, and the canonical invoice identity."""

import datetime as dt
from decimal import Decimal

import pytest

from app.forensics.canonical import canonical_invoice_hash
from app.forensics.validate import sanitise, validate_value


def test_invalid_values_become_none_with_a_warning() -> None:
    fields, warnings = sanitise(
        "COMMERCIAL_INVOICE",
        {
            "quantity": "-5",
            "unit_price": "0",
            "total": "1e40",
            "currency": "ZZZ",
            "hs_code": "not-a-code",
            "date": "1850-01-01",
            "seller": "  Huaxin \x07 Ltd  ",
            "bogus_field": "x",
        },
    )
    assert fields.quantity is None and fields.unit_price is None and fields.total is None
    assert fields.currency is None and fields.hs_code is None and fields.date is None
    assert fields.seller == "Huaxin Ltd"
    assert {
        f"FIELD_INVALID:{n}"
        for n in ("quantity", "unit_price", "total", "currency", "hs_code", "date")
    } == set(warnings)


def test_valid_values_are_normalised() -> None:
    fields, warnings = sanitise(
        "COMMERCIAL_INVOICE",
        {"quantity": "8,000", "unit_price": "1.20", "total": 9600, "currency": "rmb",
         "hs_code": "6006.22", "date": "2026-11-05"},
    )  # fmt: skip
    assert warnings == []
    assert fields.quantity == Decimal("8000") and fields.currency == "CNY"
    assert fields.date == dt.date(2026, 11, 5) and fields.hs_code == "6006.22"


@pytest.mark.parametrize(
    ("name", "value"),
    [("packages", "0"), ("packages", "x"), ("gross_weight_kg", "0"), ("eta", "2200-01-01")],
)
def test_rejects(name: str, value: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        validate_value(name, value)


def test_canonical_hash_ignores_case_spacing_and_formatting_but_not_the_amount() -> None:
    a = canonical_invoice_hash("Shaoxing  Huaxin Textile Co., Ltd.", "hx-pi-1", "9600", "usd")
    b = canonical_invoice_hash(
        "shaoxing huaxin textile co., ltd.", "HX-PI-1", Decimal("9600.00"), "USD"
    )
    assert a == b and len(a) == 64
    assert a != canonical_invoice_hash(
        "Shaoxing Huaxin Textile Co., Ltd.", "HX-PI-1", "9600.01", "USD"
    )
    assert a != canonical_invoice_hash(
        "Shaoxing Huaxin Textile Co., Ltd.", "HX-PI-2", "9600", "USD"
    )
