"""Per-check unit tests over the pure check functions."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.forensics.checks import (
    Outcome,
    account_equal,
    hidden_text,
    instruction_scan,
    metadata_anomaly,
    photo_match,
    run_checks,
)
from app.forensics.context import DealContext, DocView, Pack, RegisteredAccount, Tolerances
from app.forensics.fields import (
    BillOfEntryFields,
    BillOfLadingFields,
    CertOfOriginFields,
    InvoiceFields,
    PackingListFields,
)
from app.forensics.pdf_text import HiddenSpan
from tests.forensics.support import analysed, synth_pack, tampered

D = Decimal


def outcomes(pack: Pack, ctx: DealContext, doc_type: str, **kw) -> dict[str, Outcome]:  # type: ignore[no-untyped-def]
    return {o.code: o for o in run_checks(pack.docs[doc_type], pack, ctx, **kw)}


def status(pack: Pack, ctx: DealContext) -> dict[tuple[str, str], str]:
    out = {}
    for t, view in pack.docs.items():
        for o in run_checks(view, pack, ctx):
            out[(t, o.code)] = o.status
    return out


def test_clean_pack_passes_everything() -> None:
    pack, ctx = analysed(synth_pack(2))
    bad = {k: v for k, v in status(pack, ctx).items() if v not in ("PASS", "SKIPPED")}
    assert bad == {}
    assert status(pack, ctx)[("BILL_OF_LADING", "VESSEL_VOYAGE_MATCH")] == "PASS"
    assert status(pack, ctx)[("BILL_OF_ENTRY", "DATE_LOGIC")] == "PASS"


@pytest.mark.parametrize(
    ("fraud", "doc", "code"),
    [
        ("QUANTITY_MISMATCH", "PACKING_LIST", "QUANTITY_MATCH"),
        ("VALUE_MISMATCH", "COMMERCIAL_INVOICE", "VALUE_MATCH"),
        ("VESSEL_DATE_MISMATCH", "BILL_OF_LADING", None),
        ("NAME_MISMATCH", "COMMERCIAL_INVOICE", "NAME_MATCH"),
        ("PRICE_OUTLIER", "COMMERCIAL_INVOICE", "PRICE_BAND"),
        ("ALTERED_BENEFICIARY", "COMMERCIAL_INVOICE", "BENEFICIARY_MATCH"),
        ("WRONG_PORT", "BILL_OF_LADING", "PORT_MATCH"),
        ("HS_CODE_MISMATCH", "CERTIFICATE_OF_ORIGIN", "HS_CODE_MATCH"),
    ],
)
@pytest.mark.parametrize("diff", ["obvious", "subtle"])
def test_each_fraud_type_trips_its_check(fraud: str, doc: str, code: str | None, diff: str) -> None:
    flagged = set()
    for index in range(4):
        pack, ctx = analysed(tampered(fraud, index, diff))
        got = status(pack, ctx)
        hits = {k for k, v in got.items() if v in ("FAIL", "WARN") and k[1] != "METADATA_ANOMALY"}
        assert hits, (fraud, diff, index)
        if code:
            assert any(k[1] == code for k in hits), (fraud, diff, index, hits)
        else:
            assert any(k[1] in ("VESSEL_VOYAGE_MATCH", "DATE_LOGIC") for k in hits)
        flagged |= hits
    assert flagged


def test_hidden_instruction_pack_trips_hidden_text_and_instruction_scan() -> None:
    pack, ctx = analysed(tampered("HIDDEN_INSTRUCTION", 1, "obvious"))
    got = status(pack, ctx)
    assert any(k[1] == "HIDDEN_TEXT" and v == "FAIL" for k, v in got.items())
    assert any(k[1] == "INSTRUCTION_SCAN" and v == "FAIL" for k, v in got.items())


# --- quantity ---------------------------------------------------------------------------------


def invoice(**kw) -> DocView:  # type: ignore[no-untyped-def]
    base = {"doc_type": "COMMERCIAL_INVOICE", "quantity": D("100"), "unit": "m"}
    return DocView("COMMERCIAL_INVOICE", InvoiceFields(**{**base, **kw}))


def packing(**kw) -> DocView:  # type: ignore[no-untyped-def]
    return DocView("PACKING_LIST", PackingListFields(**kw))


def test_quantity_tolerance_and_units() -> None:
    ctx = DealContext("D", quantity=D("100"), unit="m")
    pl = packing(quantity=D("103"), unit="m")
    pack = Pack(docs={"PACKING_LIST": pl})
    strict = {o.code: o for o in run_checks(pl, pack, ctx)}["QUANTITY_MATCH"]
    assert strict.status == "FAIL" and strict.detail["conflicts"][0]["diff_pct"] == "3.00"
    loose = {o.code: o for o in run_checks(pl, pack, ctx, tol=Tolerances(quantity_pct=D("5")))}[
        "QUANTITY_MATCH"
    ]
    assert loose.status == "PASS"
    metres = packing(quantity=D("100"), unit="metres")
    assert {o.code: o for o in run_checks(metres, Pack(docs={"PACKING_LIST": metres}), ctx)}[
        "QUANTITY_MATCH"
    ].status == "PASS"
    kg = packing(quantity=D("100"), unit="kg")
    got = {o.code: o for o in run_checks(kg, Pack(docs={"PACKING_LIST": kg}), ctx)}
    assert got["QUANTITY_MATCH"].status == "FAIL"


def test_quantity_without_a_reference_is_skipped_not_warned() -> None:
    pl = packing(quantity=D("100"), unit="m")
    got = {o.code: o for o in run_checks(pl, Pack(docs={"PACKING_LIST": pl}), DealContext("D"))}
    assert got["QUANTITY_MATCH"].status == "SKIPPED"


def test_packing_list_and_bl_weights_must_agree() -> None:
    ctx = DealContext("D", quantity=D("100"), unit="m")
    pl = packing(quantity=D("100"), unit="m", gross_weight_kg=D("50"), packages=5)
    bl = DocView(
        "BILL_OF_LADING",
        BillOfLadingFields(quantity=D("100"), unit="m", gross_weight_kg=D("55"), packages=5),
    )
    pack = Pack(docs={"PACKING_LIST": pl, "BILL_OF_LADING": bl})
    for view in (pl, bl):
        o = {x.code: x for x in run_checks(view, pack, ctx)}["QUANTITY_MATCH"]
        assert o.status == "FAIL" and o.detail["conflicts"][0]["field"] == "gross_weight_kg"


# --- value ------------------------------------------------------------------------------------


def test_value_math_and_match() -> None:
    ctx = DealContext("D", unit_price=D("1.20"), goods_value=D("9600.00"), currency="USD")
    ok = invoice(quantity=D("8000"), unit_price=D("1.20"), total=D("9600.00"), currency="USD")
    got = {o.code: o for o in run_checks(ok, Pack(docs={"COMMERCIAL_INVOICE": ok}), ctx)}
    assert got["VALUE_MATH"].status == "PASS" and got["VALUE_MATCH"].status == "PASS"
    off = invoice(quantity=D("8000"), unit_price=D("1.20"), total=D("9700.00"), currency="USD")
    got = {o.code: o for o in run_checks(off, Pack(docs={"COMMERCIAL_INVOICE": off}), ctx)}
    assert got["VALUE_MATH"].status == "FAIL" and got["VALUE_MATH"].detail["diff"] == "100.00"
    assert got["VALUE_MATCH"].status == "FAIL"
    cent = invoice(quantity=D("3"), unit_price=D("0.333"), total=D("1.00"), currency="USD")
    assert {o.code: o for o in run_checks(cent, Pack(docs={"COMMERCIAL_INVOICE": cent}), ctx)}[
        "VALUE_MATH"
    ].status == "PASS"  # 0.999 rounds to 1.00
    sneaky = invoice(quantity=D("8000"), unit_price=D("1.22"), total=D("9760.00"), currency="USD")
    got = {o.code: o for o in run_checks(sneaky, Pack(docs={"COMMERCIAL_INVOICE": sneaky}), ctx)}
    assert got["VALUE_MATH"].status == "PASS" and got["VALUE_MATCH"].status == "FAIL"
    eur = invoice(quantity=D("8000"), unit_price=D("1.20"), total=D("9600.00"), currency="EUR")
    assert {o.code: o for o in run_checks(eur, Pack(docs={"COMMERCIAL_INVOICE": eur}), ctx)}[
        "VALUE_MATCH"
    ].status == "FAIL"


def test_commercial_invoice_is_compared_with_the_proforma_when_the_deal_has_no_price() -> None:
    pi = DocView(
        "PROFORMA_INVOICE",
        InvoiceFields(doc_type="PROFORMA_INVOICE", unit_price=D("1.20"), total=D("9600.00")),
    )
    ci = invoice(unit_price=D("1.22"), total=D("9600.00"))
    pack = Pack(docs={"PROFORMA_INVOICE": pi, "COMMERCIAL_INVOICE": ci})
    o = {x.code: x for x in run_checks(ci, pack, DealContext("D"))}["VALUE_MATCH"]
    assert o.status == "FAIL" and o.detail["conflicts"][0]["against"] == "PROFORMA_INVOICE"


# --- names, beneficiary -----------------------------------------------------------------------


def test_name_match_is_exact_ignoring_case_and_spacing_otherwise_review_or_fail() -> None:
    ctx = DealContext("D", supplier_license_name="Shaoxing Huaxin Textile Co., Ltd.")

    def name(value: str) -> Outcome:
        v = invoice(seller=value)
        return {o.code: o for o in run_checks(v, Pack(docs={v.doc_type: v}), ctx)}["NAME_MATCH"]

    assert name("SHAOXING  HUAXIN textile co., ltd.").status == "PASS"
    assert name("Shaoxing Huaxin Textile Co. Ltd.").status == "WARN"  # punctuation only
    assert name("Shaoxing Huaxin Textiles Co., Ltd.").status == "WARN"  # plural
    assert name("Shaoxing Huaxin Textile Co., Ltd").status == "WARN"
    assert name("Shaoxing Huaxin Textille Co., Ltd.").status == "WARN"  # typo
    assert name("Huaxin Textiles Trading").status == "FAIL"
    assert name("Chen Wei").status == "FAIL"


def test_account_equal_handles_masks_on_either_side() -> None:
    assert account_equal("SIM-CN-6222-****-1188", "SIM-CN-6222-0400-1188")
    assert account_equal("SIM-CN-6222-0400-1188", "SIM-CN-6222-****-1188")
    assert account_equal("SIM-CN-6222-****-1188", "SIM-CN-6222-****-1188")
    assert not account_equal("SIM-CN-6222-****-1188", "SIM-CN-6222-0400-1189")
    assert not account_equal("SIM-CN-6222-****-1188", "SIM-HK-6222-0400-1188")
    assert not account_equal("SIM-CN-6222-0400-1188", "SIM-CN-6222-0401-1188")


def test_beneficiary_match_fields() -> None:
    reg = RegisteredAccount("Riverside Bank", "Huaxin Ltd.", "SIM-CN-6222-0400-1188")
    ctx = DealContext("D", registered_account=reg)

    def check(**kw) -> Outcome:  # type: ignore[no-untyped-def]
        v = invoice(**kw)
        return {o.code: o for o in run_checks(v, Pack(docs={v.doc_type: v}), ctx)}[
            "BENEFICIARY_MATCH"
        ]

    good = {"bank_name": "Riverside Bank", "bank_holder": "Huaxin Ltd.",
            "bank_account": "SIM-CN-6222-****-1188"}  # fmt: skip
    assert check(**good).status == "PASS"
    assert check(**{**good, "bank_holder": "Huaxin (HK) Trading Ltd"}).detail["mismatched"] == [
        "holder"
    ]
    assert check(**{**good, "bank_account": "SIM-CN-6222-****-1199"}).detail["mismatched"] == [
        "account"
    ]
    assert check(**{**good, "bank_name": "Victoria Bank"}).detail["mismatched"] == ["bank"]
    assert check().status == "WARN"  # no bank details at all
    assert check(bank_account="SIM-CN-6222-****-1188").status == "WARN"  # incomplete
    none = invoice(**good)
    assert {
        o.code: o for o in run_checks(none, Pack(docs={none.doc_type: none}), DealContext("D"))
    }["BENEFICIARY_MATCH"].status == "SKIPPED"


# --- vessel, dates ----------------------------------------------------------------------------


def bl(**kw) -> DocView:  # type: ignore[no-untyped-def]
    return DocView("BILL_OF_LADING", BillOfLadingFields(**kw))


def test_vessel_voyage_uses_the_deal_booking_else_the_proforma_schedule() -> None:
    ship = bl(vessel="MV KELMAR PEARL", voyage="026E")
    pi = DocView(
        "PROFORMA_INVOICE",
        InvoiceFields(
            doc_type="PROFORMA_INVOICE", booked_vessel="MV KELMAR PEARL", booked_voyage="026E"
        ),
    )
    pack = Pack(docs={"BILL_OF_LADING": ship, "PROFORMA_INVOICE": pi})
    assert {o.code: o for o in run_checks(ship, pack, DealContext("D"))}[
        "VESSEL_VOYAGE_MATCH"
    ].status == "PASS"
    wrong = bl(vessel="MV KELMAR PEARL", voyage="027E")
    pack = Pack(docs={"BILL_OF_LADING": wrong, "PROFORMA_INVOICE": pi})
    o = {x.code: x for x in run_checks(wrong, pack, DealContext("D"))}["VESSEL_VOYAGE_MATCH"]
    assert o.status == "FAIL" and o.detail["conflicts"][0]["field"] == "voyage"
    alone = Pack(docs={"BILL_OF_LADING": ship})
    assert {x.code: x for x in run_checks(ship, alone, DealContext("D"))}[
        "VESSEL_VOYAGE_MATCH"
    ].status == "SKIPPED"
    ctx = DealContext("D", booked_vessel="MV OTHER", booked_voyage="001")
    assert {x.code: x for x in run_checks(ship, alone, ctx)}["VESSEL_VOYAGE_MATCH"].status == "FAIL"


def test_date_logic_rules() -> None:
    base = date(2026, 10, 1)
    ctx = DealContext(
        "D", production_complete=base + timedelta(days=10), eta=base + timedelta(days=40)
    )

    def check(on_board: int, **others) -> Outcome:  # type: ignore[no-untyped-def]
        ship = bl(on_board_date=base + timedelta(days=on_board))
        docs = {"BILL_OF_LADING": ship, **others}
        return {o.code: o for o in run_checks(ship, Pack(docs=docs), ctx)}["DATE_LOGIC"]

    assert check(12).status == "PASS"
    assert check(9).detail["broken"][0]["rule"] == "ON_BOARD_AFTER_PRODUCTION"  # a day early
    assert check(33).status == "PASS"  # exactly seven days before ETA
    assert check(34).detail["broken"][0]["rule"] == "TRANSIT_BEFORE_ETA"
    ci = DocView(
        "COMMERCIAL_INVOICE",
        InvoiceFields(doc_type="COMMERCIAL_INVOICE", date=base + timedelta(days=20)),
    )
    assert check(12, COMMERCIAL_INVOICE=ci).detail["broken"][0]["rule"] == "CI_BEFORE_ON_BOARD"
    entry_early = DocView("BILL_OF_ENTRY", BillOfEntryFields(date=base + timedelta(days=39)))
    got = {
        o.code: o for o in run_checks(entry_early, Pack(docs={"BILL_OF_ENTRY": entry_early}), ctx)
    }
    assert got["DATE_LOGIC"].status == "FAIL"
    entry_ok = DocView("BILL_OF_ENTRY", BillOfEntryFields(date=base + timedelta(days=41)))
    got = {o.code: o for o in run_checks(entry_ok, Pack(docs={"BILL_OF_ENTRY": entry_ok}), ctx)}
    assert got["DATE_LOGIC"].status == "PASS"
    coo = DocView("CERTIFICATE_OF_ORIGIN", CertOfOriginFields(issue_date=base + timedelta(days=80)))
    ship = bl(on_board_date=base + timedelta(days=12))
    got = {
        o.code: o
        for o in run_checks(
            coo, Pack(docs={"CERTIFICATE_OF_ORIGIN": coo, "BILL_OF_LADING": ship}), ctx
        )
    }
    assert got["DATE_LOGIC"].status == "WARN"  # sensible-date rule is a review item, not a failure


# --- ports, HS, price -------------------------------------------------------------------------


def test_port_and_incoterm_match() -> None:
    ctx = DealContext(
        "D", incoterm="FOB Ningbo", port_of_loading="Ningbo", port_of_discharge="Chittagong"
    )
    ship = bl(port_of_loading="Ningbo", port_of_discharge="Chattogram")
    assert {o.code: o for o in run_checks(ship, Pack(docs={"BILL_OF_LADING": ship}), ctx)}[
        "PORT_MATCH"
    ].status == "PASS"
    wrong = bl(port_of_loading="Ningbo", port_of_discharge="Colombo")
    o = {x.code: x for x in run_checks(wrong, Pack(docs={"BILL_OF_LADING": wrong}), ctx)}[
        "PORT_MATCH"
    ]
    assert o.status == "FAIL" and o.detail["conflicts"][0]["found"] == "Colombo"
    inv = invoice(incoterm="CIF Ningbo", port_of_loading="Ningbo", port_of_discharge="Chittagong")
    assert {x.code: x for x in run_checks(inv, Pack(docs={inv.doc_type: inv}), ctx)}[
        "PORT_MATCH"
    ].status == "FAIL"
    bare = DealContext(
        "D", incoterm="FOB", port_of_loading="Ningbo", port_of_discharge="Chittagong"
    )
    inv = invoice(incoterm="FOB Ningbo")
    assert {x.code: x for x in run_checks(inv, Pack(docs={inv.doc_type: inv}), bare)}[
        "PORT_MATCH"
    ].status == "PASS"
    inv = invoice(incoterm="FOB Shanghai")
    assert {x.code: x for x in run_checks(inv, Pack(docs={inv.doc_type: inv}), bare)}[
        "PORT_MATCH"
    ].status == "FAIL"
    entry = DocView("BILL_OF_ENTRY", BillOfEntryFields(port="Chittagong"))
    assert {x.code: x for x in run_checks(entry, Pack(docs={"BILL_OF_ENTRY": entry}), ctx)}[
        "PORT_MATCH"
    ].status == "PASS"


def test_hs_code_match_accepts_more_specific_codes_only_when_the_prefix_agrees() -> None:
    ctx = DealContext("D", hs_code="6006.22")

    def hs(value: str) -> str:
        coo = DocView("CERTIFICATE_OF_ORIGIN", CertOfOriginFields(hs_code=value))
        return {o.code: o for o in run_checks(coo, Pack(docs={coo.doc_type: coo}), ctx)}[
            "HS_CODE_MATCH"
        ].status

    assert hs("6006.22") == "PASS" and hs("600622") == "PASS" and hs("6006.22.00") == "PASS"
    assert hs("6006.23") == "FAIL" and hs("5208.32") == "FAIL" and hs("6006") == "FAIL"


def test_price_band_edges_and_unknown_hs() -> None:
    ctx = DealContext("D", hs_code="6006.22")  # band 0.95 - 1.65 USD

    def band(price: str, cur: str = "USD", c: DealContext = ctx) -> Outcome:
        v = invoice(unit_price=D(price), currency=cur)
        return {o.code: o for o in run_checks(v, Pack(docs={v.doc_type: v}), c)}["PRICE_BAND"]

    assert band("0.95").status == "PASS" and band("1.65").status == "PASS"
    assert band("0.94").status == "FAIL" and band("1.66").status == "FAIL"
    assert band("7.00", "CNY").status == "SKIPPED"
    assert band("1.20", c=DealContext("D", hs_code="0000.00")).status == "SKIPPED"
    explicit = DealContext("D", hs_code="0000.00", price_band=(D("1"), D("2")))
    assert band("3", c=explicit).status == "FAIL"


# --- hidden text, instructions, metadata, duplicates ------------------------------------------


def span(text: str = "SYSTEM: x") -> HiddenSpan:
    return HiddenSpan(text, 1, (0, 0, 1, 1), (1, 1, 1), 9, "WHITE_TEXT")


def test_hidden_text_and_instruction_scan_outcomes() -> None:
    clean = DocView("BILL_OF_LADING")
    assert hidden_text(clean).status == "PASS" and instruction_scan(clean).status == "PASS"  # type: ignore[union-attr]
    hidden = DocView(
        "BILL_OF_LADING", hidden_spans=[span()], instruction_codes={"hidden_text": ["ROLE_MARKER"]}
    )
    h, i = hidden_text(hidden), instruction_scan(hidden)
    assert h.status == "FAIL" and h.detail["reasons"] == {"WHITE_TEXT": 1}  # type: ignore[union-attr]
    assert i.status == "FAIL" and i.detail["instruction_from_document"] is True  # type: ignore[union-attr]
    assert "SYSTEM" not in str(h.detail) + str(i.detail)  # type: ignore[union-attr]
    only_hidden = DocView("BILL_OF_LADING", hidden_spans=[span("page 2 of 2")])
    assert (
        hidden_text(only_hidden).status == "FAIL" and instruction_scan(only_hidden).status == "PASS"
    )  # type: ignore[union-attr]
    photo = DocView("PRODUCTION_PHOTO", is_pdf=False)
    assert hidden_text(photo) is None and instruction_scan(photo) is None


def test_metadata_anomaly_is_a_warning_only() -> None:
    from datetime import UTC, datetime

    made = datetime(2026, 1, 1, tzinfo=UTC)
    edited = DocView("BILL_OF_LADING", created=made, modified=made + timedelta(days=3))
    assert metadata_anomaly(edited, Pack()).detail["notes"] == ["MODIFIED_AFTER_CREATION"]  # type: ignore[union-attr]
    tool = DocView("BILL_OF_LADING", metadata={"Producer": "Adobe Photoshop 25"})
    assert metadata_anomaly(tool, Pack()).detail["notes"] == ["EDITING_TOOL"]  # type: ignore[union-attr]
    siblings = {
        t: DocView(t, metadata={"Producer": "ExporterERP"})
        for t in ("PACKING_LIST", "COMMERCIAL_INVOICE")
    }
    odd = DocView("BILL_OF_LADING", metadata={"Producer": "Other PDF Writer"})
    assert metadata_anomaly(odd, Pack(docs=siblings)).status == "WARN"  # type: ignore[union-attr]
    fine = DocView(
        "BILL_OF_LADING", created=made, modified=made, metadata={"Producer": "ExporterERP"}
    )
    assert metadata_anomaly(fine, Pack(docs=siblings)).status == "PASS"  # type: ignore[union-attr]


def test_duplicate_hash_outcome() -> None:
    v = DocView("COMMERCIAL_INVOICE")
    pack = Pack(docs={v.doc_type: v})
    new = {o.code: o for o in run_checks(v, pack, DealContext("D"), registry_status="NEW")}
    dup = {
        o.code: o
        for o in run_checks(
            v,
            pack,
            DealContext("D"),
            registry_status="DUPLICATE",
            registry_detail={"scope": "platform"},
        )
    }
    assert new["DUPLICATE_HASH"].status == "PASS"
    assert (
        dup["DUPLICATE_HASH"].status == "FAIL"
        and dup["DUPLICATE_HASH"].detail["scope"] == "platform"
    )


def test_extraction_complete_warns_when_required_fields_are_missing() -> None:
    v = DocView(
        "COMMERCIAL_INVOICE",
        InvoiceFields(doc_type="COMMERCIAL_INVOICE"),
        missing=["total", "seller"],
    )
    o = {x.code: x for x in run_checks(v, Pack(docs={v.doc_type: v}), DealContext("D"))}[
        "EXTRACTION_COMPLETE"
    ]
    assert o.status == "WARN" and o.detail["missing"] == ["seller", "total"]


def test_photo_match_colour_only() -> None:
    pi = DocView(
        "PROFORMA_INVOICE",
        InvoiceFields(
            doc_type="PROFORMA_INVOICE", goods_description="Jersey, width 160 cm, colour Navy Blue"
        ),
    )

    def photo(rgb: tuple[int, int, int]) -> Outcome:
        p = DocView("PRODUCTION_PHOTO", is_pdf=False, photo_colour=("x", rgb, 0))
        return photo_match(p, Pack(docs={"PROFORMA_INVOICE": pi}))  # type: ignore[return-value]

    assert photo((24, 43, 87)).status == "PASS" and photo((30, 50, 95)).status == "PASS"
    assert photo((110, 25, 38)).status == "FAIL"  # maroon swatch for a navy order
    assert photo((24, 43, 87)).detail["width_label"].startswith("not checked")
    no_spec = DocView(
        "PROFORMA_INVOICE", InvoiceFields(doc_type="PROFORMA_INVOICE", goods_description="Fabric")
    )
    p = DocView("PRODUCTION_PHOTO", is_pdf=False, photo_colour=("x", (1, 2, 3), 0))
    assert photo_match(p, Pack(docs={"PROFORMA_INVOICE": no_spec})).status == "SKIPPED"  # type: ignore[union-attr]


def test_checks_are_deterministic() -> None:
    pack, ctx = analysed(tampered("QUANTITY_MISMATCH", 3, "subtle"))
    first = status(pack, ctx)
    random.seed(1)
    assert status(pack, ctx) == first
