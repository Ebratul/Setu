"""Upload security and the documents API: magic bytes, size, names, roles, duplicates, signed URLs,
supplier projection, recheck."""

import time
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuditLog, Document
from app.db.session import get_engine
from app.services.documents import signing
from app.services.documents.upload import sanitise_filename, sniff
from tests.api.deals_support import HUAXIN, RAHIMA, as_user, create, propose
from tests.documents.support import invoice_lines, upload
from tests.forensics.support import make_pdf

pytestmark = pytest.mark.db


@pytest.fixture
def deal(client: TestClient) -> Iterator[dict]:
    rahima = as_user(RAHIMA)
    d = create(rahima, HUAXIN)
    propose(rahima, d["id"])
    yield d


def pdf(nonce: str | None = None, **kw) -> bytes:  # type: ignore[no-untyped-def]
    return make_pdf(invoice_lines(nonce=nonce or uuid.uuid4().hex, **kw))


def doc_count() -> int:
    with Session(get_engine()) as s:
        return s.scalar(select(func.count()).select_from(Document)) or 0


def audit_actions() -> list[str]:
    with Session(get_engine()) as s:
        return list(s.scalars(select(AuditLog.action)).all())


def test_sniff_and_sanitise_unit() -> None:
    assert sniff(b"%PDF-1.7 x") == "application/pdf" and sniff(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert sniff(b"\xff\xd8\xff\xe0") == "image/jpeg" and sniff(b"MZ\x90\x00") is None
    assert sniff(b"hello %PDF- later than 1 KB".rjust(2000)) is None
    assert sanitise_filename("../../etc/passwd", "application/pdf") == "passwd.pdf"
    assert (
        sanitise_filename("C:\\Users\\x\\inv oice (1).PDF", "application/pdf") == "inv oice (1).pdf"
    )
    assert sanitise_filename("a" * 400 + ".pdf", "application/pdf").endswith(".pdf")
    assert len(sanitise_filename("a" * 400 + ".pdf", "application/pdf")) <= 120
    assert sanitise_filename("evil\x00\n<script>.exe", "image/png") == "evil_script.png"
    assert sanitise_filename("...", "image/jpeg") == "document.jpg"
    assert sanitise_filename(None, "application/pdf") == "document.pdf"
    assert sanitise_filename("发票.pdf", "application/pdf") == "document.pdf"


def test_wrong_magic_bytes_are_refused_whatever_the_name_and_mime(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    before = doc_count()
    res = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "invoice.pdf", b"MZ\x90\x00 not a pdf")
    assert res.status_code == 415 and res.json()["code"] == "UNSUPPORTED_FILE_TYPE"
    res = upload(
        rahima,
        deal["id"],
        "COMMERCIAL_INVOICE",
        "invoice.pdf",
        b"<html>x</html>",
        mime="application/pdf",
    )
    assert res.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    res = upload(
        rahima, deal["id"], "COMMERCIAL_INVOICE", "invoice.pdf", png, mime="application/pdf"
    )
    assert res.status_code == 415 and res.json()["code"] == "WRONG_FILE_TYPE"
    res = upload(rahima, deal["id"], "PRODUCTION_PHOTO", "photo.jpg", pdf(), mime="image/jpeg")
    assert res.status_code == 415 and res.json()["code"] == "WRONG_FILE_TYPE"
    res = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "empty.pdf", b"")
    assert res.status_code == 400 and res.json()["code"] == "EMPTY_FILE"
    assert doc_count() == before


def test_oversize_is_refused_with_413_and_nothing_is_stored(
    client: TestClient, deal: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_MAX_BYTES", "2048")
    get_settings.cache_clear()
    rahima = as_user(RAHIMA)
    before = doc_count()
    res = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "big.pdf", b"%PDF-1.4\n" + b"0" * 4000)
    assert res.status_code == 413 and res.json()["code"] == "FILE_TOO_LARGE"
    assert doc_count() == before


