"""FR-4 KYB endpoints against the seeded demo (DEMO_TODAY 2026-10-20): results, auth scopes,
history, idempotent re-runs, audit chain, alerts. Verify runs only converge on the same outcome,
so tests do not depend on order; state-changing scenarios live in test_kyb_lifecycle.py."""

import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import AlertType
from app.db.models import Alert, AuditLog, KybCheck, KybRun, Party
from app.db.session import get_engine
from app.security.audit import (
    AuditFields,
    SignedEntry,
    load_signing_key,
    verify_chain,
)
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM, HUAXIN_USER = "rahima@demo.setu", "karim@demo.setu", "huaxin@demo.setu"
ADMIN, JUDGE = "admin@demo.setu", "judge@demo.setu"
MAIN_DEAL = "SETU-2026-0001"


def supplier_ids(client: TestClient, email: str) -> dict[str, str]:
    login(client, email)
    rows = client.get("/suppliers").json()["suppliers"]
    return {r["name"].split()[1].lower(): r["supplier_id"] for r in rows}  # huaxin, huameng, ...


def codes(res: dict, status: str | None = None) -> dict[str, str]:
    return {c["code"]: c["status"] for c in res["checks"] if status in (None, c["status"])}


def test_huaxin_is_verified_and_the_pending_hk_account_is_flagged(client: TestClient) -> None:
    sid = supplier_ids(client, ADMIN)["huaxin"]
    res = client.post(f"/kyb/verify/{sid}", params={"deal_id": MAIN_DEAL})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "VERIFIED" and body["score"] == 100 and body["persisted"] is True
    assert body["invoice_name_source"] == "proforma" and body["deal_ref"] == MAIN_DEAL
    assert body["account"]["account_type"] == "CORPORATE" and body["account"]["currency"] == "CNY"
    assert body["account"]["masked_number"] == "****1188"
    assert "SIM-CN" not in res.text and "SIM-HK" not in res.text, (
        "full account numbers never leave the API"
    )
    assert body["has_pending_change"] is True
    [pending] = body["pending_accounts"]
    got = codes(pending)
    assert got["PENDING_BENEFICIARY_CHANGE"] == "WARN" and got["ACCOUNT_COUNTRY"] == "WARN"
    assert got["LICENSE_VS_ACCOUNT_HOLDER"] in ("WARN", "FAIL")
    assert pending["status"] == "WARNING" and pending["account"]["status"] == "PENDING_CHANGE"
    assert "PENDING_BENEFICIARY_CHANGE" in pending["reason_codes"]
    assert pending["explanation_en"] and pending["explanation_bn"]
    assert body["thresholds"] == {
        "match": 92.0,
        "partial": 80.0,
        "account_age_warn_days": 30,
        "account_age_fail_days": 7,
    }


def test_huameng_tc01_warning_for_its_buyer(client: TestClient) -> None:
    sid = supplier_ids(client, KARIM)["huameng"]
    body = client.post(f"/kyb/verify/{sid}").json()
    assert body["status"] == "WARNING" and body["score"] == 40
    assert codes(body, "FAIL") == {
        "LICENSE_VS_ACCOUNT_HOLDER": "FAIL",
        "ACCOUNT_TYPE": "FAIL",
        "ACCOUNT_AGE": "FAIL",
    }
    assert body["reason_codes"][:3] == ["LICENSE_VS_ACCOUNT_HOLDER", "ACCOUNT_TYPE", "ACCOUNT_AGE"]
    assert "Chen Wei" in body["explanation_en"] and body["explanation_bn"]
    assert body["has_pending_change"] is False
    listed = {s["name"]: s for s in client.get("/suppliers").json()["suppliers"]}
    h = listed["Guangzhou Huameng Trading Co., Ltd."]
    assert h["kyb_badge"] == "WARNING" and h["kyb_score"] == 40 and h["last_checked"]


def test_brightline_is_verified(client: TestClient) -> None:
    sid = supplier_ids(client, KARIM)["brightline"]
    body = client.post(f"/kyb/verify/{sid}").json()
    assert body["status"] == "VERIFIED", body["reason_codes"]


