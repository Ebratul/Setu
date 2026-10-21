# ruff: noqa: F811  (fixtures imported from the API test conftest are used as arguments)
"""The remaining demo sets, run against the real API in demo mode (seeded sandbox data): each
screen accepts its values and shows the result the documentation promises."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import client, login, seeded_db  # noqa: F401  (fixtures)
from tests.synthetic.test_form_samples import (
    col,
    email_text,
    landed_cost,
    match,
    risk,
    tamper,
    whatif,
)

pytestmark = pytest.mark.db

VERDICT = {"No payment change found": "NO_PAYMENT_CHANGE_FOUND", "Blocked": "BLOCKED"}
DECISION = {
    "Allowed, Tier 1 (automatic)": ("ALLOW", 1),
    "Approval, Tier 2 (one tap)": ("REQUIRE_APPROVAL", 2),
    "Approval, Tier 3 (OTP + cooling-off)": ("REQUIRE_APPROVAL", 3),
    "Approval, Tier 3 (instruction in a document)": ("REQUIRE_APPROVAL", 3),
    "Blocked": ("BLOCK", 3),
}


@pytest.mark.parametrize("n", range(5))
def test_demo_login_users_exist(client: TestClient, n: int) -> None:
    res = client.post(
        "/auth/demo-login", json={"email": col("demo-login", n)["Email (sent by the button)"]}
    )
    assert res.status_code == 200, res.text


@pytest.mark.parametrize("n", range(5))
def test_email_check_verdict_matches_the_documentation(client: TestClient, n: int) -> None:
    c = col("email-check", n)
    res = login(client, "karim@demo.setu").post("/inbox/email-check", json={"text": email_text(c)})
    assert res.status_code == 200, res.text
    assert res.json()["verdict"] == VERDICT[c["Expected verdict"]]


@pytest.mark.parametrize("n", range(5))
def test_risk_playground_decision_matches_the_documentation(client: TestClient, n: int) -> None:
    c = col("risk-playground", n)
    res = login(client, "karim@demo.setu").post("/risk/evaluate", json=risk(c))
    assert res.status_code == 200, res.text
    assert (res.json()["decision"], res.json()["tier"]) == DECISION[c["Expected decision"]]


@pytest.mark.parametrize("n", range(5))
def test_landed_cost_and_target_margin(client: TestClient, n: int) -> None:
    buyer = login(client, "rahima@demo.setu")
    res = buyer.post("/analysis/landed-cost", json=landed_cost(col("landed-cost", n)))
    assert res.status_code == 200, res.text
    assert res.json()["gross_margin_pct"] is not None
    margin = col("target-margin", n)["Target margin (%)"]
    res = buyer.post(
        "/analysis/landed-cost",
        json={**landed_cost(col("landed-cost", 0)), "target_margin_pct": margin},
    )
    assert res.status_code == 200 and res.json()["target"] is not None, res.text


@pytest.mark.parametrize("n", range(5))
def test_monthly_summary_has_data(client: TestClient, n: int) -> None:
    c = col("monthly-summary", n)
    buyer = login(
        client,
        "rahima@demo.setu"
        if c["Business (admin or judge only)"] == "Rahima Knitwear"
        else "karim@demo.setu",
    )
    res = buyer.get("/analysis/monthly", params={"month": c["Month"]})
    assert res.status_code == 200, res.text
    assert res.json()["deals_count"] > 0, c


@pytest.mark.parametrize("n", range(5))
def test_financing_match_returns_options(client: TestClient, n: int) -> None:
    res = login(client, "rahima@demo.setu").post(
        "/financing/match", json=match(col("financing-match", n))
    )
    assert res.status_code == 200, res.text
    assert res.json()["options"], res.json()


@pytest.mark.parametrize("n", range(5))
def test_cashflow_what_if_runs(client: TestClient, n: int) -> None:
    buyer = login(client, "rahima@demo.setu")
    forecast = buyer.get("/cashflow/forecast").json()
    c = col("cashflow-whatif", n)
    body = whatif(c)
    if c["Move a payment: New date"]:
        first = next(f for d in forecast["daily"] for f in d["items"] if f["direction"] == "OUT")
        moved = timedelta(days=7)
        body["moves"] = [
            {"ref": first["ref"], "on": (date.fromisoformat(first["on"]) + moved).isoformat()}
        ]
    res = buyer.post("/cashflow/scenario", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["forecast"]["scenario"] is True


@pytest.mark.parametrize("n", range(5))
def test_payout_account_request_is_sent_to_the_buyer(client: TestClient, n: int) -> None:
    supplier = login(client, "huaxin@demo.setu")
    deals = supplier.get("/deals").json()
    deal = next(d for d in deals["deals"] if d["reference"] == "SETU-2026-0001")
    c = col("payout-account", n)
    res = supplier.post(
        "/supplier/accounts/change-request",
        json={
            "deal_id": deal["id"],
            "bank_name": c["Bank name"],
            "bank_country": c["Bank country (2 letters)"],
            "account_number": c["Account number"],
            "holder_name": c["Account holder name"],
            "account_type": c["Account type"].upper(),
            "currency": c["Currency"],
        },
    )
    assert res.status_code == 202, res.text
    assert res.json()["stage"] == "WAITING_BUYER"


@pytest.mark.parametrize("n", range(5))
def test_privacy_playground_masks_something(client: TestClient, n: int) -> None:
    c = col("privacy-playground", n)
    res = login(client, "judge@demo.setu").post(
        "/privacy/dry-run",
        json={"text": c["Text to protect"], "mask_amounts": c["Mask amounts"] == "yes"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["hits"], c["Text to protect"]


@pytest.mark.parametrize("n", range(5))
def test_attack_console_runs_the_gallery_item(client: TestClient, n: int) -> None:
    c = col("injection-console", n)
    res = login(client, "admin@demo.setu").post(
        "/security/injection/run",
        json={"attack_id": c["Attack gallery item"], "defences": c["Defences"] == "ON"},
    )
    assert res.status_code == 200, res.text


@pytest.mark.parametrize("n", range(5))
def test_audit_tamper_breaks_the_copy_not_the_log(client: TestClient, n: int) -> None:
    admin = login(client, "admin@demo.setu")
    res = admin.post("/audit/tamper-demo", json=tamper(col("audit-tamper", n)))
    assert res.status_code == 200, res.text
    assert res.json()["report"]["ok"] is False
    assert res.json()["real_table_changed"] is False
