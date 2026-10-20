"""Document checks record what the model would get (masked) and expose it as an X-ray."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

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


def test_document_xray_shows_masked_fields_and_real_text(client: TestClient, deal: dict) -> None:
    rahima = as_user(RAHIMA)
    pdf = make_pdf(invoice_lines(nonce=uuid.uuid4().hex, extra=["Contact: +8801711223344"]))
    res = upload(rahima, deal["id"], "COMMERCIAL_INVOICE", "invoice.pdf", pdf)
    assert res.status_code == 201, res.text
    doc_id = res.json()["document"]["id"]
    x = rahima.get(f"/privacy/documents/{doc_id}").json()
    assert x["kind"] == "document" and x["available"]
    right = "".join(s["text"] for b in x["right"] for s in b["segments"])
    for raw in ("SIM-CN-6222-****-1188", "9,600.00", "01711223344"):
        assert raw not in right
    assert "⟦ACCT_1⟧" in right and "⟦AMT_" in right and "⟦PHONE_1⟧" in right
    assert x["right"][0]["sent"] is False  # mock mode: prepared, not sent
    left = "".join(s["text"] for b in x["left"] for s in b["segments"])
    assert "SIM-CN-6222-****-1188" in left
    assert x["stats"]["leaked_count"] == 0