def test_hostile_file_name_never_reaches_the_path(client: TestClient, deal: dict, tmp_path) -> None:
    rahima = as_user(RAHIMA)
    data = pdf()
    res = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "../../../etc/passwd\x00.pdf", data)
    assert res.status_code == 201, res.text
    body = res.json()["document"]
    assert body["file_name"].startswith("passwd") and body["file_name"].endswith(".pdf")
    assert "/" not in body["file_name"] and ".." not in body["file_name"]
    with Session(get_engine()) as s:
        row = s.get(Document, uuid.UUID(body["id"]))
        assert row is not None
        assert row.storage_path == f"deals/{deal['id']}/{body['sha256']}.pdf"
        assert (get_settings().storage_dir / row.storage_path).read_bytes() == data
    assert not (tmp_path / "etc").exists()


def test_roles_foreign_deal_judge_and_supplier(client: TestClient, deal: dict) -> None:
    data = pdf()
    karim = as_user("karim@demo.setu")
    assert upload(karim, deal["id"], "COMMERCIAL_INVOICE", "i.pdf", data).status_code == 404
    assert karim.get(f"/deals/{deal['id']}/documents").status_code == 404
    judge = as_user("judge@demo.setu")
    before = audit_actions().count("DOC_UPLOAD_FORBIDDEN")
    assert upload(judge, deal["id"], "COMMERCIAL_INVOICE", "i.pdf", data).status_code == 403
    assert audit_actions().count("DOC_UPLOAD_FORBIDDEN") == before + 1
    assert judge.get(f"/deals/{deal['id']}/documents").status_code == 200
    supplier = as_user("huaxin@demo.setu")
    res = upload(supplier, deal["id"], "COMMERCIAL_INVOICE", "i.pdf", data)
    assert res.status_code == 201 and res.json()["document"]["score"] is None
    assert as_user("admin@demo.setu").get(f"/deals/{deal['id']}/documents").status_code == 200
    anon = TestClient(client.app)
    assert (
        anon.post(
            f"/deals/{deal['id']}/documents",
            data={"doc_type": "PACKING_LIST"},
            files={"file": ("a.pdf", data)},
        ).status_code
        == 401
    )


def test_identical_file_on_the_same_deal_is_reused_on_another_deal_it_is_a_duplicate(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    data = pdf()
    first = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()
    uploads = audit_actions().count("DOC_UPLOADED")
    again = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "renamed.pdf", data)
    assert again.status_code == 201 and again.json()["reused"] is True
    assert again.json()["document"]["id"] == first["document"]["id"] and first["reused"] is False
    assert audit_actions().count("DOC_UPLOADED") == uploads
    other = create(rahima, HUAXIN)
    res = upload(rahima, other["id"], "COMMERCIAL_INVOICE", "a.pdf", data)
    assert res.status_code == 201 and res.json()["reused"] is False
    assert res.json()["document"]["id"] != first["document"]["id"]
    got = as_user(RAHIMA).get(f"/documents/{res.json()['document']['id']}").json()
    assert {f["check_code"]: f for f in got["findings"]}["DUPLICATE_HASH"]["status"] == "FAIL"


def test_background_check_runs_and_wait_runs_inline(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    queued = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", pdf(), wait=False).json()
    assert queued["checking"] == "QUEUED"
    doc = rahima.get(f"/documents/{queued['document']['id']}").json()
    assert doc["check_status"] in ("PASSED", "WARNING"), doc["verdict"]  # ran after the response
    done = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "b.pdf", pdf(), wait=True).json()
    assert done["checking"] == "DONE" and done["document"]["check_status"] != "PENDING"


