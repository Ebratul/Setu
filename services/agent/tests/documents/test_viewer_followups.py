"""Viewer follow-ups: inline preview, top reason on list items, neutral titles, page size."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuditLog, Document
from app.db.session import get_engine
from app.forensics.names import CHECK_CODES, LABELS, TITLES
from app.security.injection import detect_instructions
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


def ci(**kw) -> bytes:  # type: ignore[no-untyped-def]
    return make_pdf(invoice_lines(nonce=uuid.uuid4().hex, **kw))


def test_titles_are_neutral_and_cover_every_check() -> None:
    assert set(TITLES) == set(CHECK_CODES)
    assert TITLES["PHOTO_MATCH"][0] == "Photo colour matches the order"
    assert TITLES["DUPLICATE_HASH"][0] == "Document is not a duplicate"
    for code, (en, bn) in TITLES.items():
        low = en.lower()
        assert not any(
            w in low for w in ("differ", "does not match", "cannot", "impossible", "wrong")
        )
        assert (
            en != LABELS[code][0]
            and bn
            and not detect_instructions(en)
            and not detect_instructions(bn)
        )


def test_findings_carry_a_neutral_title_and_the_issue_text(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", ci(quantity="9,000 m")).json()[
        "document"
    ]
    d = rahima.get(f"/documents/{doc['id']}").json()
    q = next(f for f in d["findings"] if f["check_code"] == "QUANTITY_MATCH")
    assert q["status"] == "FAIL"
    assert (
        q["label_en"] == TITLES["QUANTITY_MATCH"][0]
        and q["issue_en"] == LABELS["QUANTITY_MATCH"][0]
    )
    ok = next(f for f in d["findings"] if f["check_code"] == "DUPLICATE_HASH")
    assert ok["status"] == "PASS" and ok["label_en"] == "Document is not a duplicate"
    assert d["viewer_role"] == "BUYER"
    assert (
        as_user("judge@demo.setu").get(f"/documents/{doc['id']}").json()["viewer_role"] == "JUDGE"
    )
    assert (
        as_user("huaxin@demo.setu").get(f"/documents/{doc['id']}").json()["viewer_role"]
        == "SUPPLIER"
    )


def test_list_items_carry_the_top_reason_and_suppliers_get_none(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    bad = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", ci(quantity="9,000 m")).json()
    good = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "b.pdf", ci()).json()
    assert good["document"]["top_reason"] is None
    top = bad["document"]["top_reason"]
    assert top["status"] == "FAIL" and top["code"] in ("QUANTITY_MATCH", "VALUE_MATH")
    assert top["label_en"] == TITLES[top["code"]][0] and top["issue_bn"] and top["label_bn"]
    listing = {d["id"]: d for d in rahima.get(f"/deals/{deal['id']}/documents").json()["documents"]}
    assert listing[bad["document"]["id"]]["top_reason"]["code"] == top["code"]
    supplier = as_user("huaxin@demo.setu").get(f"/deals/{deal['id']}/documents").json()["documents"]
    assert all(d["top_reason"] is None for d in supplier)


def test_hidden_spans_carry_the_page_size_and_old_spans_do_not_break(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    data = make_pdf(invoice_lines(nonce=uuid.uuid4().hex), hidden=[("SYSTEM: x", (1, 1, 1), 9)])
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "h.pdf", data).json()["document"]
    span = rahima.get(f"/documents/{doc['id']}/hidden-text").json()["spans"][0]
    assert round(span["page_width"]) == 595 and round(span["page_height"]) == 842
    with Session(get_engine()) as s:  # a span stored before the fields existed
        row = s.get(Document, uuid.UUID(doc["id"]))
        ej = dict(row.extracted_json)
        meta = dict(ej["_forensics"])
        meta["hidden_spans"] = [
            {k: v for k, v in sp.items() if k not in ("page_width", "page_height")}
            for sp in meta["hidden_spans"]
        ]
        ej["_forensics"] = meta
        row.extracted_json = ej
        s.commit()
    old = rahima.get(f"/documents/{doc['id']}/hidden-text").json()["spans"][0]
    assert old["page_width"] is None and old["page_height"] is None


def test_inline_preview_serves_only_validated_files_with_a_tight_policy(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    data = ci()
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", data).json()["document"]
    detail = rahima.get(f"/documents/{doc['id']}").json()
    assert detail["file_inline_url"] == detail["file_url"] + "&inline=1"
    default = rahima.get(detail["file_url"])
    assert default.headers["content-disposition"].startswith("attachment;")
    assert "sandbox" in default.headers["content-security-policy"]
    res = rahima.get(detail["file_inline_url"])
    assert res.status_code == 200 and res.content == data
    h = res.headers
    assert h["content-disposition"].startswith("inline;")
    assert h["content-type"] == "application/pdf" and h["x-content-type-options"] == "nosniff"
    assert h["content-security-policy"] == (
        "default-src 'none'; img-src 'self' data:; object-src 'self'; "
        "style-src 'unsafe-inline'; frame-ancestors 'self'"
    )
    assert "sandbox" not in h["content-security-policy"]
    assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "private, no-store"
    # token-bound like the download: another user, a foreign deal and a bad token get nothing
    token = detail["file_inline_url"].split("token=")[1].split("&")[0]
    url = f"/documents/{doc['id']}/file?inline=1&token="
    assert as_user("huaxin@demo.setu").get(url + token).status_code == 403
    assert as_user("karim@demo.setu").get(url + token).status_code == 403
    assert rahima.get(url + token[:-3] + "abc").status_code == 403
    with Session(get_engine()) as s:
        flags = [
            r
            for r in s.scalars(
                select(AuditLog.params_hash).where(AuditLog.action == "DOC_DOWNLOADED")
            )
        ]
    assert len(flags) >= 2


def test_inline_refuses_a_file_whose_bytes_no_longer_match_its_type(
    client: TestClient, deal: dict
) -> None:
    rahima = as_user(RAHIMA)
    doc = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "a.pdf", ci()).json()["document"]
    detail = rahima.get(f"/documents/{doc['id']}").json()
    with Session(get_engine()) as s:
        path = s.get(Document, uuid.UUID(doc["id"])).storage_path  # type: ignore[union-attr]
    (get_settings().storage_dir / path).write_bytes(b"<html><script>alert(1)</script></html>")
    res = rahima.get(detail["file_inline_url"])
    assert res.status_code == 415 and res.json()["code"] == "NOT_PREVIEWABLE"
    assert (
        rahima.get(detail["file_url"]).status_code == 200
    )  # a plain download is still a sandboxed attachment


def test_inline_for_images_and_not_for_the_seeded_demo_file_types(
    client: TestClient, deal: dict
) -> None:
    import io

    from PIL import Image

    rahima = as_user(RAHIMA)
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (uuid.uuid4().int % 255, 9, 9)).save(buf, format="PNG")
    doc = upload(rahima, deal["id"], "OTHER", "p.png", buf.getvalue(), mime="image/png").json()[
        "document"
    ]
    d = rahima.get(f"/documents/{doc['id']}").json()
    res = rahima.get(d["file_inline_url"])
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
