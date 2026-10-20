"""FR-2 forecast, alerts and dashboard against the seeded demo world (DEMO_TODAY 2026-10-20).
The seed runs the alert engine once, so alerts exist before any test calls recompute."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.domain.cashflow import running_balance
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM = "rahima@demo.setu", "karim@demo.setu"
M2 = "2026-11-07"
GOOD_CNY_DAY = "2026-10-22"


def alerts(client: TestClient, **params: str) -> list[dict]:
    res = client.get("/alerts", params=params)
    assert res.status_code == 200, res.text
    return res.json()["alerts"]


def test_tc08_shortfall_on_m2_date(client: TestClient) -> None:
    login(client, RAHIMA)
    [sf] = [a for a in alerts(client, status="OPEN") if a["type"] == "SHORTFALL"]
    assert sf["due_on"] == M2
    assert sf["amount"] == "1560.00"
    assert sf["severity"] in ("CRITICAL", "WARNING")
    assert sf["deal_ref"] == "SETU-2026-0001" and sf["milestone_seq"] == 2
    assert sf["action"]["route"] == "/app/financing"
    assert sf["action"]["query"]["amount"] == "1560.00"
    assert sf["facts"]["balance"] == "4200.00"
    assert sf["title_bn"]


def test_deadline_and_fx_alerts(client: TestClient) -> None:
    rows = alerts(login(client, RAHIMA), status="OPEN")
    deadlines = {a["facts"]["deadline"]: a for a in rows if a["type"] == "DEADLINE"}
    assert deadlines["DUTY"]["amount"] == "800.00"
    assert deadlines["DUTY"]["due_on"] == "2026-12-04"
    assert deadlines["BILL_OF_ENTRY"]["due_on"] == "2026-11-30"  # arrival T+40 + 1
    assert deadlines["BILL_OF_ENTRY"]["action"]["code"] == "UPLOAD_BILL_OF_ENTRY"
    assert "MILESTONE" not in deadlines  # milestone 2 is covered by the shortfall alert
    [fx] = [a for a in rows if a["type"] == "FX_OPPORTUNITY"]
    assert fx["due_on"] == GOOD_CNY_DAY
    assert fx["facts"]["rate"] == "16.9682" and fx["facts"]["pair"] == "CNY/BDT"
    order = [a["severity"] for a in rows]
    assert order == sorted(order, key=["CRITICAL", "WARNING", "INFO"].index)


def test_recompute_is_idempotent(client: TestClient) -> None:
    login(client, RAHIMA)
    before = alerts(client)
    res = client.post("/alerts/recompute").json()
    assert (res["created"], res["updated"], res["reopened"], res["resolved"]) == (0, 0, 0, 0)
    after = alerts(client)
    assert sorted(a["key"] for a in after) == sorted(a["key"] for a in before)
    assert len({a["key"] for a in after}) == len(after)


def test_forecast_matches_running_balance(client: TestClient) -> None:
    """Hand check 2026-11-03 … 2026-11-07: opening 3,645.00; rent 720 + insurance 50 → 2,875.00;
    nothing → 2,875.00; sales +1,325 → 4,200.00; nothing → 4,200.00; milestone 2 −5,760 → −1,560."""
    fc = login(client, RAHIMA).get("/cashflow/forecast").json()
    assert fc["simulated"] is True and len(fc["daily"]) == 91
    window = [d for d in fc["daily"] if "2026-11-03" <= d["on"] <= M2]
    assert [d["closing"] for d in window] == [
        "2875.00",
        "2875.00",
        "4200.00",
        "4200.00",
        "-1560.00",
    ]
    assert window[0]["opening"] == "3645.00"
    closings = running_balance(Decimal(window[0]["opening"]), [Decimal(d["net"]) for d in window])
    assert [f"{c}" for c in closings] == [d["closing"] for d in window]
    whole = running_balance(
        Decimal(fc["opening_balance"]), [Decimal(d["net"]) for d in fc["daily"]]
    )
    assert [f"{c:.2f}" for c in whole] == [d["closing"] for d in fc["daily"]]
    assert fc["first_shortfall"] == {"on": M2, "amount": "1560.00"}
    m2_items = next(d for d in fc["daily"] if d["on"] == M2)["items"]
    assert [i["ref"] for i in m2_items] == ["milestone:SETU-2026-0001:2"]


def test_scenario_loan_removes_m2_shortfall(client: TestClient) -> None:
    login(client, RAHIMA)
    body = {"loans": [{"amount": "1560.00", "on": "2026-11-05", "repay_on": "2027-02-01"}]}
    res = client.post("/cashflow/scenario", json=body).json()
    assert res["forecast"]["scenario"] is True
    m2 = next(d for d in res["forecast"]["daily"] if d["on"] == M2)
    assert m2["closing"] == "0.00" and m2["below_buffer"] is False
    assert not [a for a in res["alerts"] if a["type"] == "SHORTFALL" and a["due_on"] == M2]
    cover = client.get("/cashflow/forecast").json()["cover_amount"]
    full = client.post(
        "/cashflow/scenario", json={"loans": [{"amount": cover, "on": "2026-10-21"}]}
    ).json()
    assert full["forecast"]["first_shortfall"] is None
    assert not [a for a in full["alerts"] if a["type"] == "SHORTFALL"]
    # nothing was saved
    assert [a for a in alerts(client, status="OPEN") if a["type"] == "SHORTFALL"]


def test_scenario_move_and_remove(client: TestClient) -> None:
    login(client, RAHIMA)
    moved = client.post(
        "/cashflow/scenario",
        json={"moves": [{"ref": "milestone:SETU-2026-0001:2", "on": "2026-11-20"}]},
    ).json()
    assert next(d for d in moved["forecast"]["daily"] if d["on"] == M2)["closing"] == "4200.00"
    removed = client.post(
        "/cashflow/scenario", json={"removes": ["milestone:SETU-2026-0001:2"]}
    ).json()
    assert removed["forecast"]["lowest_balance"] != "-3835.00"
    bad = client.post("/cashflow/scenario", json={"removes": ["nope"]})
    assert bad.status_code == 400


def test_buyer_isolation(client: TestClient) -> None:
    karim_party = login(client, KARIM).get("/auth/me").json()["party_id"]
    karim_alert = alerts(client)[0]["id"]
    login(client, RAHIMA)
    assert client.get("/cashflow/forecast", params={"party_id": karim_party}).status_code == 403
    assert client.get("/alerts", params={"party_id": karim_party}).status_code == 403
    assert client.get("/dashboard", params={"party_id": karim_party}).status_code == 403
    assert client.post(f"/alerts/{karim_alert}/acknowledge").status_code == 404
    assert client.post("/cashflow/scenario", json={"party_id": karim_party}).status_code == 403
    assert client.post("/alerts/recompute", params={"party_id": karim_party}).status_code == 403


def test_judge_reads_but_cannot_write(client: TestClient) -> None:
    rahima_party = login(client, RAHIMA).get("/auth/me").json()["party_id"]
    some_alert = alerts(client)[0]["id"]
    login(client, "judge@demo.setu")
    assert client.get("/dashboard", params={"party_id": rahima_party}).status_code == 200
    assert client.get("/cashflow/forecast").status_code == 400  # party_id required
    assert client.post(f"/alerts/{some_alert}/acknowledge").status_code == 403
    assert client.post("/alerts/recompute", params={"party_id": rahima_party}).status_code == 403
    login(client, "huaxin@demo.setu")
    assert client.get("/cashflow/forecast").status_code == 403


def test_dashboard_rahima(client: TestClient) -> None:
    d = login(client, RAHIMA).get("/dashboard").json()
    assert d["simulated"] is True
    assert d["cash_balance"]["USD"] == "6000.00"
    assert d["in_escrow"]["USD"] == "2880.00"
    assert d["first_shortfall"] == {"on": M2, "amount": "1560.00"}
    assert d["pending_approvals"] == 2
    assert len(d["alerts"]) <= 5 and d["open_alerts_count"] >= len(d["alerts"])
    assert any(a["type"] == "SHORTFALL" and a["amount"] == "1560.00" for a in d["alerts"])
    top = {a["facts"].get("deadline") for a in d["alerts"] if a["type"] == "DEADLINE"}
    assert {"DUTY", "BILL_OF_ENTRY"} <= top
    assert d["deals_by_status"] == {"FUNDED": 1, "COMPLETED": 2, "DRAFT": 1}
    main = next(x for x in d["active_deals"] if x["reference"] == "SETU-2026-0001")
    assert main["next_milestone"]["seq"] == 1
    assert d["month"]["month"] == "2026-10" and d["month"]["average_margin_pct"] == "18.01"
    due = Decimal(d["due_next_30_days"]["USD"])
    assert due > Decimal("5760")  # includes milestone 2 on T+18


def test_karim_has_no_shortfall(client: TestClient) -> None:
    login(client, KARIM)
    assert client.get("/cashflow/forecast").json()["first_shortfall"] is None
    types = {a["type"] for a in alerts(client, status="OPEN")}
    assert "SHORTFALL" not in types and "KYB_WARNING" in types


def test_kyb_alert_resolve_rules(client: TestClient) -> None:
    login(client, KARIM)
    [kyb] = [a for a in alerts(client) if a["type"] == "KYB_WARNING"]
    assert client.post(f"/alerts/{kyb['id']}/resolve").status_code == 403
    assert client.post(f"/alerts/{kyb['id']}/acknowledge").json()["status"] == "ACKNOWLEDGED"
    login(client, "huaxin@demo.setu")
    assert client.post(f"/alerts/{kyb['id']}/resolve").status_code == 403
    login(client, "admin@demo.setu")
    assert client.post(f"/alerts/{kyb['id']}/resolve").json()["status"] == "RESOLVED"


@pytest.mark.parametrize(
    "body",
    [
        {"loans": [{"amount": "100", "on": "2026-10-19"}]},
        {"loans": [{"amount": "100", "on": "2027-06-01"}]},
        {"loans": [{"amount": "100", "on": "2026-11-01", "repay_on": "2026-10-30"}]},
        {"loans": [{"amount": "0", "on": "2026-11-01"}]},
        {"moves": [{"ref": "milestone:SETU-2026-0001:2", "on": "2030-01-01"}]},
    ],
)
def test_scenario_rejects_out_of_window_input(client: TestClient, body: dict) -> None:
    res = login(client, RAHIMA).post("/cashflow/scenario", json=body)
    assert res.status_code == 400, res.text


@pytest.mark.parametrize(
    "body",
    [
        {"days": 6},
        {"days": 181},
        {"loans": [{"amount": "1", "on": "2026-11-01"}] * 6},
        {"removes": ["x" * 121]},
        {"loans": [{"amount": 100.5, "on": "2026-11-01"}]},
    ],
)
def test_scenario_schema_bounds(client: TestClient, body: dict) -> None:
    assert login(client, RAHIMA).post("/cashflow/scenario", json=body).status_code == 422
