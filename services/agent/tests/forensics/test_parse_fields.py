"""Deterministic field parser: layout variations, date formats and day-first ambiguity."""

from datetime import date
from decimal import Decimal

import pytest

from app.forensics.analyze import analyze_pdf
from app.forensics.parse_fields import (
    detect_date_order,
    parse_date,
    parse_document,
    parse_money,
    parse_number,
    split_party,
)
from synthetic.render_pdf import render_document
from tests.forensics.support import synth_pack

FORMATS = ["%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%B %d, %Y"]


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("font", ["helvetica", "times", "courier"])
def test_every_document_type_round_trips_for_each_date_format_and_font(fmt: str, font: str) -> None:
    pack = synth_pack(3)
    pack.style = pack.style.model_copy(update={"date_fmt": fmt, "font": font})
    for i, (_, doc) in enumerate(pack.pdf_docs()):
        got = analyze_pdf(render_document(doc, pack.style, i), doc.doc_type)
        f = got.view.fields
        assert f is not None and got.view.missing == [], (doc.doc_type, got.view.missing)
        if doc.doc_type in ("PROFORMA_INVOICE", "COMMERCIAL_INVOICE"):
            assert (f.invoice_no, f.date, f.quantity, f.unit_price, f.total) == (
                doc.invoice_no, doc.date, doc.quantity, doc.unit_price, doc.total,
            )  # fmt: skip
            assert f.seller == doc.seller.name and f.bank_account == doc.bank.account_masked
            assert f.bank_holder == doc.bank.holder_name and f.hs_code == doc.hs_code
        elif doc.doc_type == "BILL_OF_LADING":
            assert (f.vessel, f.voyage, f.on_board_date) == (
                doc.vessel,
                doc.voyage,
                doc.on_board_date,
            )
            assert f.shipper == doc.shipper.name and f.gross_weight_kg == doc.gross_weight_kg
            assert f.packages == doc.packages and f.quantity == doc.quantity
        elif doc.doc_type == "PACKING_LIST":
            assert f.date == doc.date and f.net_weight_kg == doc.net_weight_kg
        elif doc.doc_type == "CERTIFICATE_OF_ORIGIN":
            assert f.issue_date == doc.issue_date and f.exporter == doc.exporter.name
        elif doc.doc_type == "BILL_OF_ENTRY":
            assert f.date == doc.date and f.port == doc.port


def test_schedule_dates_of_the_proforma_invoice() -> None:
    pack = synth_pack(5)
    doc = pack.proforma
    f = analyze_pdf(render_document(doc, pack.style, 0), "PROFORMA_INVOICE").view.fields
    assert doc.schedule is not None and f is not None
    assert (f.booked_vessel, f.booked_voyage) == (
        doc.schedule.booked_vessel, doc.schedule.booked_voyage
    )  # fmt: skip
    assert (f.production_complete, f.est_ship_date, f.eta) == (
        doc.schedule.production_complete, doc.schedule.est_ship_date, doc.schedule.eta
    )  # fmt: skip


def test_swapped_seller_buyer_blocks_and_shuffled_fields_do_not_confuse_labels() -> None:
    for index in range(12):  # layout variation is seeded per document: cover several
        pack = synth_pack(index)
        f = analyze_pdf(
            render_document(pack.invoice, pack.style, 1), "COMMERCIAL_INVOICE"
        ).view.fields
        assert f is not None
        assert f.seller == pack.invoice.seller.name and f.buyer == pack.invoice.buyer.name


def test_date_formats_and_invalid_dates() -> None:
    assert parse_date("2026-11-05") == date(2026, 11, 5)
    assert parse_date("05-Nov-2026") == date(2026, 11, 5)
    assert parse_date("November 05, 2026") == date(2026, 11, 5)
    assert parse_date("05/11/2026", "DMY") == date(2026, 11, 5)
    assert parse_date("05/11/2026", "MDY") == date(2026, 5, 11)
    assert parse_date("31/02/2026", "DMY") is None and parse_date("garbage") is None
    assert parse_date("2026-13-01") is None


def test_day_first_ambiguity_is_resolved_from_the_whole_document() -> None:
    # a 25th makes the whole document day-first, so 05/11 is 5 November
    assert detect_date_order("a 25/11/2026 b 05/11/2026") == ("DMY", False)
    # a 25 in the month slot proves month-first
    assert detect_date_order("a 11/25/2026 b 05/11/2026") == ("MDY", False)
    # nothing proves it: the default is day-first, flagged as assumed; a sibling's proof wins
    assert detect_date_order("05/11/2026 06/11/2026") == ("DMY", True)
    assert detect_date_order("05/11/2026 06/11/2026", hint="MDY") == ("MDY", True)
    text = (
        "Invoice date: 05/11/2026\nProduction completion: 25/11/2026\nEstimated arrival: 06/12/2026"
    )
    got = parse_document(text, "PROFORMA_INVOICE")
    assert got.fields.date == date(2026, 11, 5) and got.date_order == "DMY"
    assert not got.date_order_assumed
    month_first = parse_document(
        "Invoice date: 05/11/2026\nEstimated arrival: 11/25/2026", "PROFORMA_INVOICE"
    )
    assert month_first.fields.date == date(2026, 5, 11) and month_first.date_order == "MDY"
    assert month_first.fields.eta == date(2026, 11, 25)


def test_numbers_money_parties_and_wrapping() -> None:
    assert parse_number("8,000 m") == Decimal("8000") and parse_number("1,234,567.50") == Decimal(
        "1234567.50"
    )
    assert parse_money("USD 9,600.00") == ("USD", Decimal("9600.00"))
    assert parse_money("12.50") == (None, Decimal("12.50"))
    assert split_party("Shaoxing Huaxin Textile Co., Ltd., No. 66 Jiangnan Road, Shaoxing") == (
        "Shaoxing Huaxin Textile Co., Ltd.", "No. 66 Jiangnan Road, Shaoxing",
    )  # fmt: skip
    assert split_party("Huaxin Trading, Room 5, Hong Kong") == (
        "Huaxin Trading",
        "Room 5, Hong Kong",
    )
    text = (
        "Goods description: Dyed cotton jersey fabric, 180 gsm,\n"
        "width 160 cm, colour Navy Blue\n"
        "HS code: 6006.22\n"
        "Quantity: 8,000 m\n"
        "Total amount: USD 9,600.00\n"
        "Item HS code Quantity Unit price Amount\n"
        "Dyed cotton jersey fabric 6006.22 8,000 m 1.20 9,600.00\n"
    )
    f = parse_document(text, "COMMERCIAL_INVOICE").fields
    assert (
        f.goods_description == "Dyed cotton jersey fabric, 180 gsm, width 160 cm, colour Navy Blue"
    )
    assert f.total == Decimal("9600.00") and f.quantity == Decimal("8000") and f.unit == "m"


def test_garbage_values_become_none_with_a_warning() -> None:
    got = parse_document(
        "Quantity: lots\nInvoice date: someday\nTotal amount: USD x", "COMMERCIAL_INVOICE"
    )
    assert got.fields.quantity is None and got.fields.date is None and got.fields.total is None
    assert {"FIELD_INVALID:quantity", "FIELD_INVALID:date", "FIELD_INVALID:total"} <= set(
        got.warnings
    )
    assert "invoice_no" in got.missing


def test_hostile_values_are_cleaned_and_capped() -> None:
    got = parse_document("Seller: Evil\x07 Ltd" + "x" * 900, "COMMERCIAL_INVOICE")
    assert got.fields.seller is not None and "\x07" not in got.fields.seller
    assert len(got.fields.seller) <= 400
