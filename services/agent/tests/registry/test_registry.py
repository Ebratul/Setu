"""FR-6.2 / SR-6 / TC-05: the hash registry. Lender B is protected from the invoice Lender A
already holds; a re-saved copy is caught; the same deal re-using its own document is not."""

import hashlib
import json
import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.registry import ToolContext, default_registry
from app.auth.deps import to_current
from app.db.enums import AlertStatus, AlertType, DocType, RegistryPurpose, RegistryStatus
from app.db.models import Alert, Deal, Document, HashRegistry, Party, User
from app.db.session import batch_session, get_engine
from app.services import hash_registry as hr
from app.services.documents import release_facts
from tests.api.deals_support import ADMIN, HUAXIN, JUDGE, RAHIMA, as_user, create, propose
from tests.documents.support import DEAL, demo_bytes, invoice_lines, upload
from tests.forensics.support import make_pdf

pytestmark = pytest.mark.db

LENDER_A, LENDER_B = "meghna-commercial-bank", "setu-partner-finance"
PREFINANCED = "prefinanced_invoice.pdf"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check(who: str, **body: Any) -> dict[str, Any]:
    res = as_user(who).post("/registry/lender-check", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def fresh_deal(who: str = RAHIMA) -> dict[str, Any]:
    d = create(as_user(who), HUAXIN)
    propose(as_user(who), d["id"])
    return d


def new_ci(**kw: Any) -> bytes:
    return make_pdf(invoice_lines(nonce=uuid.uuid4().hex, **kw))


def findings(doc_id: str) -> dict[str, Any]:
    got = as_user(RAHIMA).get(f"/documents/{doc_id}").json()
    return {f["check_code"]: f for f in got["findings"]} | {"_": got}


def entry(sha256: str, purpose: RegistryPurpose) -> HashRegistry | None:
    with batch_session() as s:
        return s.scalars(
            select(HashRegistry).where(
                HashRegistry.sha256 == sha256, HashRegistry.purpose == purpose
            )
        ).first()


# --- the lender-facing check (TC-05) ----------------------------------------------------------


def test_tc05_lender_b_gets_exact_duplicate_for_the_prefinanced_invoice() -> None:
    out = check(ADMIN, lender_id=LENDER_B, sha256=sha(demo_bytes(PREFINANCED)))
    assert out["result"] == "EXACT_DUPLICATE"
    assert out["already_registered_for"] == "FINANCING_COLLATERAL"
    assert out["held_by"] == "Lender A" and date.fromisoformat(out["registered_on"])


def test_tc05_file_variant_and_lender_a_asking_about_its_own_collateral() -> None:
    res = as_user(JUDGE).post(
        "/registry/lender-check/file",
        data={"lender_id": LENDER_B},
        files={"file": (PREFINANCED, demo_bytes(PREFINANCED), "application/pdf")},
    )
    assert res.status_code == 200 and res.json()["result"] == "EXACT_DUPLICATE"
    own = check(ADMIN, lender_id=LENDER_A, sha256=sha(demo_bytes(PREFINANCED)))
    assert own["result"] == "SAME_CONTEXT" and own["already_registered_for"] is None


def test_resaved_copy_is_a_near_duplicate_by_file_and_by_fields() -> None:
    resaved = demo_bytes("proforma_invoice_resaved.pdf")
    assert sha(resaved) != sha(demo_bytes(PREFINANCED))
    res = as_user(ADMIN).post(
        "/registry/lender-check/file",
        data={"lender_id": LENDER_B},
        files={"file": ("resaved.pdf", resaved, "application/pdf")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["result"] == "NEAR_DUPLICATE" and res.json()["held_by"] == "Lender A"
    fields = {
        "doc_type": "PROFORMA_INVOICE",
        "seller": "  SHAOXING HUAXIN textile Co., Ltd. ",
        "number": "hx-pi-2026-118",
        "total": "9600",
        "currency": "usd",
    }
    assert check(ADMIN, lender_id=LENDER_B, fields=fields)["result"] == "NEAR_DUPLICATE"
    other = {**fields, "number": "HX-PI-2026-999"}
    assert check(ADMIN, lender_id=LENDER_B, fields=other)["result"] == "NEW"


def test_unknown_document_is_new_and_the_check_registers_nothing() -> None:
    with batch_session() as s:
        before = s.scalar(select(func.count()).select_from(HashRegistry))
    assert check(ADMIN, lender_id=LENDER_B, sha256=sha(b"never seen"))["result"] == "NEW"
    with batch_session() as s:
        assert s.scalar(select(func.count()).select_from(HashRegistry)) == before


def test_lender_check_exposes_nothing_but_the_minimum() -> None:
    out = check(ADMIN, lender_id=LENDER_B, sha256=sha(demo_bytes(PREFINANCED)))
    assert set(out) <= {"simulated", "result", "already_registered_for", "registered_on", "held_by"}
    text = json.dumps(out).lower()
    for leak in ("rahima", "huaxin", "9600", "1.20", DEAL.lower(), "hx-pi", "deal"):
        assert leak not in text


def test_lender_check_input_rules() -> None:
    rahima = as_user(ADMIN)
    sha_ = sha(b"x")
    assert rahima.post("/registry/lender-check", json={"lender_id": LENDER_B}).status_code == 400
    both = {
        "lender_id": LENDER_B,
        "sha256": sha_,
        "fields": {"doc_type": "BILL_OF_LADING", "seller": "a", "number": "b"},
    }
    assert rahima.post("/registry/lender-check", json=both).status_code == 400
    assert (
        rahima.post(
            "/registry/lender-check", json={"lender_id": "nobody", "sha256": sha_}
        ).status_code
        == 404
    )
    assert (
        rahima.post(
            "/registry/lender-check", json={"lender_id": "shaoxing-huaxin", "sha256": sha_}
        ).status_code
        == 404
    )
    assert (
        rahima.post(
            "/registry/lender-check", json={"lender_id": LENDER_B, "sha256": "zz"}
        ).status_code
        == 422
    )
    assert (
        as_user("huaxin@demo.setu")
        .post("/registry/lender-check", json={"lender_id": LENDER_B, "sha256": sha_})
        .status_code
        == 403
    )
    assert (
        TestClient(rahima.app)
        .post("/registry/lender-check", json={"lender_id": LENDER_B, "sha256": sha_})
        .status_code
        == 401
    )


# --- the upload pipeline ----------------------------------------------------------------------


def test_tc05_uploading_the_prefinanced_invoice_fails_with_fraud_alert_and_flag() -> None:
    d = fresh_deal()
    res = upload(as_user(RAHIMA), d["id"], "PROFORMA_INVOICE", PREFINANCED)
    assert res.status_code == 201, res.text
    doc_id = res.json()["document"]["id"]
    got = findings(doc_id)
    dup = got["DUPLICATE_HASH"]
    assert dup["status"] == "FAIL" and dup["detail"]["scope"] == "registry"
    assert dup["detail"]["result"] == "EXACT_DUPLICATE" and dup["detail"]["lender"] == "Lender A"
    assert got["_"]["check_status"] == "FAILED"
    with batch_session() as s:
        alert = s.scalars(select(Alert).where(Alert.key == f"alert:fraud:doc:{doc_id}")).one()
        assert alert.type == AlertType.FRAUD and alert.status == AlertStatus.OPEN
        deal = s.get(Deal, uuid.UUID(d["id"]))
        ms = (
            deal
            and s.scalars(
                select(Document.milestone_id).where(Document.id == uuid.UUID(doc_id))
            ).one()
        )
        assert release_facts.facts(s, uuid.UUID(d["id"]), ms).duplicate is True


def test_near_duplicate_upload_to_another_deal_fails() -> None:
    d = fresh_deal()
    res = upload(as_user(RAHIMA), d["id"], "PROFORMA_INVOICE", "proforma_invoice_resaved.pdf")
    got = findings(res.json()["document"]["id"])
    assert got["DUPLICATE_HASH"]["status"] == "FAIL"
    assert got["DUPLICATE_HASH"]["detail"]["result"] == "NEAR_DUPLICATE"


def test_same_file_on_the_same_deal_is_the_same_context_and_raises_no_alert() -> None:
    d = fresh_deal()
    rahima = as_user(RAHIMA)
    data = new_ci()
    first = upload(rahima, d["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    assert findings(first["id"])["DUPLICATE_HASH"]["status"] == "PASS"
    again = upload(rahima, d["id"], "COMMERCIAL_INVOICE", "renamed.pdf", data).json()
    assert again["reused"] is True and again["document"]["id"] == first["id"]
    rechecked = rahima.post(f"/documents/{first['id']}/recheck")
    assert rechecked.status_code == 200
    assert findings(first["id"])["DUPLICATE_HASH"]["status"] == "PASS"
    row = entry(sha(data), RegistryPurpose.ESCROW_EVIDENCE)
    assert row is not None and row.seen_count >= 2 and row.exact_hits == 0 and row.near_hits == 0
    with batch_session() as s:
        n = s.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.key == f"alert:fraud:doc:{first['id']}")
        )
        assert n == 0


def test_a_failed_document_does_not_hold_the_registry() -> None:
    rahima = as_user(RAHIMA)
    d1, d2 = fresh_deal(), fresh_deal()
    bad = make_pdf(invoice_lines(nonce=uuid.uuid4().hex, holder="Kowloon Trading Co."))
    doc = upload(rahima, d1["id"], "COMMERCIAL_INVOICE", "bad.pdf", bad).json()["document"]
    assert doc["check_status"] == "FAILED"
    assert entry(sha(bad), RegistryPurpose.ESCROW_EVIDENCE) is None
    again = upload(rahima, d2["id"], "COMMERCIAL_INVOICE", "bad.pdf", bad).json()["document"]
    assert findings(again["id"])["DUPLICATE_HASH"]["status"] == "PASS"


def test_released_entries_no_longer_block() -> None:
    rahima = as_user(RAHIMA)
    d1, d2, d3 = fresh_deal(), fresh_deal(), fresh_deal()
    data = new_ci()
    first = upload(rahima, d1["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    assert first["check_status"] == "PASSED"
    blocked = upload(rahima, d2["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    assert findings(blocked["id"])["DUPLICATE_HASH"]["status"] == "FAIL"
    with batch_session() as s:
        assert hr.release_for_deal(s, uuid.UUID(d1["id"])) == 1
        s.commit()
    row = entry(sha(data), RegistryPurpose.ESCROW_EVIDENCE)
    assert row is not None and row.status == RegistryStatus.RELEASED and row.released_at
    free = upload(rahima, d3["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    assert findings(free["id"])["DUPLICATE_HASH"]["status"] == "PASS"


def test_bill_of_lading_fingerprint_folds_case_and_spacing() -> None:
    from app.schemas.registry import SemanticFields
    from app.services import registry as registry_service

    doc = Document(
        doc_type=DocType.BILL_OF_LADING,
        sha256="b" * 64,
        extracted_json={
            "bl_no": "NGB123456",
            "shipper": "Shaoxing  Huaxin Textile",
            "vessel": "MV Sea Star",
        },
    )
    typed = SemanticFields(
        doc_type="BILL_OF_LADING",
        seller="shaoxing huaxin textile",
        number="ngb123456",
        vessel="mv  sea star",
    )
    assert hr.semantic_of(doc) == registry_service.subject_from_fields(typed).semantic
    other = SemanticFields(
        doc_type="BILL_OF_LADING", seller="shaoxing huaxin textile", number="NGB999"
    )
    assert hr.semantic_of(doc) != registry_service.subject_from_fields(other).semantic


# --- financing --------------------------------------------------------------------------------


def apply(who: str, deal_ref: str, option: str, amount: str = "5200.00") -> Any:
    return as_user(who).post(
        "/financing/applications",
        json={"deal_id": deal_ref, "option_id": option, "amount": amount, "mode": "order"},
    )


def test_financing_at_lender_b_with_the_prefinanced_invoice_is_blocked() -> None:
    before = entry(sha(demo_bytes("proforma_invoice.pdf")), RegistryPurpose.FINANCING_COLLATERAL)
    assert before is not None
    res = apply(RAHIMA, DEAL, "escrow-order-loan-setu-partner")
    assert res.status_code == 409 and res.json()["code"] == "INVOICE_ALREADY_FINANCED"
    assert "Lender A" in res.json()["detail"]
    after = entry(sha(demo_bytes("proforma_invoice.pdf")), RegistryPurpose.FINANCING_COLLATERAL)
    assert after is not None and after.exact_hits == before.exact_hits + 1
    with batch_session() as s:
        alert = s.scalars(select(Alert).where(Alert.key.like("alert:fraud:registry:%"))).first()
        assert (
            alert is not None and alert.type == AlertType.FRAUD and alert.status == AlertStatus.OPEN
        )
    m = as_user(RAHIMA).post("/financing/match", json={"deal_id": DEAL, "mode": "order"}).json()
    opt = next(o for o in m["options"] if o["code"] == "escrow-order-loan-setu-partner")
    assert opt["eligible"] is False and opt["registry_block"]["holder"] == "Lender A"
    assert opt["registry_block"]["reason_en"].startswith("Blocked: invoice already")
    assert opt["registry_block"]["reason_bn"]


def test_financing_at_the_holding_lender_is_allowed() -> None:
    res = apply(RAHIMA, DEAL, "import-loan-meghna")
    assert res.status_code == 200, res.text


def test_a_fresh_invoice_is_registered_as_collateral_with_that_lender() -> None:
    rahima = as_user(RAHIMA)
    d = fresh_deal()
    data = new_ci()
    doc = upload(rahima, d["id"], "COMMERCIAL_INVOICE", "ci.pdf", data).json()["document"]
    assert doc["check_status"] == "PASSED"
    res = apply(RAHIMA, d["reference"], "import-loan-meghna", "3000.00")
    assert res.status_code == 200, res.text
    row = entry(sha(data), RegistryPurpose.FINANCING_COLLATERAL)
    assert row is not None and row.status == RegistryStatus.ACTIVE
    assert row.external_ref == res.json()["reference"]
    with batch_session() as s:
        lender = s.scalar(select(Party.id).where(hr.Party.code == LENDER_A))
        assert row.lender_party_id == lender
    # now Lender B is told the truth about it, and the escrow evidence of the same deal is fine
    assert check(ADMIN, lender_id=LENDER_B, sha256=sha(data))["result"] == "EXACT_DUPLICATE"
    assert findings(doc["id"])["DUPLICATE_HASH"]["status"] == "PASS"


def test_lender_check_by_document_raises_a_fraud_alert_on_its_deal() -> None:
    d = fresh_deal()
    doc = upload(as_user(RAHIMA), d["id"], "PROFORMA_INVOICE", PREFINANCED).json()["document"]
    out = check(RAHIMA, lender_id=LENDER_B, document_id=doc["id"])
    assert out["result"] == "EXACT_DUPLICATE"
    with batch_session() as s:
        alert = s.scalars(
            select(Alert).where(Alert.key.like(f"alert:fraud:registry:{d['id']}:%"))
        ).one()
        assert alert.status == AlertStatus.OPEN and "Duplicate financing blocked" in alert.title_en
        assert alert.message_bn


# --- admin, document box, tool ----------------------------------------------------------------


def test_admin_listing_stats_and_filters() -> None:
    check(ADMIN, lender_id=LENDER_B, sha256=sha(demo_bytes(PREFINANCED)))
    admin = as_user(ADMIN)
    listing = admin.get("/registry").json()
    assert listing["total"] >= 2
    row = next(
        i
        for i in listing["items"]
        if i["purpose"] == "FINANCING_COLLATERAL" and i["lender_name"] == "Lender A"
    )
    assert len(row["sha256_prefix"]) == 12 and row["exact_hits"] >= 1 and row["status"] == "ACTIVE"
    assert set(row) == {
        "id", "sha256_prefix", "semantic_prefix", "doc_type", "purpose", "lender_name", "deal_ref",
        "registered_on", "last_seen_at", "seen_count", "exact_hits", "near_hits", "status",
    }  # fmt: skip
    hit_only = admin.get("/registry", params={"result": "EXACT_DUPLICATE"}).json()
    assert hit_only["items"] and all(i["exact_hits"] > 0 for i in hit_only["items"])
    assert admin.get("/registry", params={"status": "RELEASED"}).json()["total"] >= 0
    stats = admin.get("/registry/stats").json()
    assert stats["entries"] == stats["active"] + stats["released"]
    assert stats["duplicates_blocked"] == stats["exact_blocked"] + stats["near_blocked"] >= 1
    assert as_user(JUDGE).get("/registry/stats").status_code == 200
    assert as_user(RAHIMA).get("/registry").status_code == 403
    assert as_user(RAHIMA).get("/registry/stats").status_code == 403


def test_document_registry_box_and_supplier_is_refused() -> None:
    rahima = as_user(RAHIMA)
    seeded_pi = rahima.get(f"/deals/{DEAL}/documents").json()["documents"]
    pi = next(x for x in seeded_pi if x["doc_type"] == "PROFORMA_INVOICE")
    box = rahima.get(f"/documents/{pi['id']}/registry").json()
    assert box["state"] == "REGISTERED" and box["purpose"] in (
        "ESCROW_EVIDENCE",
        "FINANCING_COLLATERAL",
    )
    d = fresh_deal()
    dup = upload(rahima, d["id"], "PROFORMA_INVOICE", PREFINANCED).json()["document"]
    box = rahima.get(f"/documents/{dup['id']}/registry").json()
    assert box["state"] == "DUPLICATE" and box["result"] == "EXACT_DUPLICATE"
    assert box["purpose"] == "FINANCING_COLLATERAL" and box["lender_name"] == "Lender A"
    assert as_user("huaxin@demo.setu").get(f"/documents/{pi['id']}/registry").status_code in (
        403,
        404,
    )
    assert as_user("karim@demo.setu").get(f"/documents/{pi['id']}/registry").status_code == 404


def test_registry_status_tool_is_tier0_and_check_documents_carries_the_flag() -> None:
    d = fresh_deal()
    dup = upload(as_user(RAHIMA), d["id"], "PROFORMA_INVOICE", PREFINANCED).json()["document"]
    with Session(get_engine()) as s:
        user = to_current(s.query(User).filter(User.email == RAHIMA).one())
        ctx = ToolContext(caller="llm", user=user, db=s, thread_id="t")
        reg = default_registry()
        out = reg.guard("registry_status", {"document_id": dup["id"]}, ctx)
        assert out.ok, out.error
        data = out.data["data"]
        assert data["state"] == "DUPLICATE" and data["holder"] == "Lender A"
        assert "REGISTRY_DUPLICATE" in data["security_flags"]
        assert out.data["explanation_en"] and out.data["explanation_bn"]
        chk = reg.guard("check_documents", {"deal_id": d["reference"]}, ctx)
        assert chk.ok and chk.data["data"]["documents"][0]["registry_state"] == "DUPLICATE"
        assert "REGISTRY_DUPLICATE" in chk.data["data"]["security_flags"]
        missing = reg.guard("registry_status", {"document_id": str(uuid.uuid4())}, ctx)
        assert not missing.ok
    assert reg.get("registry_status").max_tier == 0  # type: ignore[union-attr]


def test_audit_rows_for_register_and_hit() -> None:
    from app.db.models import AuditLog

    d = fresh_deal()
    upload(as_user(RAHIMA), d["id"], "COMMERCIAL_INVOICE", "ci.pdf", new_ci())
    upload(as_user(RAHIMA), fresh_deal()["id"], "PROFORMA_INVOICE", PREFINANCED)
    with batch_session() as s:
        actions = set(s.scalars(select(AuditLog.action)).all())
        tiers = dict(
            s.execute(
                select(AuditLog.action, AuditLog.tier).where(AuditLog.action.like("REGISTRY_%"))
            ).all()
        )
    assert {"REGISTRY_REGISTERED", "REGISTRY_DUPLICATE_HIT"} <= actions
    assert tiers["REGISTRY_DUPLICATE_HIT"] == 3 and tiers["REGISTRY_REGISTERED"] == 0


def test_pure_context_rules() -> None:
    """Conflict rules without HTTP: same deal other purpose is one context; other lender is not."""
    e = HashRegistry(
        sha256="a" * 64, purpose=RegistryPurpose.FINANCING_COLLATERAL, deal_id=uuid.uuid4(),
        lender_party_id=uuid.uuid4(), doc_type=DocType.PROFORMA_INVOICE,
        status=RegistryStatus.ACTIVE,
    )  # fmt: skip
    same_deal_evidence = hr.Context(RegistryPurpose.ESCROW_EVIDENCE, deal_id=e.deal_id)
    other_lender = hr.Context(RegistryPurpose.FINANCING_COLLATERAL, e.deal_id, uuid.uuid4())
    own_lender = hr.Context(RegistryPurpose.FINANCING_COLLATERAL, e.deal_id, e.lender_party_id)
    other_deal = hr.Context(RegistryPurpose.ESCROW_EVIDENCE, deal_id=uuid.uuid4())
    outside_same = hr.Context(RegistryPurpose.FINANCING_COLLATERAL, None, e.lender_party_id)
    outside_other = hr.Context(RegistryPurpose.FINANCING_COLLATERAL, None, uuid.uuid4())
    assert hr._same_context(e, same_deal_evidence)
    assert not hr._same_context(e, other_lender)
    assert hr._same_context(e, own_lender)
    assert not hr._same_context(e, other_deal)
    assert hr._same_context(e, outside_same)
    assert not hr._same_context(e, outside_other)


def test_buyers_may_only_check_their_own_documents_and_misses_are_audited() -> None:
    body = {"lender_id": LENDER_B, "sha256": sha(b"probe")}
    assert as_user(RAHIMA).post("/registry/lender-check", json=body).status_code == 403
    from app.db.models import AuditLog

    check(ADMIN, lender_id=LENDER_B, sha256=sha(b"probe"))
    with batch_session() as s:
        assert s.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "REGISTRY_LENDER_CHECK")
        )


def test_relabelled_invoice_is_still_a_near_duplicate() -> None:
    rahima = as_user(RAHIMA)
    d1, d2 = fresh_deal(), fresh_deal()
    upload(rahima, d1["id"], "COMMERCIAL_INVOICE", "a.pdf", new_ci(invoice_no="HX-REL-1"))
    other = new_ci(invoice_no="hx-rel-1")
    doc = upload(rahima, d2["id"], "PROFORMA_INVOICE", "b.pdf", other).json()["document"]
    f = findings(doc["id"])["DUPLICATE_HASH"]
    assert f["status"] == "FAIL" and f["detail"]["result"] == "NEAR_DUPLICATE"


def test_collateral_options_need_an_invoice_first() -> None:
    d = fresh_deal()
    res = apply(RAHIMA, d["reference"], "import-loan-meghna", "3000.00")
    assert res.status_code == 400 and res.json()["code"] == "INVOICE_REQUIRED"


def test_a_failed_document_keeps_its_registered_entry() -> None:
    rahima = as_user(RAHIMA)
    d = fresh_deal()
    data = new_ci()
    doc = upload(rahima, d["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    assert entry(sha(data), RegistryPurpose.ESCROW_EVIDENCE) is not None
    upload(rahima, d["id"], "COMMERCIAL_INVOICE", "bad.pdf", new_ci(holder="Kowloon Trading Co."))
    row = entry(sha(data), RegistryPurpose.ESCROW_EVIDENCE)
    assert row is not None and row.status == RegistryStatus.ACTIVE and doc
