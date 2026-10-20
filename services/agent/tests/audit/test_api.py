"""Audit API over HTTP against the seeded demo chain: role matrix, entry detail, export, verify."""

# ruff: noqa: F811  (pytest fixtures imported by name)

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.audit.export import line_of
from app.audit.keys import fingerprint, load_signing_key, public_pem
from app.audit.scheme import body_of, canonical_json
from app.audit.verify import verify_lines
from app.audit.writer import write_audit
from app.db.models import AuditLog, Deal, Party
from app.db.session import batch_session
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)
from tests.api.deals_support import ADMIN, HUAXIN_USER, JUDGE, KARIM, RAHIMA, as_user
from tests.documents.support import DEAL as MAIN

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def ids(seeded_db: str) -> dict[str, uuid.UUID]:
    """One audit seq with a deal of Rahima, one of Karim, one without any deal."""
    with batch_session() as s:
        rahima_party = s.scalars(select(Party.id).where(Party.code == "rahima-knitwear")).one()
        karim_party = s.scalars(select(Party.id).where(Party.code == "dhaka-stitch-works")).one()
        out: dict[str, uuid.UUID] = {}
        for name, party in (("rahima", rahima_party), ("karim", karim_party)):
            deal, seq = s.execute(
                select(AuditLog.deal_id, func.min(AuditLog.seq))
                .join(Deal, Deal.id == AuditLog.deal_id)
                .where(Deal.buyer_id == party)
                .group_by(AuditLog.deal_id)
                .order_by(func.min(AuditLog.seq))
                .limit(1)
            ).one()
            out[f"{name}_deal"], out[f"{name}_seq"] = deal, seq  # type: ignore[assignment]
        out["no_deal_seq"] = write_audit(  # type: ignore[assignment]
            s, actor="system", action="TEST_NO_DEAL", tier=0, params={}, result="OK"
        )
    assert out["rahima_seq"] and out["karim_seq"] and out["no_deal_seq"]
    return out


ALL_READERS_ONLY = ["/audit/summary", "/audit/entries", "/audit/verify"]


@pytest.mark.parametrize("path", ALL_READERS_ONLY)
@pytest.mark.parametrize("who", [ADMIN, JUDGE])
def test_admin_and_judge_can_read_the_whole_log(seeded_db: str, path: str, who: str) -> None:
    assert as_user(who).get(path).status_code == 200


@pytest.mark.parametrize("path", ALL_READERS_ONLY)
@pytest.mark.parametrize("who", [RAHIMA, KARIM, HUAXIN_USER])
def test_buyers_and_suppliers_are_forbidden_from_the_whole_log(
    seeded_db: str, path: str, who: str
) -> None:
    assert as_user(who).get(path).status_code == 403


@pytest.mark.parametrize(
    "path",
    [*ALL_READERS_ONLY, "/audit/entries/1", "/audit/export"],
)
def test_unauthenticated_requests_get_401(seeded_db: str, path: str) -> None:
    from app.main import create_app

    assert TestClient(create_app()).get(path).status_code == 401


def test_public_key_is_public_and_matches_the_signing_key(seeded_db: str) -> None:
    from app.main import create_app

    res = TestClient(create_app()).get("/audit/public-key")
    assert res.status_code == 200
    body = res.json()
    pub = load_signing_key().public_key()
    assert body["pem"] == public_pem(pub) and body["fingerprint"] == fingerprint(pub)
    assert body["scheme"] == "setu-audit-v2" and body["genesis"] == "0" * 64
    assert body["key_id"] == body["fingerprint"][:16]
    assert "PRIVATE" not in res.text


def test_summary_counts_match_the_table(seeded_db: str) -> None:
    body = as_user(ADMIN).get("/audit/summary").json()
    with batch_session() as s:
        total = s.scalar(select(func.count()).select_from(AuditLog))
        head = s.scalar(select(func.max(AuditLog.seq)))
    assert body["total"] == total and body["head_seq"] == head
    assert sum(x["count"] for x in body["by_action"]) == total
    assert sum(x["count"] for x in body["by_tier"]) == total
    assert body["fingerprint"] == fingerprint(load_signing_key().public_key())


def test_entries_page_oldest_first_after_a_seq_and_filter_by_action(seeded_db: str) -> None:
    admin = as_user(ADMIN)
    page = admin.get("/audit/entries", params={"after": 0, "limit": 5}).json()
    seqs = [r["seq"] for r in page["rows"]]
    assert len(seqs) == 5 and seqs == sorted(seqs) and seqs[-1] == page["head_seq"]
    nxt = admin.get("/audit/entries", params={"after": 3, "limit": 4}).json()
    assert [r["seq"] for r in nxt["rows"]] == [4, 5, 6, 7]
    only = admin.get("/audit/entries", params={"action": "ESCROW_FUNDED", "limit": 50}).json()
    assert only["rows"] and {r["action"] for r in only["rows"]} == {"ESCROW_FUNDED"}
    assert all(r["text_en"] and r["text_bn"] for r in only["rows"])
    assert admin.get("/audit/entries", params={"limit": 201}).status_code == 422


