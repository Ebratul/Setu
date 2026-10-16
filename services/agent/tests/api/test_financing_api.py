"""FR-1 financing endpoints against the seeded demo world (read-only)."""

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM = "rahima@demo.setu", "karim@demo.setu"
MAIN = "SETU-2026-0001"


def match(client: TestClient, **body: object) -> dict:
    res = client.post("/financing/match", json={"deal_id": MAIN, **body})
    assert res.status_code == 200, res.text
    return res.json()


def test_tc09_order_mode(client: TestClient) -> None:
    login(client, RAHIMA)
    gap = client.get("/financing/gap", params={"mode": "order", "deal_id": MAIN}).json()
    assert gap["amount"]["USD"] == "5200.00"
    assert gap["landed_cost"]["USD"] == "11200.00" and gap["available_cash"]["USD"] == "6000.00"
    assert gap["needed_for_days"] == 45
    m = match(client, mode="order")
    assert m["amount"]["USD"] == "5200.00"
    ranked = [(o["code"], o["cost"]["total"]["USD"], o["tenor_days"]) for o in m["options"]]
    assert ranked[:3] == [
        ("escrow-order-loan-setu-partner", "97.70", 45),
        ("supplier-credit-huaxin", "104.00", 60),
        ("import-loan-meghna", "173.45", 90),
    ]
    assert m["options"][0]["recommended"] and not any(o["recommended"] for o in m["options"][1:])
    assert all(o["checks"] for o in m["options"])  # every option carries its eligibility reasons
    insured = next(o for o in m["options"] if o["code"] == "insured-supplier-terms")
    assert not insured["eligible"]
    assert [w["code"] for w in insured["why_not"]] == ["NOT_WITH_FUNDED_ESCROW"]
    pick = m["top_pick"]
    assert pick["code"] == "escrow-order-loan-setu-partner"
    assert pick["saving_vs_next"]["USD"] == "6.30"
    assert {"LOWEST_COST", "USES_ESCROW"} <= set(pick["why_codes"])
    assert all(s["en"] and s["bn"] for s in pick["sentences"])
    supplier = next(o for o in m["options"] if o["code"] == "supplier-credit-huaxin")
    assert any(n["code"] == "PRICE_UPLIFT" for n in supplier["risk_notes"])


def test_shortfall_mode(client: TestClient) -> None:
    login(client, RAHIMA)
    gap = client.get("/financing/gap").json()
    assert gap["mode"] == "shortfall" and gap["deal"]["reference"] == MAIN
    assert gap["amount"]["USD"] == "1560.00"
    assert gap["needed_by"] == "2026-11-07" and gap["recover_on"] == "2026-11-19"
    assert gap["needed_for_days"] == 12 and gap["peak_amount"]["USD"] == "2160.00"
    m = match(client, mode="shortfall")
    assert m["amount"]["USD"] == "1560.00" and m["needed_by"] == "2026-11-07"
    why_not = {o["code"]: {w["code"] for w in o["why_not"]} for o in m["options"]}
    assert why_not["insured-supplier-terms"] == {"MIN_AMOUNT", "NOT_WITH_FUNDED_ESCROW"}
    assert "MIN_AMOUNT" in why_not["import-loan-meghna"]
    eligible = [o for o in m["options"] if o["eligible"]]
    assert eligible and all(o["rank"] < 4 for o in eligible)


def test_ranking_is_deterministic(client: TestClient) -> None:
    login(client, RAHIMA)
    first = match(client, mode="order")
    second = match(client, mode="order")
    assert [o["code"] for o in first["options"]] == [o["code"] for o in second["options"]]
    assert first == second


def test_amount_override_and_no_financing_needed(client: TestClient) -> None:
    login(client, RAHIMA)
    m = match(client, mode="order", amount="2500.00")
    assert m["amount"]["USD"] == "2500.00"
    karim = login(client, KARIM)
    g = karim.get("/financing/gap").json()
    assert g["no_financing_needed"] is True and g["amount"]["USD"] == "0.00"


def test_schedule_and_impact(client: TestClient) -> None:
    login(client, RAHIMA)
    s = client.get(
        "/financing/options/import-loan-meghna/schedule",
        params={"amount": "5200.00", "deal_id": MAIN, "start": "2026-10-20"},
    ).json()
    assert s["tenor_days"] == 90 and s["maturity_on"] == "2027-01-18"
    assert s["instalments"][0]["total"]["USD"] == "5373.45"
    i = client.post(
        "/financing/impact",
        json={"option_id": "escrow-order-loan-setu-partner", "amount": "1560.00", "deal_id": MAIN},
    ).json()
    assert i["original_shortfall"]["on"] == "2026-11-07"
    assert i["original_covered"] is True
    assert i["inflow"] == {"on": "2026-11-07", "amount": "1560.00"}
    assert i["repayment"]["on"] == "2026-12-04" and i["repayment_in_window"] is True
    assert len(i["series"]) == 91
    assert (
        client.post("/financing/impact", json={"option_id": "nope", "amount": "1"}).status_code
        == 404
    )


def test_isolation_and_roles(client: TestClient) -> None:
    karim_party = login(client, KARIM).get("/auth/me").json()["party_id"]
    login(client, RAHIMA)
    assert client.get("/financing/gap", params={"deal_id": "SETU-2026-0004"}).status_code == 403
    assert client.post("/financing/match", json={"deal_id": "SETU-2026-0004"}).status_code == 403
    assert client.get("/financing/gap", params={"party_id": karim_party}).status_code == 403
    assert (
        client.get("/financing/applications", params={"party_id": karim_party}).status_code == 403
    )
    login(client, "judge@demo.setu")
    rahima_party = login(client, RAHIMA).get("/auth/me").json()["party_id"]
    login(client, "judge@demo.setu")
    assert client.get("/financing/gap", params={"party_id": rahima_party}).status_code == 200
    body = {
        "party_id": rahima_party,
        "deal_id": MAIN,
        "option_id": "supplier-credit-huaxin",
        "amount": "1560.00",
    }
    assert client.post("/financing/applications", json=body).status_code == 403
    login(client, "huaxin@demo.setu")
    assert client.get("/financing/gap").status_code == 403