def test_auth_scopes(client: TestClient) -> None:
    ids = supplier_ids(client, ADMIN)
    # unauthenticated
    client.post("/auth/logout")
    assert client.post(f"/kyb/verify/{ids['huaxin']}").status_code == 401
    assert client.get(f"/kyb/{ids['huaxin']}").status_code == 401
    # buyer: only suppliers it has deals with; a foreign one looks missing
    login(client, RAHIMA)
    assert client.get(f"/kyb/{ids['huameng']}").status_code == 404
    assert client.post(f"/kyb/verify/{ids['huameng']}").status_code == 404
    assert client.get(f"/suppliers/{ids['huameng']}").status_code == 404
    assert client.post(f"/kyb/verify/{uuid.uuid4()}").status_code == 404  # same answer as foreign
    assert client.get(f"/kyb/{ids['huaxin']}").status_code == 200
    # another buyer's deal on a supplier both know is still not theirs
    login(client, KARIM)
    assert (
        client.post(f"/kyb/verify/{ids['huaxin']}", params={"deal_id": MAIN_DEAL}).status_code
        == 404
    )
    assert (
        client.post(f"/kyb/verify/{ids['huameng']}", params={"deal_id": MAIN_DEAL}).status_code
        == 404
    )
    # supplier role: no access at all
    login(client, HUAXIN_USER)
    assert client.get(f"/kyb/{ids['huaxin']}").status_code == 403
    assert client.post(f"/kyb/verify/{ids['huaxin']}").status_code == 403
    assert client.get("/suppliers").status_code == 403
    # judge: read-only
    login(client, JUDGE)
    assert client.get(f"/kyb/{ids['huameng']}").status_code == 200
    assert client.get(f"/suppliers/{ids['huameng']}").status_code == 200
    assert client.post(f"/kyb/verify/{ids['huameng']}").status_code == 403
    # input validation
    login(client, ADMIN)
    assert client.post("/kyb/verify/not-a-uuid").status_code == 422
    assert client.post(f"/kyb/verify/{ids['huaxin']}", params={"deal_id": "x;y"}).status_code == 422


def test_supplier_lists_are_buyer_scoped(client: TestClient) -> None:
    login(client, RAHIMA)
    rahima = client.get("/suppliers").json()
    assert sorted(s["code"] for s in rahima["suppliers"]) == [
        "ningbo-brightline",
        "shaoxing-huaxin",
    ]
    login(client, KARIM)
    assert len(client.get("/suppliers").json()["suppliers"]) == 3
    login(client, ADMIN)
    everything = client.get("/suppliers").json()
    assert len(everything["suppliers"]) == 3 and everything["buyer_id"] is None
    buyer = client.get("/auth/me").json()
    assert buyer["party_id"] is None
    login(client, RAHIMA)
    rahima_id = client.get("/auth/me").json()["party_id"]
    login(client, KARIM)
    assert client.get("/suppliers", params={"buyer_id": rahima_id}).status_code == 403
    login(client, ADMIN)
    scoped = client.get("/suppliers", params={"buyer_id": rahima_id}).json()
    assert len(scoped["suppliers"]) == 2
    huaxin = next(s for s in scoped["suppliers"] if s["code"] == "shaoxing-huaxin")
    assert huaxin["kyb_badge"] == "VERIFIED" and huaxin["has_pending_change"] is True
    assert huaxin["completed_deals"] == 2 and huaxin["on_time_rate_pct"] is not None
    assert huaxin["city"] == "Shaoxing" and huaxin["country"] == "CN"


def test_profile_has_company_accounts_deals_trend_and_kyb(client: TestClient) -> None:
    sid = supplier_ids(client, RAHIMA)["huaxin"]
    p = client.get(f"/suppliers/{sid}").json()
    assert p["company"]["legal_name"] == "Shaoxing Huaxin Textile Co., Ltd."
    assert p["company"]["license_no"].startswith("USCC-SIM-")
    kinds = sorted((a["status"], a["bank_country"], a["masked_number"][:4]) for a in p["accounts"])
    assert kinds == [("ACTIVE", "CN", "****"), ("PENDING_CHANGE", "HK", "****")]
    assert {d["reference"] for d in p["deals"]} == {MAIN_DEAL, "SETU-2025-0011", "SETU-2025-0019"}
    assert len(p["score_trend"]) >= 1 and p["completed_deals"] == 2
    assert p["kyb"]["supplier_id"] == sid and p["kyb_source"] in ("stored", "live")
    assert "SIM-CN" not in str(p) and "SIM-HK" not in str(p)
    login(client, KARIM)  # Karim only has the cancelled deal; Rahima's deals are not his to see
    pk = client.get(f"/suppliers/{sid}").json()
    assert [d["reference"] for d in pk["deals"]] == ["SETU-2026-0003"]


