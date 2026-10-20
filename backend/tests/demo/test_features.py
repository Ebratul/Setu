"""What the demo needed from the product: reject a document, the signed credit record, the demo
seed profile. Each runs on the real services in a sandbox."""

import pathlib
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.db import tenancy
from app.db.enums import ApprovalStatus, DocStatus
from app.db.models import ApprovalRequest, AuditLog, CreditRecord, Document
from app.db.session import batch_session
from app.demo import runner, sandbox
from app.seed_ids import PI_KEY, RAHIMA
from tests.demo.conftest import new_client

pytestmark = pytest.mark.db
DEMO = pathlib.Path(__file__).resolve().parents[3] / "data" / "demo" / "SETU-2026-0001"
REF = "SETU-2026-0001"


def login(c: Any, email: str) -> None:
    assert c.post("/auth/demo-login", json={"email": email}).status_code == 200


def upload(c: Any, name: str, doc_type: str) -> dict[str, Any]:
    r = c.post(
        f"/deals/{REF}/documents",
        params={"wait": "true"},
        data={"doc_type": doc_type},
        files={"file": (name, (DEMO / name).read_bytes(), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    return r.json()["document"]


def test_the_seed_names_the_runner_depends_on_still_match() -> None:
    from seed.documents import PI_KEY as SEED_PI
    from seed.parties import RAHIMA as SEED_RAHIMA

    assert (PI_KEY, RAHIMA) == (SEED_PI, SEED_RAHIMA)


def test_demo_profile_leaves_out_only_the_fake_email_tier3_request(client) -> None:  # type: ignore[no-untyped-def]
    from seed.alerts_approvals import approvals
    from seed.common import Ctx, default_ctx

    standard = {r["action"] for r in approvals(default_ctx())}
    demo = {r["action"] for r in approvals(default_ctx("demo"))}
    assert "CHANGE_BENEFICIARY" in standard and "CHANGE_BENEFICIARY" not in demo
    assert standard - {"CHANGE_BENEFICIARY"} == demo  # M1's Tier 2 stays
    assert Ctx(today=default_ctx().today).profile == "standard"
    client.post("/demo/sandbox", json={})
    login(client, "rahima@demo.setu")
    pending = client.get("/approvals", params={"status": "pending"}).json()["items"]
    assert [(p["action"], p["tier"]) for p in pending] == [("RELEASE_MILESTONE", 2)]


def test_reject_document_is_for_the_buyer_or_admin_and_is_audited(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/demo/sandbox", json={})
    login(client, "rahima@demo.setu")
    forged = upload(client, "bill_of_lading_forged.pdf", "BILL_OF_LADING")
    assert forged["check_status"] == "FAILED"

    login(client, "huaxin@demo.setu")  # the supplier cannot withdraw documents
    r = client.post(f"/documents/{forged['id']}/reject", json={"reason": "not mine to remove"})
    assert r.status_code in (403, 404)
    login(client, "karim@demo.setu")  # another buyer cannot even see the deal
    r = client.post(f"/documents/{forged['id']}/reject", json={"reason": "nope not allowed"})
    assert r.status_code == 404

    login(client, "rahima@demo.setu")
    assert client.post(f"/documents/{forged['id']}/reject", json={"reason": "x"}).status_code == 422
    ok = client.post(f"/documents/{forged['id']}/reject", json={"reason": "Forged bill of lading"})
    assert ok.status_code == 200 and ok.json()["status"] == "REJECTED"
    again = client.post(
        f"/documents/{forged['id']}/reject", json={"reason": "Forged bill of lading"}
    )
    assert again.status_code == 404  # already withdrawn

    sid = uuid.UUID(client.get("/demo/sandbox").json()["id"])
    info = sandbox.lookup(sid)
    with tenancy.use_schema(info.schema), batch_session() as db:
        doc = db.get(Document, uuid.UUID(forged["id"]))
        assert doc.status == DocStatus.REJECTED and doc.sha256  # kept on record, not deleted
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "DOC_REJECTED"))
    assert audit is not None and audit.tier == 2 and audit.payload["doc_type"] == "BILL_OF_LADING"
    assert "Forged bill of lading" in audit.payload["reason"]
    # a buyer's withdrawal never loosens a held verdict (only an admin may)
    detail = client.get(f"/deals/{REF}").json()
    assert next(m for m in detail["milestones"] if m["seq"] == 2)["evidence_status"] == "REJECTED"


def test_an_admin_withdrawing_the_last_file_clears_the_held_verdict(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/demo/sandbox", json={})
    login(client, "rahima@demo.setu")
    forged = upload(client, "bill_of_lading_forged.pdf", "BILL_OF_LADING")
    login(client, "admin@demo.setu")
    assert (
        client.post(f"/documents/{forged['id']}/reject", json={"reason": "Forged"}).status_code
        == 200
    )
    detail = client.get(f"/deals/{REF}").json()
    assert next(m for m in detail["milestones"] if m["seq"] == 2)["evidence_status"] == "PENDING"


def test_clean_evidence_verifies_after_a_withdrawal(client) -> None:  # type: ignore[no-untyped-def]
    """Forged B/L withdrawn by an admin, clean set uploaded: evidence verified (admin re-check)."""
    client.post("/demo/sandbox", json={})
    login(client, "rahima@demo.setu")
    forged = upload(client, "bill_of_lading_forged.pdf", "BILL_OF_LADING")
    for name, kind in (
        ("packing_list.pdf", "PACKING_LIST"),
        ("commercial_invoice.pdf", "COMMERCIAL_INVOICE"),
    ):
        upload(client, name, kind)
    deal = client.get(f"/deals/{REF}").json()
    assert next(m for m in deal["milestones"] if m["seq"] == 2)["evidence_status"] == "REJECTED"
    login(client, "admin@demo.setu")
    assert (
        client.post(f"/documents/{forged['id']}/reject", json={"reason": "Forged"}).status_code
        == 200
    )
    login(client, "rahima@demo.setu")
    clean = upload(client, "bill_of_lading_clean.pdf", "BILL_OF_LADING")
    assert clean["check_status"] == "PASSED"
    login(client, "admin@demo.setu")
    assert client.post(f"/documents/{clean['id']}/recheck").status_code == 200
    login(client, "rahima@demo.setu")
    deal = client.get(f"/deals/{REF}").json()
    assert next(m for m in deal["milestones"] if m["seq"] == 2)["evidence_status"] == "VERIFIED"


@pytest.fixture(scope="module")
def completed(demo_db: str):  # type: ignore[no-untyped-def]
    from app.demo.script import load_script
    from app.main import create_app

    c = new_client(create_app())
    c.post("/demo/sandbox", json={})
    for n, k in load_script().scene_ids():
        assert c.post(f"/demo/run/scenes/{n}/{k}/run").status_code == 200
    yield c
    c.delete("/demo/sandbox")


def test_completion_issues_one_signed_credit_record(completed) -> None:  # type: ignore[no-untyped-def]
    c = completed
    login(c, "rahima@demo.setu")
    r = c.get(f"/credit-records/{REF}")
    assert r.status_code == 200
    rec = r.json()
    assert rec["verified"] and rec["hash_ok"] and rec["signature_ok"] and rec["simulated"] is True
    p = rec["payload"]
    assert p["record_type"] == "setu.completed_deal.v1" and p["deal_ref"] == REF
    assert (p["amount"], p["currency"], p["on_time"], p["disputes"]) == ("9600.00", "USD", True, 0)
    assert p["milestones"] == ["2880.00", "5760.00", "960.00"]
    kinds = {e["doc_type"] for e in p["evidence"]}
    assert {"PROFORMA_INVOICE", "BILL_OF_LADING", "PACKING_LIST", "BILL_OF_ENTRY"} <= kinds
    assert "BEGIN PUBLIC KEY" in rec["public_key_pem"]
    # the same record by id, and from the supplier's side
    assert c.get(f"/credit-records/{rec['deal_ref']}").json()["id"] == rec["id"]
    login(c, "huaxin@demo.setu")
    assert c.get(f"/credit-records/{REF}").json()["verified"] is True
    # exactly one record, one audit row
    sid = uuid.UUID(c.get("/demo/sandbox").json()["id"])
    with tenancy.use_schema(sandbox.lookup(sid).schema), batch_session() as db:
        issued = [
            a
            for a in db.scalars(select(AuditLog).where(AuditLog.action == "CREDIT_RECORD_ISSUED"))
            if a.payload.get("deal_ref") == REF
        ]
        rows = db.scalars(
            select(CreditRecord).where(CreditRecord.payload["deal_ref"].astext == REF)
        ).all()
    assert len(issued) == 1 and len(rows) == 1
    assert issued[0].payload["payload_hash"] == rec["payload_hash"]


def test_credit_record_verification_catches_tampering_and_strangers_see_nothing(completed) -> None:  # type: ignore[no-untyped-def]
    c = completed
    login(c, "rahima@demo.setu")
    rec = c.get(f"/credit-records/{REF}").json()
    good = c.post(
        "/credit-records/verify", json={"payload": rec["payload"], "signature": rec["signature"]}
    )
    assert good.json()["verified"] is True and good.json()["payload_hash"] == rec["payload_hash"]
    forged = {**rec["payload"], "amount": "99999.00"}
    assert (
        c.post(
            "/credit-records/verify", json={"payload": forged, "signature": rec["signature"]}
        ).json()["verified"]
        is False
    )
    badsig = rec["signature"][:-4] + "0000"
    assert (
        c.post(
            "/credit-records/verify", json={"payload": rec["payload"], "signature": badsig}
        ).json()["verified"]
        is False
    )
    login(c, "karim@demo.setu")  # another buyer's view: the deal does not exist for them
    assert c.get(f"/credit-records/{REF}").status_code == 404
    login(c, "judge@demo.setu")
    assert c.get(f"/credit-records/{REF}").status_code == 200
    assert c.get("/credit-records/SETU-2026-0006").status_code == 404  # not completed: no record


def test_completion_does_not_issue_twice_and_a_modified_record_fails_its_own_check(
    completed,
) -> None:  # type: ignore[no-untyped-def]
    from app.services import credit_record

    c = completed
    sid = uuid.UUID(c.get("/demo/sandbox").json()["id"])
    with tenancy.use_schema(sandbox.lookup(sid).schema), batch_session() as db:
        row = db.scalars(
            select(CreditRecord).where(CreditRecord.payload["deal_ref"].astext == REF)
        ).one()
        assert credit_record.verify(row) == (True, True)
        row.payload = {**row.payload, "on_time": False}
        assert credit_record.verify(row) == (False, False)
        db.rollback()


def test_completed_scenes_left_no_open_approval_behind(completed) -> None:  # type: ignore[no-untyped-def]
    sid = uuid.UUID(completed.get("/demo/sandbox").json()["id"])
    with tenancy.use_schema(sandbox.lookup(sid).schema), batch_session() as db:
        open_ = db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.status == ApprovalStatus.PENDING)
        ).all()
    assert open_ == []  # M1 executed, the Tier 3 request was cancelled


def test_scene_runner_reads_ids_from_the_sandbox_not_from_the_shared_data(client) -> None:  # type: ignore[no-untyped-def]
    client.post("/demo/sandbox", json={})
    sid = uuid.UUID(client.get("/demo/sandbox").json()["id"])
    with sandbox.acting_in(sid):
        static = runner.static_vars()
    assert static["deal"]["ref"] == REF and len(static["m2"]["id"]) == 36
    assert static["huaxin"]["id"] != static["huameng"]["id"]
