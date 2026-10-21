# ruff: noqa: F811  (fixtures imported from the API test conftest are used as arguments)
"""Each demo order set (create-order values + document pack) works end to end: the order is created
with the documented values, every file uploads, and no check fails or warns."""

import pytest
from fastapi.testclient import TestClient

from synthetic.form_samples import files
from synthetic.form_samples.people import ORDERS, Order
from tests.api.conftest import client, login, seeded_db  # noqa: F401  (fixtures)
from tests.api.deals_support import BRIGHTLINE, HUAXIN, as_user, confirmed, party_id
from tests.synthetic.test_form_samples import col, percents

pytestmark = pytest.mark.db

UPLOAD_ORDER = (
    ("PROFORMA_INVOICE", "1_proforma_invoice.pdf"),
    ("PRODUCTION_PHOTO", "2_production_photo_1.jpg"),
    ("PRODUCTION_PHOTO", "2_production_photo_2.jpg"),
    ("COMMERCIAL_INVOICE", "3_commercial_invoice.pdf"),
    ("PACKING_LIST", "4_packing_list.pdf"),
    ("BILL_OF_LADING", "5_bill_of_lading.pdf"),
    ("CERTIFICATE_OF_ORIGIN", "6_certificate_of_origin.pdf"),
    ("BILL_OF_ENTRY", "7_bill_of_entry.pdf"),
)


def create_payload(o: Order) -> dict[str, object]:
    code = HUAXIN if o.supplier_short == "Huaxin" else BRIGHTLINE
    return {
        "supplier_id": party_id(code),
        "title": o.title,
        "hs_code": o.hs_code,
        "quantity": o.quantity,
        "unit": o.unit,
        "unit_price": o.unit_price,
        "currency": "USD",
        "incoterm": "FOB",
        "port_of_loading": o.port_of_loading,
        "port_of_discharge": "Chittagong",
        "expected_sale_value": o.expected_sale_value,
        "costs": [
            {"kind": "FREIGHT", "amount": o.freight},
            {"kind": "INSURANCE", "amount": o.insurance},
            {"kind": "DUTY", "amount": o.duty},
            {"kind": "BANK_CHARGES", "amount": o.bank_charges},
        ],
    }


@pytest.mark.parametrize("order", ORDERS, ids=lambda o: f"order-{o.n}")
def test_order_set_creates_and_every_document_passes(client: TestClient, order: Order) -> None:
    buyer = login(client, "karim@demo.setu")
    res = buyer.post("/deals", json=create_payload(order))
    assert res.status_code == 201, res.text
    ref = res.json()["reference"]
    pack = files.order_files(order)
    for doc_type, name in UPLOAD_ORDER:
        mime = "image/jpeg" if name.endswith(".jpg") else "application/pdf"
        up = buyer.post(
            f"/deals/{ref}/documents",
            params={"wait": "true"},
            data={"doc_type": doc_type},
            files={"file": (name, pack[name], mime)},
        )
        assert up.status_code == 201, (name, up.text)
        doc_id = up.json()["document"]["id"]
        detail = buyer.get(f"/documents/{doc_id}").json()
        bad = [
            (f["check_code"], f["status"])
            for f in detail["findings"]
            if f["status"] in ("FAIL", "WARN")
        ]
        assert detail["check_status"] == "PASSED" and not bad, (order.n, name, bad)


@pytest.mark.parametrize("order", ORDERS, ids=lambda o: f"order-{o.n}")
def test_order_schedule_is_confirmed_and_first_tranche_funded(
    client: TestClient, order: Order
) -> None:
    buyer = login(client, "karim@demo.setu")
    res = buyer.post("/deals", json=create_payload(order))
    assert res.status_code == 201, res.text
    ref = res.json()["reference"]
    assert (
        buyer.post(f"/deals/{ref}/milestones/propose", json={"template": "30/60/10"}).status_code
        == 200
    )
    supplier = as_user("huaxin@demo.setu") if order.supplier_short == "Huaxin" else None
    confirmed(buyer, supplier, ref)
    amount = col("escrow-fund", order.n - 1)["Amount (USD)"]
    fund = buyer.post(f"/deals/{ref}/escrow/fund", json={"amount": amount})
    assert fund.status_code == 200, fund.text


@pytest.mark.parametrize("n", range(5))
def test_every_proposed_schedule_is_accepted(client: TestClient, n: int) -> None:
    buyer = login(client, "karim@demo.setu")
    res = buyer.post("/deals", json=create_payload(ORDERS[0]))
    assert res.status_code == 201, res.text
    body = percents(col("milestone-propose", n))
    prop = buyer.post(f"/deals/{res.json()['reference']}/milestones/propose", json=body)
    assert prop.status_code == 200, prop.text