def test_get_returns_latest_and_history_newest_first(client: TestClient) -> None:
    sid = supplier_ids(client, KARIM)["huameng"]
    client.post(f"/kyb/verify/{sid}")
    client.post(f"/kyb/verify/{sid}")
    out = client.get(f"/kyb/{sid}").json()
    assert out["source"] == "stored" and out["latest"]["persisted"] is True
    assert out["latest"]["status"] == "WARNING"
    times = [h["checked_at"] for h in out["history"]]
    assert len(times) >= 2 and times == sorted(times, reverse=True)
    assert out["history"][0]["status"] == "WARNING" and out["history"][0]["score"] == 40


def test_rerun_is_idempotent_and_audited(client: TestClient, seeded_db: str) -> None:
    sid = supplier_ids(client, KARIM)["huameng"]
    client.post(f"/kyb/verify/{sid}")  # settle first so the counts below are stable

    def snapshot() -> dict[str, int]:
        with Session(get_engine()) as s:
            return {
                "runs": s.scalar(select(func.count()).select_from(KybRun)) or 0,
                "checks": s.scalar(select(func.count()).select_from(KybCheck)) or 0,
                "audit": s.scalar(select(func.count()).select_from(AuditLog)) or 0,
                "kyb_alerts": s.scalar(
                    select(func.count())
                    .select_from(Alert)
                    .where(Alert.type == AlertType.KYB_WARNING)
                )
                or 0,
            }

    before = snapshot()
    for _ in range(3):
        assert client.post(f"/kyb/verify/{sid}").status_code == 200
    after = snapshot()
    assert after["runs"] == before["runs"] + 3
    assert after["audit"] == before["audit"] + 3, "an audit row is written on every run"
    assert after["checks"] == before["checks"], "KybCheck is updated in place, never duplicated"
    assert after["kyb_alerts"] == before["kyb_alerts"] == 1, "no duplicate alerts"

    with Session(get_engine()) as s:
        rows = s.scalars(select(AuditLog).order_by(AuditLog.seq)).all()
        last = rows[-1]
        assert last.action == "KYB_CHECKED" and last.result == "WARNING" and last.tier == 0
        entries = [
            SignedEntry(
                AuditFields(
                    r.seq,
                    r.ts,
                    r.actor.value,
                    r.action,
                    r.tier,
                    r.params_hash,
                    r.result,
                    r.prev_hash,
                ),
                r.entry_hash,
                r.signature,
                r.key_id,
            )
            for r in rows
        ]
        key: Ed25519PrivateKey = load_signing_key()
        assert verify_chain(key.public_key(), entries) == [], "seeded + appended chain stays valid"
        run = s.scalars(select(KybRun).order_by(KybRun.checked_at.desc())).first()
        assert run is not None and run.audit_seq == last.seq


def test_karims_kyb_alert_is_unique_and_buyer_scoped(client: TestClient) -> None:
    sid = supplier_ids(client, KARIM)["huameng"]
    client.post(f"/kyb/verify/{sid}")
    [alert] = [a for a in client.get("/alerts").json()["alerts"] if a["type"] == "KYB_WARNING"]
    assert (
        alert["key"] == "alert:dhaka-stitch-works:kyb:guangzhou-huameng"
        and alert["status"] == "OPEN"
    )
    assert alert["severity"] == "WARNING" and alert["deal_ref"] == "SETU-2026-0005"
    assert alert["action"]["route"] == f"/app/suppliers/{sid}"
    login(client, RAHIMA)
    assert [a for a in client.get("/alerts").json()["alerts"] if a["type"] == "KYB_WARNING"] == []
    with Session(get_engine()) as s:
        status = s.scalar(select(Party.kyb_status).where(Party.code == "guangzhou-huameng"))
        assert status is not None and status.value == "WARNING"
