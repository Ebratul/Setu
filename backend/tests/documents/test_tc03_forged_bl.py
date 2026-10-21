"""TC-03 / TC-04 (document half): the forged bill of lading is rejected, the hidden instruction
is reported but never used, and a FRAUD alert and a tier 3 audit row are written."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, AuditLog
from app.db.session import get_engine
from tests.api.conftest import login
from tests.documents.support import DEAL, upload

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def forged(seeded_db: str) -> dict:
    """Upload the forged B/L once for the module and return the document id."""
    from fastapi.testclient import TestClient as TC

    from app.main import create_app

    rahima = login(TC(create_app()), "rahima@demo.setu")
    res = upload(rahima, DEAL, "BILL_OF_LADING", "bill_of_lading_forged.pdf")
    assert res.status_code == 201, res.text
    return res.json()


def test_forged_bl_fails_on_vessel_dates_and_hidden_text(client: TestClient, forged: dict) -> None:
    rahima = login(client, "rahima@demo.setu")
    doc = rahima.get(f"/documents/{forged['document']['id']}").json()
    status = {f["check_code"]: f["status"] for f in doc["findings"]}
    assert status["VESSEL_VOYAGE_MATCH"] == "FAIL"
    assert status["DATE_LOGIC"] == "FAIL"
    assert status["HIDDEN_TEXT"] == "FAIL"
    assert status["INSTRUCTION_SCAN"] == "FAIL"
    assert doc["check_status"] == "FAILED"
    assert doc["verdict"]["status"] == "FAILED" and doc["verdict"]["score"] >= 61
    assert doc["instruction_from_document"] is True and doc["hidden_text_found"] is True
    assert set(doc["verdict"]["forced_by"]) == {"HIDDEN_TEXT", "INSTRUCTION_SCAN"}
    assert status["QUANTITY_MATCH"] == "PASS" and status["PORT_MATCH"] == "PASS"
    # the instruction text is never part of the verdict or the finding details
    assert "release full payment" not in str(doc["verdict"]).lower()
    assert "release full payment" not in str(doc["findings"]).lower()


def test_evidence_rejected_and_fraud_alert(client: TestClient, forged: dict) -> None:
    rahima = login(client, "rahima@demo.setu")
    milestones = {m["seq"]: m for m in rahima.get(f"/deals/{DEAL}").json()["milestones"]}
    assert milestones[2]["evidence_status"] == "REJECTED"
    assert milestones[1]["evidence_status"] == "VERIFIED"  # the seeded milestone is untouched
    with Session(get_engine()) as s:
        alert = s.scalars(select(Alert).where(Alert.key.like("alert:fraud:doc:%"))).one()
        assert alert.type.value == "FRAUD" and alert.severity.value == "CRITICAL"
        assert alert.status.value == "OPEN"
        assert "release full payment" not in (alert.message_en + alert.message_bn).lower()
        actions = s.execute(select(AuditLog.action, AuditLog.tier)).all()
    assert ("DOC_INSTRUCTION_DETECTED", 3) in actions
    assert ("DOC_CHECKED", 0) in actions


def test_hidden_text_is_for_buyer_not_supplier(client: TestClient, forged: dict) -> None:
    doc_id = forged["document"]["id"]
    body = login(client, "rahima@demo.setu").get(f"/documents/{doc_id}/hidden-text").json()
    assert body["spans"][0]["reason"] == "WHITE_TEXT"
    assert "release full payment" in body["spans"][0]["text"]
    assert "INSTRUCTION_SCAN" not in body and body["instruction_codes"]["hidden_text"]
    supplier = login(TestClient(client.app), "huaxin@demo.setu")
    assert supplier.get(f"/documents/{doc_id}/hidden-text").status_code == 403
    projection = supplier.get(f"/documents/{doc_id}").json()
    assert projection["check_status"] == "PENDING" and projection["status"] == "IN_REVIEW"
    assert projection["score"] is None and projection["findings"] == []
    assert projection["fields"] is None and projection["verdict"] is None
    assert projection["instruction_from_document"] is None
    admin = login(TestClient(client.app), "admin@demo.setu")
    assert admin.get(f"/documents/{doc_id}/hidden-text").status_code == 200