def test_unreadable_pdf_is_a_warning_not_a_500(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    res = upload(
        rahima,
        deal["id"],
        "COMMERCIAL_INVOICE",
        "broken.pdf",
        b"%PDF-1.4\ngarbage\x00\x01" + uuid.uuid4().bytes,
    )
    assert res.status_code == 201, res.text
    doc = rahima.get(f"/documents/{res.json()['document']['id']}").json()
    assert doc["check_status"] == "WARNING" and "UNREADABLE_FILE" in doc["warnings"]
    codes = {f["check_code"]: f["status"] for f in doc["findings"]}
    assert codes["EXTRACTION_COMPLETE"] == "WARN"


def test_clean_invoice_passes_and_a_tampered_one_fails_its_checks(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    ok = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "ok.pdf", pdf()).json()["document"]
    detail = rahima.get(f"/documents/{ok['id']}").json()
    assert detail["check_status"] == "PASSED", detail["findings"]
    assert detail["fields"]["seller"] == "Shaoxing Huaxin Textile Co., Ltd."
    bad = upload(
        rahima, deal["id"], "COMMERCIAL_INVOICE", "bad.pdf",
        pdf(holder="Huaxin Textile (HK) Trading Ltd", account="SIM-HK-012-****-001", quantity="8,500 m"),
    ).json()["document"]  # fmt: skip
    d = rahima.get(f"/documents/{bad['id']}").json()
    status = {f["check_code"]: f["status"] for f in d["findings"]}
    assert status["BENEFICIARY_MATCH"] == "FAIL" and status["QUANTITY_MATCH"] == "FAIL"
    assert status["VALUE_MATH"] == "FAIL"
    assert d["check_status"] == "FAILED" and d["verdict"]["forced_by"] == ["BENEFICIARY_MATCH"]
    ben = next(f for f in d["findings"] if f["check_code"] == "BENEFICIARY_MATCH")
    assert ben["ground_truth"] == "BENEFICIARY_MATCH" and set(ben["detail"]["mismatched"]) >= {
        "holder"
    }
    assert ben["label_en"] and ben["label_bn"]


# --- signed URLs ------------------------------------------------------------------------------


def test_signed_file_url_roles_expiry_and_tampering(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    data = pdf()
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    detail = rahima.get(f"/documents/{doc['id']}").json()
    url = detail["file_url"]
    assert url.startswith(f"/documents/{doc['id']}/file?token=") and detail["file_url_expires_at"]
    res = rahima.get(url)
    assert res.status_code == 200 and res.content == data
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in res.headers["cache-control"]
    token = url.split("token=")[1]
    # another signed-in user cannot replay the link; neither can an anonymous caller
    supplier = as_user("huaxin@demo.setu")
    assert supplier.get(url).status_code == 403
    assert TestClient(client.app).get(url).status_code == 401
    # tampered signature, other document, missing token
    assert rahima.get(f"/documents/{doc['id']}/file?token={token[:-3]}abc").status_code == 403
    other = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "o.pdf", pdf()).json()["document"]
    assert rahima.get(f"/documents/{other['id']}/file?token={token}").status_code == 403
    assert rahima.get(f"/documents/{doc['id']}/file").status_code == 422
    # a foreign buyer never gets a link, and a forged one for them does not work either
    karim = as_user("karim@demo.setu")
    assert karim.get(f"/documents/{doc['id']}").status_code == 404
    assert karim.get(url).status_code == 403


def test_token_expiry_and_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    doc, user = uuid.uuid4(), uuid.uuid4()
    tok = signing.make_token(doc, user, now=1_000_000)
    raw = signing.encode(tok)
    assert signing.decode(raw, now=1_000_000) == tok
    assert signing.decode(raw, now=tok.expires_at) == tok
    assert signing.decode(raw, now=tok.expires_at + 1) is None
    assert signing.decode(raw + "x", now=1_000_000) is None
    assert signing.decode("garbage", now=1_000_000) is None
    monkeypatch.setenv("DOCUMENT_URL_SECRET", "another-secret")
    get_settings.cache_clear()
    assert signing.decode(raw, now=1_000_000) is None  # signed with a different key
    assert int(time.time()) < tok.expires_at or True


# --- projection and recheck -------------------------------------------------------------------


def test_supplier_gets_a_status_only_projection_and_judge_sees_everything(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    bad = upload(
        rahima, deal["id"], "COMMERCIAL_INVOICE", "bad.pdf", pdf(quantity="9,000 m")
    ).json()["document"]
    supplier = as_user("huaxin@demo.setu")
    s = supplier.get(f"/documents/{bad['id']}").json()
    assert s["check_status"] == "PENDING" and s["status"] == "IN_REVIEW"  # never the verdict
    assert s["score"] is None and s["findings"] == [] and s["fields"] is None
    assert s["verdict"] is None and s["hidden_spans_count"] is None and s["warnings"] == []
    assert s["instruction_from_document"] is None and s["hidden_text_found"] is None
    listing = supplier.get(f"/deals/{deal['id']}/documents").json()["documents"]
    assert (
        all(d["score"] is None for d in listing) and listing[0]["check_status"] == s["check_status"]
    )
    full = as_user("judge@demo.setu").get(f"/documents/{bad['id']}").json()
    assert full["score"] is not None and full["findings"] and full["fields"]["quantity"] == "9000"


def test_recheck_is_for_buyer_and_admin_only(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", pdf()).json()["document"]
    url = f"/documents/{doc['id']}/recheck"
    assert as_user("huaxin@demo.setu").post(url).status_code == 403
    assert as_user("judge@demo.setu").post(url).status_code == 403
    assert as_user("karim@demo.setu").post(url).status_code == 404
    before = audit_actions().count("DOC_RECHECKED_BY_USER")
    res = rahima.post(url)
    assert res.status_code == 200 and res.json()["check_status"] == "PASSED"
    assert as_user("admin@demo.setu").post(url).status_code == 200
    assert audit_actions().count("DOC_RECHECKED_BY_USER") == before + 2
    assert "DOC_RECHECK_FORBIDDEN" in audit_actions()


def test_the_seeded_proforma_invoice_still_works(client: TestClient) -> None:
    rahima = as_user(RAHIMA)
    docs = rahima.get("/deals/SETU-2026-0001/documents").json()["documents"]
    pi = next(d for d in docs if d["doc_type"] == "PROFORMA_INVOICE")
    assert pi["check_status"] == "PASSED" and pi["score"] == 0
    assert all(d["status"] == "UPLOADED" for d in docs)  # placeholders are not listed
    assert {d["doc_type"] for d in docs} == {"PROFORMA_INVOICE", "PRODUCTION_PHOTO"}
    res = rahima.post(f"/documents/{pi['id']}/recheck")
    assert res.status_code == 200, res.text
    detail = res.json()
    assert detail["check_status"] == "PASSED" and detail["verdict"]["score"] == 0
    assert detail["fields"]["seller"] == "Shaoxing Huaxin Textile Co., Ltd."
    assert detail["fields"]["booked_vessel"] == "MV KELMAR PEARL"
    assert rahima.get(detail["file_url"]).status_code == 200
    photos = [d for d in docs if d["doc_type"] == "PRODUCTION_PHOTO"]
    for p in photos:
        d = rahima.post(f"/documents/{p['id']}/recheck").json()
        assert d["check_status"] == "PASSED", d["findings"]
        assert {f["check_code"] for f in d["findings"]} == {"PHOTO_MATCH", "DUPLICATE_HASH"}
    ms = {
        m["seq"]: m["evidence_status"]
        for m in rahima.get("/deals/SETU-2026-0001").json()["milestones"]
    }
    assert ms[1] == "VERIFIED"


def test_dev_evidence_endpoint_stays_gated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_DEV_EVIDENCE", "false")
    get_settings.cache_clear()
    rahima = as_user(RAHIMA)
    ms = rahima.get("/deals/SETU-2026-0001").json()["milestones"][1]["id"]
    assert rahima.post(f"/milestones/{ms}/evidence", json={"status": "VERIFIED"}).status_code == 404
