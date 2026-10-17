"""TC-02: the clean demo pack passes every check and verifies the shipment milestone."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Milestone
from app.db.session import get_engine
from tests.api.conftest import login
from tests.documents.support import DEAL, upload

pytestmark = pytest.mark.db


def evidence(client: TestClient) -> dict[int, str]:
    deal = client.get(f"/deals/{DEAL}").json()
    return {m["seq"]: m["evidence_status"] for m in deal["milestones"]}


def test_clean_pack_passes_and_verifies_m2(client: TestClient) -> None:
    rahima = login(client, "rahima@demo.setu")
    assert evidence(rahima)[2] == "PENDING"
    results = {}
    for doc_type, name in (
        ("COMMERCIAL_INVOICE", "commercial_invoice.pdf"),
        ("PACKING_LIST", "packing_list.pdf"),
    ):
        res = upload(rahima, DEAL, doc_type, name)
        assert res.status_code == 201, res.text
        results[doc_type] = res.json()
        assert evidence(rahima)[2] == "PENDING"  # not all three yet
    res = upload(rahima, DEAL, "BILL_OF_LADING", "bill_of_lading_clean.pdf")
    assert res.status_code == 201, res.text
    results["BILL_OF_LADING"] = res.json()
    assert evidence(rahima)[2] == "VERIFIED"
    for doc_type, body in results.items():
        assert body["checking"] == "DONE", doc_type
        detail = rahima.get(f"/documents/{body['document']['id']}").json()
        assert detail["check_status"] == "PASSED", (doc_type, detail["verdict"])
        bad = [f["check_code"] for f in detail["findings"] if f["status"] in ("FAIL", "WARN")]
        assert bad == [], (doc_type, bad)
        assert detail["verdict"]["score"] == 0
    # the seeded proforma invoice is re-checked as a sibling and still passes
    with Session(get_engine()) as s:
        pi = s.scalars(select(Document).where(Document.key.like("%proforma-invoice"))).one()
        assert pi.check_status.value == "PASSED"
        m2 = s.scalars(select(Milestone).where(Milestone.seq == 2)).first()
        assert m2 is not None
