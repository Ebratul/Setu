"""FR-3 analysis endpoints against the seeded demo world (DEMO_TODAY 2026-10-20)."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.domain.landed_cost import CostLine, landed_cost
from app.domain.margin import gross_margin, pct
from app.domain.money import Money, q2
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM = "rahima@demo.setu", "karim@demo.setu"
MAIN = "SETU-2026-0001"


def test_requires_sign_in(client: TestClient) -> None:
    res = client.get(f"/analysis/orders/{MAIN}")
    assert res.status_code == 401
    assert res.headers["content-type"].startswith("application/problem+json")


def test_main_deal_matches_demo_table(client: TestClient) -> None:
    body = login(client, RAHIMA).get(f"/analysis/orders/{MAIN}").json()
    assert body["simulated"] is True
    assert body["deal"]["reference"] == MAIN
    assert body["landed_cost"]["USD"] == "11200.00"
    assert body["cost_per_unit"]["USD"] == "1.40"
    # Prompt listed "18.00"; the seed and hand calculation give 2460 / 13660 = 18.01%.
    assert body["gross_margin_pct"] == "18.01"
    assert body["markup_pct"] == "21.96"
    assert body["margin_band"] == "healthy"
    assert body["expected_revenue"]["USD"] == "13660.00"
    assert body["break_even_price_per_unit"]["USD"] == "1.40"
    assert body["landed_cost"]["BDT"] == "1373008.00"  # 11,200 x 122.59
    assert {(f["base"], f["quote"]) for f in body["fx"]} == {("USD", "BDT"), ("USD", "CNY")}
    shares = {line["kind"]: line["share_pct"] for line in body["breakdown"]}
    assert shares == {
        "GOODS": "85.71",
        "FREIGHT": "5.36",
        "INSURANCE": "0.45",
        "DUTY": "7.14",
        "BANK_CHARGES": "1.34",
    }
    first = body["explanations"][0]
    assert first["code"] == "LARGEST_EXTRA_COST" and first["en"].startswith("Duty")
    assert first["bn"]
    assert body["target"] is None


def test_target_margin_price(client: TestClient) -> None:
    res = login(client, RAHIMA).get(f"/analysis/orders/{MAIN}", params={"target_margin_pct": "20"})
    assert res.json()["target"]["price_per_unit"]["USD"] == "1.75"
    bad = client.get(f"/analysis/orders/{MAIN}", params={"target_margin_pct": "100"})
    assert bad.status_code == 422


def test_what_if_matches_domain_library(client: TestClient) -> None:
    lines = {"FREIGHT": "600", "INSURANCE": "50", "DUTY": "812.35", "OTHER": "17.5"}
    payload = {
        "currency": "USD",
        "goods_value": "9600",
        "quantity": "8000",
        "unit": "m",
        "cost_lines": [{"kind": k, "amount": v} for k, v in lines.items()],
        "selling_price_per_unit": "1.70",
        "target_margin_pct": "25",
    }
    body = login(client, KARIM).post("/analysis/landed-cost", json=payload).json()
    lc = landed_cost(
        Money.of("9600", "USD"),
        Decimal("8000"),
        [CostLine(k, Money.of(v, "USD")) for k, v in lines.items()],
    )
    m = gross_margin(Money(Decimal("1.70") * 8000, "USD"), lc.total)
    assert body["deal"] is None
    assert body["landed_cost"]["USD"] == f"{q2(lc.total.amount)}"
    assert body["extra_costs"]["USD"] == f"{q2(lc.extras.amount)}"
    assert body["gross_margin_pct"] == f"{pct(m.margin)}"  # type: ignore[arg-type]
    assert body["target"]["margin_pct"] == "25.00"


def test_what_if_rejects_floats_and_zero_quantity(client: TestClient) -> None:
    login(client, RAHIMA)
    base = {"goods_value": "100", "quantity": "10"}
    assert (
        client.post("/analysis/landed-cost", json={**base, "goods_value": 100.5}).status_code == 422
    )
    assert client.post("/analysis/landed-cost", json={**base, "quantity": "0"}).status_code == 422
    assert client.post("/analysis/landed-cost", json=base).status_code == 200


def test_buyer_cannot_read_another_buyers_deal(client: TestClient) -> None:
    res = login(client, RAHIMA).get("/analysis/orders/SETU-2026-0004")
    assert res.status_code == 403
    login(client, KARIM)
    assert client.get(f"/analysis/orders/{MAIN}").status_code == 403
    assert client.get("/analysis/orders/SETU-2026-0004").status_code == 200


def test_judge_and_admin_read_all_supplier_cannot(client: TestClient) -> None:
    login(client, "judge@demo.setu")
    assert client.get(f"/analysis/orders/{MAIN}").status_code == 200
    assert len(client.get("/analysis/orders").json()["orders"]) == 8
    login(client, "huaxin@demo.setu")
    assert client.get(f"/analysis/orders/{MAIN}").status_code == 403


def test_unknown_deal_404(client: TestClient) -> None:
    assert login(client, RAHIMA).get("/analysis/orders/SETU-1999-0001").status_code == 404


def test_order_list_is_scoped(client: TestClient) -> None:
    refs = [o["reference"] for o in login(client, RAHIMA).get("/analysis/orders").json()["orders"]]
    assert sorted(refs) == ["SETU-2025-0011", "SETU-2025-0019", "SETU-2026-0001", "SETU-2026-0006"]


def test_monthly_summary_rahima(client: TestClient) -> None:
    body = login(client, RAHIMA).get("/analysis/monthly").json()
    assert body["month"] == "2026-10"
    assert body["deals_count"] == 1  # the draft SETU-2026-0006 is excluded
    assert body["total_purchases"]["USD"] == "9600.00"
    assert body["total_landed_cost"]["USD"] == "11200.00"
    assert body["average_margin_pct"] == "18.01"
    assert body["top_cost_driver"]["kind"] == "DUTY"
    assert body["top_cost_driver"]["share_pct"] == "50.00"  # 800 of 1,600 extras
    assert body["previous"]["month"] == "2026-09" and body["previous"]["deals_count"] == 0
    assert body["change"]["purchases_pct"] is None
    assert [h["month"] for h in body["history"]][-1] == "2026-10" and len(body["history"]) == 6
    assert 2 <= len(body["insights"]) <= 3
    assert all(i["en"] and i["bn"] for i in body["insights"])


def test_monthly_summary_karim_september(client: TestClient) -> None:
    body = login(client, KARIM).get("/analysis/monthly", params={"month": "2026-09"}).json()
    assert body["deals_count"] == 2
    assert body["total_purchases"]["USD"] == "11700.00"  # 7,400 + 4,300
    assert body["total_landed_cost"]["USD"] == "14595.00"
    assert body["average_margin_pct"] == "12.60"


def test_monthly_scope_rules(client: TestClient) -> None:
    rahima_party = login(client, RAHIMA).get("/auth/me").json()["party_id"]
    login(client, KARIM)
    assert client.get("/analysis/monthly", params={"party_id": rahima_party}).status_code == 403
    login(client, "admin@demo.setu")
    assert client.get("/analysis/monthly").status_code == 400
    assert client.get("/analysis/monthly", params={"party_id": rahima_party}).status_code == 200
    assert client.get("/analysis/monthly", params={"month": "2026-13"}).status_code == 422


def test_supplier_scorecard_flags_huameng(client: TestClient) -> None:
    body = login(client, RAHIMA).get("/analysis/suppliers").json()
    by_code = {s["code"]: s for s in body["suppliers"]}
    assert set(by_code) == {"shaoxing-huaxin", "ningbo-brightline", "guangzhou-huameng"}
    huameng = by_code["guangzhou-huameng"]
    assert huameng["weak"] is True
    assert huameng["kyb_status"] == "WARNING"
    assert "KYB_NOT_VERIFIED" in huameng["flags"] and "LOW_SCORE" in huameng["flags"]
    assert Decimal(huameng["score"]) < 60
    assert not by_code["shaoxing-huaxin"]["weak"] and not by_code["ningbo-brightline"]["weak"]
    assert by_code["shaoxing-huaxin"]["your_deals_count"] == 3
    assert by_code["shaoxing-huaxin"]["completed_deals_count"] == 2
    assert [s["code"] for s in body["suppliers"]][-1] == "guangzhou-huameng"  # sorted by score
    assert len(huameng["score_trend"]) == 6


def test_supplier_cannot_use_calculator(client: TestClient) -> None:
    login(client, "huaxin@demo.setu")
    res = client.post("/analysis/landed-cost", json={"goods_value": "1", "quantity": "1"})
    assert res.status_code == 403


def test_scorecard_and_uuid_scope_rules(client: TestClient) -> None:
    karim_deal = login(client, "judge@demo.setu").get("/analysis/orders/SETU-2026-0004").json()
    supplier_party = (
        login(client, RAHIMA).get("/analysis/suppliers").json()["suppliers"][0]["supplier_id"]
    )
    assert client.get(f"/analysis/orders/{karim_deal['deal']['id']}").status_code == 403
    karim_party = login(client, KARIM).get("/auth/me").json()["party_id"]
    login(client, RAHIMA)
    assert client.get("/analysis/suppliers", params={"party_id": karim_party}).status_code == 403
    login(client, "admin@demo.setu")
    assert client.get("/analysis/monthly", params={"party_id": supplier_party}).status_code == 400
