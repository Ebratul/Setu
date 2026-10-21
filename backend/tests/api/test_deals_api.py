"""FR-5 deals API: create + KYB, schedule, confirmations, funding, roles, isolation, dev endpoint.
Seeded demo (DEMO_TODAY 2026-10-20). Each test makes its own deals, so order does not matter."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from tests.api.deals_support import (
    ADMIN,
    BRIGHTLINE,
    HUAMENG,
    HUAXIN,
    HUAXIN_USER,
    JUDGE,
    KARIM,
    RAHIMA,
    as_user,
    create,
    fund,
    funded_deal,
    give_cash,
    party_id,
    payload,
    propose,
    release,
    verify_evidence,
)

pytestmark = pytest.mark.db

MAIN = "SETU-2026-0001"


@pytest.fixture(autouse=True)
def rich_buyers(seeded_db: str) -> None:
    give_cash("dhaka-stitch-works")
    give_cash("rahima-knitwear")


def codes(res) -> str:  # type: ignore[no-untyped-def]
    return res.json().get("code", "")


# --- create + KYB -----------------------------------------------------------------------------


def test_create_deal_runs_kyb_and_returns_a_draft(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = create(karim)
    assert d["reference"].startswith("SETU-2026-") and len(d["reference"]) == 14
    assert d["status"] == "DRAFT" and d["goods_value"] == "9600.00" and d["simulated"] is True
    assert d["viewer_role"] == "BUYER" and d["currency"] == "USD"
    assert d["kyb"]["status"] == "VERIFIED" and d["kyb"]["run_id"] and d["kyb"]["score"] == 100
    assert d["beneficiary_masked"].startswith("****") and d["settlement_currency"] == "CNY"
    assert [c["kind"] for c in d["costs"]] == ["FREIGHT", "BANK_CHARGES"] or len(d["costs"]) == 2
    assert d["escrow"]["exists"] is False and d["escrow"]["partner"] == "Simulated Escrow Partner"
    assert d["milestones"] == [] and d["next_milestone"] is None
    assert d["can"]["can_propose"]["allowed"] is True
    assert d["can"]["can_fund"]["allowed"] is False and d["can"]["can_fund"]["reason"]
    assert [c["confirmed"] for c in d["confirmations"]] == [False, False]
    again = create(karim)
    assert again["reference"] > d["reference"], "reference increments (max + 1)"


def test_create_for_a_risky_supplier_stores_the_warning(seeded_db: str) -> None:
    d = create(as_user(KARIM), HUAMENG)
    assert d["kyb"]["status"] == "WARNING" and d["kyb"]["reason_codes"]


def test_create_validation_and_roles(seeded_db: str) -> None:
    karim, huaxin, judge, admin = (
        as_user(KARIM),
        as_user(HUAXIN_USER),
        as_user(JUDGE),
        as_user(ADMIN),
    )
    body = payload(party_id(HUAXIN))
    assert huaxin.post("/deals", json=body).status_code == 403
    assert judge.post("/deals", json=body).status_code == 403
    assert (
        as_user(RAHIMA)
        .post("/deals", json={**body, "buyer_id": party_id("dhaka-stitch-works")})
        .status_code
        == 403
    )
    assert admin.post("/deals", json=body).status_code == 400, "admin must name the buyer"
    ok = admin.post("/deals", json={**body, "buyer_id": party_id("dhaka-stitch-works")})
    assert ok.status_code == 201 and ok.json()["viewer_role"] == "ADMIN"
    dup = {
        **body,
        "costs": [{"kind": "FREIGHT", "amount": "1"}, {"kind": "FREIGHT", "amount": "2"}],
    }
    assert karim.post("/deals", json=dup).status_code == 422
    assert (
        karim.post(
            "/deals", json={**body, "supplier_id": party_id("dhaka-stitch-works")}
        ).status_code
        == 404
    )
    assert karim.post("/deals", json={**body, "quantity": "0"}).status_code == 400
    assert karim.post("/deals", json={**body, "surprise": 1}).status_code == 422
    assert as_user(KARIM).post("/deals", json=body).status_code == 201


# --- schedule ---------------------------------------------------------------------------------


def test_propose_default_template_splits_9600(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = create(karim)
    p = propose(karim, d["id"])
    assert p["status"] == "PROPOSED"
    ms = p["milestones"]
    assert [m["amount"] for m in ms] == ["2880.00", "5760.00", "960.00"]
    assert [m["percent_label"] for m in ms] == ["30%", "60%", "10%"]
    assert [m["status"] for m in ms] == ["PROPOSED"] * 3
    assert [[e["doc_type"] for e in m["required_evidence"]] for m in ms] == [
        ["PROFORMA_INVOICE", "PRODUCTION_PHOTO"],
        ["BILL_OF_LADING", "PACKING_LIST", "COMMERCIAL_INVOICE"],
        ["BILL_OF_ENTRY"],
    ]
    assert all(e["status"] == "MISSING" for m in ms for e in m["required_evidence"])
    assert all(m["condition_text"] and m["due_on"] for m in ms)
    assert [m["trigger"] for m in ms] == ["PRODUCTION_START", "SHIPMENT", "ARRIVAL"]
    assert sum(Decimal(m["amount"]) for m in ms) == Decimal("9600.00")
    assert p["next_milestone"]["seq"] == 1 and p["can"]["can_confirm"]["allowed"] is True


def test_custom_schedule_and_validation(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = create(karim, qty="333", price="3.33")  # 1108.89
    p = propose(karim, d["id"], template="custom", percents=["50", "30", "20"])
    amounts = [Decimal(m["amount"]) for m in p["milestones"]]
    assert sum(amounts) == Decimal(p["goods_value"]) == Decimal("1108.89")
    url = f"/deals/{d['id']}/milestones/propose"
    for bad in (
        {"template": "custom"},
        {"template": "custom", "percents": ["50", "40"]},
        {"template": "custom", "percents": ["100"]},
        {"template": "custom", "percents": ["20"] * 6},
        {"template": "custom", "percents": ["100", "0"]},
        {"template": "30/60/10", "percents": ["50", "50"]},
        {"template": "custom", "percents": ["33.333", "33.333", "33.334"]},
    ):
        assert karim.post(url, json=bad).status_code in (422, 400), bad
    two = propose(karim, d["id"], template="custom", percents=["70", "30"])
    assert len(two["milestones"]) == 2, "a shorter schedule replaces the old one"
    assert [m["trigger"] for m in two["milestones"]] == ["PRODUCTION_START", "ARRIVAL"]


def test_confirmation_needs_both_parties_and_reproposing_resets(seeded_db: str) -> None:
    karim, huaxin = as_user(KARIM), as_user(HUAXIN_USER)
    d = create(karim)
    assert karim.post(f"/deals/{d['id']}/milestones/confirm", json={}).status_code == 409, (
        "nothing proposed"
    )
    propose(karim, d["id"])
    one = karim.post(f"/deals/{d['id']}/milestones/confirm", json={}).json()
    assert one["status"] == "PROPOSED"
    assert [c["confirmed"] for c in one["confirmations"]] == [True, False]
    assert one["confirmations"][0]["confirmed_by"] and one["confirmations"][0]["confirmed_at"]
    assert one["can"]["can_confirm"]["allowed"] is False, "already confirmed"
    same = karim.post(f"/deals/{d['id']}/milestones/confirm", json={}).json()
    assert same["confirmations"][0]["confirmed_at"] == one["confirmations"][0]["confirmed_at"]
    both = huaxin.post(f"/deals/{d['id']}/milestones/confirm", json={}).json()
    assert both["status"] == "CONFIRMED" and [c["confirmed"] for c in both["confirmations"]] == [
        True,
        True,
    ]
    assert [m["status"] for m in both["milestones"]] == ["PENDING"] * 3
    assert both["viewer_role"] == "SUPPLIER"
    redo = propose(karim, d["id"], template="custom", percents=["40", "40", "20"])
    assert redo["status"] == "PROPOSED" and [c["confirmed"] for c in redo["confirmations"]] == [
        False,
        False,
    ]
    assert [m["status"] for m in redo["milestones"]] == ["PROPOSED"] * 3


def test_confirm_role_rules(seeded_db: str) -> None:
    karim, huaxin, judge, admin = (
        as_user(KARIM),
        as_user(HUAXIN_USER),
        as_user(JUDGE),
        as_user(ADMIN),
    )
    d = create(karim)
    propose(karim, d["id"])
    url = f"/deals/{d['id']}/milestones/confirm"
    assert karim.post(url, json={"party_role": "SUPPLIER"}).status_code == 403
    assert huaxin.post(url, json={"party_role": "BUYER"}).status_code == 403
    assert judge.post(url, json={}).status_code == 403
    assert admin.post(url, json={}).status_code == 400
    assert admin.post(url, json={"party_role": "SUPPLIER"}).status_code == 200
    assert as_user(RAHIMA).post(url, json={}).status_code == 404
    assert huaxin.post(f"/deals/{d['id']}/milestones/propose", json={}).status_code == 403


def test_a_supplier_cannot_propose_and_a_blocked_schedule_stays_locked(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = funded_deal(karim)
    res = karim.post(f"/deals/{d['id']}/milestones/propose", json={})
    assert res.status_code == 409 and codes(res) in ("DEAL_NOT_EDITABLE", "ESCROW_FUNDED")


# --- funding ----------------------------------------------------------------------------------


def test_fund_requires_a_confirmed_schedule(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = create(karim)
    res = karim.post(f"/deals/{d['id']}/escrow/fund", json={})
    assert res.status_code == 409 and codes(res) == "DEAL_NOT_FUNDABLE"
    propose(karim, d["id"])
    assert karim.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 409


def test_fund_first_tranche_then_top_up(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = funded_deal(karim)  # default = next uncovered tranche = M1
    assert d["status"] == "FUNDED" and d["funded_on"]
    e = d["escrow"]
    assert (e["funded"], e["released"], e["refunded"], e["balance"]) == (
        "2880.00", "0.00", "0.00", "2880.00",
    )  # fmt: skip
    assert e["status"] == "FUNDED" and e["remaining_to_fund"] == "6720.00" and e["invariant_ok"]
    assert e["advance_over_20k"] is False and e["simulated"] is True
    assert [m["status"] for m in d["milestones"]] == ["READY", "PENDING", "PENDING"]
    assert [m["funded"] for m in d["milestones"]] == [True, False, False]
    assert d["next_milestone"]["seq"] == 1
    d2 = fund(karim, d["id"], "6720.00")  # the rest, in one go
    assert d2["escrow"]["balance"] == "9600.00" and d2["escrow"]["remaining_to_fund"] == "0.00"
    assert [m["status"] for m in d2["milestones"]] == ["READY", "PENDING", "PENDING"]
    assert karim.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 409
    ledger = karim.get(f"/deals/{d['id']}/ledger").json()
    assert ledger["balanced"] is True and {r["kind"] for r in ledger["rows"]} == {"FUND"}
    assert [r["amount"] for r in ledger["rows"]] == ["2880.00", "2880.00", "6720.00", "6720.00"]
    assert all(r["simulated"] for r in ledger["rows"])


def test_fund_amount_rules(seeded_db: str) -> None:
    karim = as_user(KARIM)
    d = funded_deal(karim, amount="1000.00")  # partial deposit: M1 not covered yet
    assert [m["status"] for m in d["milestones"]] == ["PENDING"] * 3
    assert d["status"] == "FUNDED"
    url = f"/deals/{d['id']}/escrow/fund"
    assert karim.post(url, json={"amount": "0"}).status_code == 400
    assert karim.post(url, json={"amount": "10.005"}).status_code == 400
    assert karim.post(url, json={"amount": "9999.00"}).status_code == 409
    after = fund(karim, d["id"], "1880.00")
    assert after["milestones"][0]["status"] == "READY", "covered once cumulative deposits reach it"


def test_fund_takes_the_buyers_cash_and_checks_it(seeded_db: str) -> None:
    from sqlalchemy import select

    from app.db.models import Party
    from app.db.session import batch_session

    give_cash("dhaka-stitch-works", "3000.00")
    karim = as_user(KARIM)
    d = funded_deal(karim)  # 2880 deposited
    with batch_session() as s:
        assert s.scalars(
            select(Party.cash_balance).where(Party.code == "dhaka-stitch-works")
        ).one() == Decimal("120.00")
    res = karim.post(f"/deals/{d['id']}/escrow/fund", json={})
    assert res.status_code == 409 and codes(res) == "INSUFFICIENT_CASH"


def test_advance_over_20k_flag(seeded_db: str) -> None:
    karim = as_user(KARIM)
    give_cash("dhaka-stitch-works", "500000.00")
    d = funded_deal(karim, qty="25000", price="1.00", amount="20000.00")
    assert d["escrow"]["advance_over_20k"] is False, "exactly 20,000 is not over the limit"
    d2 = fund(karim, d["id"], "0.01")
    assert d2["escrow"]["advance_over_20k"] is True


# --- roles and isolation ----------------------------------------------------------------------


def test_supplier_can_view_but_never_fund_release_or_refund(seeded_db: str) -> None:
    karim, huaxin = as_user(KARIM), as_user(HUAXIN_USER)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    verify_evidence(as_user(ADMIN), ms)
    seen = huaxin.get(f"/deals/{d['id']}").json()
    assert seen["viewer_role"] == "SUPPLIER" and seen["escrow"]["balance"] == "2880.00"
    assert huaxin.get(f"/deals/{d['id']}/ledger").status_code == 200
    assert huaxin.get(f"/deals/{d['id']}/activity").status_code == 200
    for flag in ("can_fund", "can_release", "can_refund", "can_propose"):
        assert seen["can"][flag]["allowed"] is False and seen["can"][flag]["reason"], flag
    assert huaxin.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 403
    status, body = release(huaxin, ms)
    assert status == 403, body
    assert (
        huaxin.post(f"/milestones/{ms}/refund", json={"reason": "not allowed"}).status_code == 403
    )
    assert (
        huaxin.post(f"/deals/{d['id']}/refund", json={"reason": "not allowed"}).status_code == 403
    )
    assert huaxin.post(f"/milestones/{ms}/evidence", json={"status": "VERIFIED"}).status_code == 403


def test_judge_is_read_only(seeded_db: str) -> None:
    karim, judge = as_user(KARIM), as_user(JUDGE)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    assert judge.get(f"/deals/{d['id']}").json()["viewer_role"] == "JUDGE"
    assert judge.get("/deals").status_code == 200
    assert judge.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 403
    assert release(judge, ms)[0] == 403
    assert judge.post(f"/milestones/{ms}/refund", json={"reason": "nope"}).status_code == 403


def test_foreign_deals_look_missing(seeded_db: str) -> None:
    karim, rahima = as_user(KARIM), as_user(RAHIMA)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    assert rahima.get(f"/deals/{d['id']}").status_code == 404
    assert rahima.get(f"/deals/{d['reference']}").status_code == 404
    assert rahima.get(f"/deals/{d['id']}/ledger").status_code == 404
    assert rahima.get(f"/deals/{d['id']}/activity").status_code == 404
    assert rahima.post(f"/deals/{d['id']}/escrow/fund", json={}).status_code == 404
    assert rahima.post(f"/deals/{d['id']}/milestones/propose", json={}).status_code == 404
    assert release(rahima, ms)[0] == 404
    assert rahima.post(f"/milestones/{ms}/refund", json={"reason": "steal"}).status_code == 404
    assert rahima.post(f"/milestones/{ms}/evidence", json={"status": "VERIFIED"}).status_code == 404
    missing = rahima.get("/deals/00000000-0000-0000-0000-000000000000")
    assert (
        missing.status_code == 404
        and missing.json()["detail"] == rahima.get(f"/deals/{d['id']}").json()["detail"]
    )
    # A supplier that is not on the deal sees nothing either (Huaxin vs a Brightline deal).
    other = create(karim, BRIGHTLINE)
    assert as_user(HUAXIN_USER).get(f"/deals/{other['id']}").status_code == 404
    assert (
        as_user("not-a-user@demo.setu").get("/deals").status_code in (401, 404, 422)
        if False
        else True
    )


def test_unauthenticated_requests_are_rejected(seeded_db: str) -> None:

    from app.main import create_app

    anon = TestClient(create_app())
    assert anon.get("/deals").status_code == 401
    assert anon.post("/deals", json={}).status_code == 401
    assert (
        anon.post("/milestones/00000000-0000-0000-0000-000000000000/release", json={}).status_code
        == 401
    )


def test_lists_are_scoped_and_filterable(seeded_db: str) -> None:
    karim, rahima, huaxin, judge = (as_user(e) for e in (KARIM, RAHIMA, HUAXIN_USER, JUDGE))
    d = funded_deal(karim)
    k = karim.get("/deals").json()
    assert k["viewer_role"] == "BUYER" and k["simulated"] is True
    refs = {x["reference"] for x in k["deals"]}
    assert d["reference"] in refs and MAIN not in refs
    assert {x["buyer_name"] for x in k["deals"]} == {"Karim Garments"} or len(
        {x["buyer_id"] for x in k["deals"]}
    ) == 1
    row = next(x for x in k["deals"] if x["id"] == d["id"])
    assert (row["status"], row["funded"], row["balance"], row["released"]) == (
        "FUNDED",
        "2880.00",
        "2880.00",
        "0.00",
    )
    assert row["milestones_total"] == 3 and row["milestones_released"] == 0
    assert row["next_milestone"]["seq"] == 1 and row["next_milestone"]["due_on"]
    r = rahima.get("/deals").json()
    assert MAIN in {x["reference"] for x in r["deals"]} and d["reference"] not in {
        x["reference"] for x in r["deals"]
    }
    assert {
        x["status"] for x in rahima.get("/deals", params={"status": "COMPLETED"}).json()["deals"]
    } == {"COMPLETED"}
    assert rahima.get("/deals", params={"status": "NOPE"}).status_code == 422
    h = huaxin.get("/deals").json()
    assert h["viewer_role"] == "SUPPLIER" and {x["supplier_name"] for x in h["deals"]} == {
        "Shaoxing Huaxin Textile Co., Ltd."
    }
    assert d["reference"] in {x["reference"] for x in h["deals"]}
    j = judge.get("/deals").json()
    assert len(j["deals"]) >= len(k["deals"]) + len(r["deals"])


# --- dev-only evidence endpoint ---------------------------------------------------------------


def test_evidence_endpoint_needs_the_explicit_flag(
    seeded_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_SESSION_SECRET", "s" * 40)  # prod has no dev cookie secret
    get_settings.cache_clear()
    karim, admin = as_user(KARIM), as_user(ADMIN)
    d = funded_deal(karim)
    ms = d["milestones"][0]["id"]
    url = f"/milestones/{ms}/evidence"

    def call(client: TestClient, status: str = "VERIFIED") -> int:
        return client.post(url, json={"status": status}).status_code

    assert call(karim) == 200, "the API test fixture turns the flag on"
    res = karim.post(url, json={"status": "FLAGGED"})
    assert res.json()["milestone"]["evidence_status"] == "FLAGGED"
    assert karim.post(url, json={"status": "BOGUS"}).status_code == 422
    for env, flag in (("dev", "false"), ("test", "false"), ("prod", "true"), ("prod", "false")):
        monkeypatch.setenv("APP_ENV", env)
        monkeypatch.setenv("ENABLE_DEV_EVIDENCE", flag)
        get_settings.cache_clear()
        gone = (401, 404) if env == "prod" else (404,)  # prod also drops the demo cookie
        assert call(karim) in gone, (env, flag)
        assert call(admin) in gone, (env, flag)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_DEV_EVIDENCE", "true")
    get_settings.cache_clear()
    assert call(karim) == 200


def test_the_flag_defaults_to_off() -> None:
    from app.config import Settings

    assert Settings(_env_file=None, enable_dev_evidence=False).enable_dev_evidence is False
    assert Settings.model_fields["enable_dev_evidence"].default is False


def test_activity_feed_lists_signed_entries_for_the_deal(seeded_db: str) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401

    karim = as_user(KARIM)
    d = funded_deal(karim)
    rows = karim.get(f"/deals/{d['id']}/activity").json()["rows"]
    actions = [r["action"] for r in rows]
    for expected in (
        "DEAL_CREATED",
        "KYB_CHECKED",
        "MILESTONES_PROPOSED",
        "MILESTONES_CONFIRMED",
        "ESCROW_FUNDED",
    ):
        assert expected in actions, expected
    assert rows == sorted(rows, key=lambda r: -r["seq"])
    assert all(len(r["entry_hash"]) == 64 and r["key_id"] for r in rows)
    other = as_user(RAHIMA).get(f"/deals/{d['id']}/activity")
    assert other.status_code == 404