def test_verify_is_ok_on_the_seeded_chain(seeded_db: str) -> None:
    body = as_user(JUDGE).get("/audit/verify").json()
    assert body["ok"] is True and body["broken_seq"] is None and body["anchored"] is True
    assert body["entries_checked"] == body["last_seq"] > 0


def test_verify_of_a_range_is_anchored_by_the_trusted_previous_hash(seeded_db: str) -> None:
    body = as_user(ADMIN).get("/audit/verify", params={"from": 5, "to": 9}).json()
    assert body["ok"] is True and body["first_seq"] == 5 and body["entries_checked"] == 5
    assert body["anchored"] is False


def test_entry_detail_has_the_canonical_bytes_and_is_verified(seeded_db: str) -> None:
    res = as_user(ADMIN).get("/audit/entries/3")
    assert res.status_code == 200
    body = res.json()
    with batch_session() as s:
        line = line_of(s.get(AuditLog, 3))  # type: ignore[arg-type]
    assert body["canonical"] == canonical_json(body_of(line))
    assert json.loads(body["canonical"]) == body_of(line)
    assert body["verified"] is True and body["verify_reason"] is None
    assert body["entry_hash"] == line["entry_hash"] and body["signature"] == line["signature"]


def test_unknown_entry_is_404(seeded_db: str) -> None:
    assert as_user(ADMIN).get("/audit/entries/99999999").status_code == 404


def test_buyer_can_open_an_entry_of_their_own_deal(seeded_db: str, ids: dict) -> None:
    res = as_user(RAHIMA).get(f"/audit/entries/{ids['rahima_seq']}")
    assert res.status_code == 200 and res.json()["verified"] is True


def test_buyer_cannot_open_an_entry_of_another_buyers_deal(seeded_db: str, ids: dict) -> None:
    assert as_user(RAHIMA).get(f"/audit/entries/{ids['karim_seq']}").status_code == 404
    assert as_user(KARIM).get(f"/audit/entries/{ids['rahima_seq']}").status_code == 404


def test_buyer_cannot_open_an_entry_that_belongs_to_no_deal(seeded_db: str, ids: dict) -> None:
    assert as_user(RAHIMA).get(f"/audit/entries/{ids['no_deal_seq']}").status_code == 404


def test_supplier_cannot_open_entries_even_of_their_own_deal(seeded_db: str, ids: dict) -> None:
    # Huaxin supplies Rahima's demo deal; suppliers have no access to the audit log
    assert as_user(HUAXIN_USER).get(f"/audit/entries/{ids['rahima_seq']}").status_code in (403, 404)


def lines_of(res_text: str) -> tuple[dict, list[dict]]:
    rows = [json.loads(x) for x in res_text.splitlines()]
    return rows[0], rows[1:]


def test_export_is_ndjson_with_the_header_first_and_verifies(seeded_db: str) -> None:
    res = as_user(JUDGE).get("/audit/export")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in res.headers["content-disposition"]
    header, lines = lines_of(res.text)
    assert header["scheme"] == "setu-audit-v2" and header["contiguous"] is True
    assert header["entry_count"] == len(lines) and header["first_seq"] == 1
    assert verify_lines(lines, load_signing_key().public_key()).ok


def test_buyer_export_needs_a_deal_and_only_their_own(seeded_db: str, ids: dict) -> None:
    rahima = as_user(RAHIMA)
    assert rahima.get("/audit/export").status_code == 403
    mine = rahima.get("/audit/export", params={"deal_id": str(ids["rahima_deal"])})
    assert mine.status_code == 200
    header, lines = lines_of(mine.text)
    assert header["contiguous"] is False and lines
    assert {ln["deal_id"] for ln in lines} == {str(ids["rahima_deal"])}
    assert verify_lines(lines, load_signing_key().public_key(), contiguous=False).ok
    other = rahima.get("/audit/export", params={"deal_id": str(ids["karim_deal"])})
    assert other.status_code == 404


def test_supplier_cannot_export(seeded_db: str, ids: dict) -> None:
    huaxin = as_user(HUAXIN_USER)
    assert huaxin.get("/audit/export").status_code == 403
    res = huaxin.get("/audit/export", params={"deal_id": str(ids["rahima_deal"])})
    assert res.status_code == 404


def test_export_range_limits_the_slice(seeded_db: str) -> None:
    res = as_user(ADMIN).get("/audit/export", params={"from": 3, "to": 6})
    header, lines = lines_of(res.text)
    assert [ln["seq"] for ln in lines] == [3, 4, 5, 6] and header["first_seq"] == 3


def test_the_demo_deal_reference_resolves_for_its_buyer(seeded_db: str) -> None:
    assert as_user(RAHIMA).get(f"/deals/{MAIN}").status_code == 200
