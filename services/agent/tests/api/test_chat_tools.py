"""P09 finance tools against the seeded demo world (DEMO_TODAY 2026-10-20), plus the chat API
additions (cards in SSE/final/history, feedback, rename/delete/search). Mock model, no network."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import persistence
from app.agent.registry import ToolContext, ToolOutcome, default_registry
from app.auth.deps import CurrentUser, to_current
from app.config import get_settings
from app.db.models import User
from app.db.session import get_engine
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM = "rahima@demo.setu", "karim@demo.setu"
DEAL = "SETU-2026-0001"
M2 = "2026-11-07"


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()
    yield
    persistence.close_checkpointers()
    get_settings.cache_clear()


@pytest.fixture
def db(seeded_db: str) -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s


def user(db: Session, email: str) -> CurrentUser:
    return to_current(db.scalars(select(User).where(User.email == email)).one())


def run(
    db: Session, email: str, name: str, args: dict[str, Any] | None = None, **ctx: Any
) -> ToolOutcome:
    c = ToolContext(caller="llm", user=user(db, email), db=db, thread_id="t", **ctx)
    return default_registry().guard(name, args or {}, c)


def card(out: ToolOutcome, card_type: str) -> dict[str, Any]:
    assert out.ok, out.error
    assert out.data is not None and out.data["card_type"] == card_type
    assert out.data["simulated"] is True
    assert out.data["explanation_en"] and out.data["explanation_bn"]
    assert out.injection == [], "our own card text must not look like an instruction"
    return out.data["data"]


def test_analyze_order_landed_cost(db: Session) -> None:
    d = card(run(db, RAHIMA, "analyze_order", {"deal_id": DEAL}), "landed_cost")
    assert d["landed_cost"] == "11200.00" and d["currency"] == "USD"
    assert d["cost_per_unit"] == "1.40" and d["gross_margin_pct"] == "18.01"
    assert d["defaulted_deal"] is False
    assert d["analysis_route"] == f"/app/orders/{DEAL}/analysis"
    assert sum(1 for line in d["lines"] if line["kind"] == "GOODS") == 1


def test_analyze_order_defaults_to_active_deal(db: Session) -> None:
    d = card(run(db, RAHIMA, "analyze_order"), "landed_cost")
    assert d["deal_ref"] == DEAL and d["defaulted_deal"] is True
    scoped = card(run(db, RAHIMA, "analyze_order", deal_ref=DEAL), "landed_cost")
    assert scoped["defaulted_deal"] is False


def test_forecast_cashflow_shortfall(db: Session) -> None:
    d = card(run(db, RAHIMA, "forecast_cashflow"), "cashflow")
    assert d["before"]["first_shortfall"] == {"on": M2, "amount": "1560.00"}
    assert d["before"]["lowest_balance"] == "-3835.00"
    assert len(d["before"]["series"]) == 91  # inclusive window: today + 90 days
    assert d["after"] is None and d["upcoming"]


def test_simulated_loan_clears_the_m2_shortfall(db: Session) -> None:
    out = run(
        db,
        RAHIMA,
        "simulate_cashflow_scenario",
        {"loans": [{"amount": "1560.00", "on": "2026-11-05"}]},
    )
    d = card(out, "cashflow")
    assert d["before"]["first_shortfall"]["on"] == M2
    assert d["after"]["first_shortfall"] is None or d["after"]["first_shortfall"]["on"] != M2
    assert "SHORTFALL_CLEARED" in out.data["explanation_codes"]  # type: ignore[index]


def test_get_alerts_has_shortfall_with_safe_route(db: Session) -> None:
    d = card(run(db, RAHIMA, "get_alerts"), "alerts")
    [sf] = [a for a in d["alerts"] if a["type"] == "SHORTFALL"]
    assert sf["amount"] == "1560.00"
    assert sf["route"].startswith("/app/financing?")
    severities = [a["severity"] for a in d["alerts"]]
    order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    assert severities == sorted(severities, key=order.__getitem__)


def test_match_financing_order_ranking(db: Session) -> None:
    d = card(
        run(db, RAHIMA, "match_financing", {"deal_id": DEAL, "mode": "order"}),
        "financing_comparison",
    )
    assert d["amount"] == "5200.00"
    eligible = [(o["code"], o["kind"], o["total_cost"]) for o in d["options"] if o["eligible"]]
    costs = [c for _, _, c in eligible]
    assert costs[:3] == ["97.70", "104.00", "173.45"]
    assert d["options"][0]["recommended"] is True
    assert d["recommended"]["total_cost"] == "97.70" and d["recommended"]["reasons"]
    assert any(not o["eligible"] and o["why_not"] for o in d["options"])
    assert d["apply_route"] == f"/app/financing?deal={DEAL}&mode=order"


def test_match_financing_shortfall_uses_the_shortfall_deal(db: Session) -> None:
    d = card(run(db, RAHIMA, "match_financing"), "financing_comparison")
    assert d["mode"] == "shortfall" and d["amount"] == "1560.00" and d["deal_ref"] == DEAL
    assert d["recommended"]["total_cost"] == "31.20"


def test_financing_impact_before_after(db: Session) -> None:
    match = card(run(db, RAHIMA, "match_financing"), "financing_comparison")
    code = match["recommended"]["code"]
    d = card(
        run(db, RAHIMA, "financing_impact", {"option_id": code, "amount": "1560.00"}), "cashflow"
    )
    assert d["before"]["first_shortfall"]["on"] == M2
    assert d["after"] is not None and d["scenario_label"] == code
    assert d["after"]["first_shortfall"] is None or d["after"]["first_shortfall"]["on"] != M2


def test_compare_fx_route_next_milestone_and_amount(db: Session) -> None:
    d = card(run(db, RAHIMA, "compare_fx_route"), "fx_compare")
    assert d["basis"].endswith(DEAL) and d["payer_currency"] == "BDT"
    assert d["cheaper"] in ("USD", "CNY") and float(d["saving"]) >= 0
    d2 = card(
        run(db, RAHIMA, "compare_fx_route", {"amount": "5760", "to_currency": "USD"}), "fx_compare"
    )
    assert d2["invoice_amount"] == "5760.00" and d2["supplier_receives_cny"] == "40890.24"
    assert d2["cheaper"] == "CNY"
    assert len(d2["assumptions"]) == 5


def test_monthly_summary_and_scorecard(db: Session) -> None:
    m = card(run(db, RAHIMA, "get_monthly_summary", {"month": "2026-10"}), "monthly_summary")
    assert m["deals_count"] == 1 and m["total_landed_cost"] == "11200.00"
    assert m["average_margin_pct"] == "18.01"
    s = card(run(db, RAHIMA, "get_supplier_scorecard"), "scorecard")
    scores = {x["name"].split()[0]: x["score"] for x in s["suppliers"]}
    assert scores["Shaoxing"] == "96.25"
    assert any(x["weak"] for x in s["suppliers"])


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("analyze_order", {"deal_id": DEAL}),
        ("match_financing", {"deal_id": DEAL, "mode": "order"}),
        ("financing_impact", {"deal_id": DEAL, "option_id": "SUPPLIER_CREDIT", "amount": "100"}),
        ("compare_fx_route", {"deal_id": DEAL}),
    ],
)
def test_karim_cannot_use_rahimas_deal(db: Session, name: str, args: dict[str, Any]) -> None:
    out = run(db, KARIM, name, args)
    assert out.ok is False and out.error == {"code": "not_found", "message": "deal not found"}


def test_karim_scope_from_chat_is_also_isolated(db: Session) -> None:
    out = run(db, KARIM, "analyze_order", deal_ref=DEAL)
    assert out.error["code"] == "not_found"  # type: ignore[index]


def test_what_if_landed_cost(db: Session) -> None:
    out = run(
        db,
        RAHIMA,
        "landed_cost_what_if",
        {
            "goods_value": "9600",
            "quantity": "8000",
            "unit": "m",
            "cost_lines": [{"kind": "FREIGHT", "amount": "500"}],
            "selling_price": "1.70",
        },
    )
    d = card(out, "landed_cost")
    assert d["landed_cost"] == "10100.00" and d["deal_ref"] is None


# --- API -------------------------------------------------------------------------------------


def sse_events(client: TestClient, body: dict) -> list[tuple[str, dict]]:
    with client.stream("POST", "/chat/stream", json=body) as res:
        assert res.status_code == 200
        raw = res.read().decode()
    out = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_cards_in_sse_final_and_history(client: TestClient) -> None:
    login(client, RAHIMA)
    events = sse_events(client, {"message": "আমার কি এই মাসে cash কম পড়বে?"})
    [tool_end] = [d for e, d in events if e == "tool_end"]
    assert tool_end["name"] == "forecast_cashflow" and tool_end["card"]["card_type"] == "cashflow"
    final = events[-1][1]
    assert final["language"] == "bn"
    assert final["cards"][0]["data"]["before"]["first_shortfall"]["amount"] == "1560.00"
    assert final["why"].startswith("কারণ:") and final["why"] in final["answer"]
    assert final["notes"] and final["message_id"]
    msgs = client.get(f"/chat/threads/{final['thread_id']}/messages").json()["messages"]
    tool = next(m for m in msgs if m["role"] == "tool")
    assert tool["card"]["card_type"] == "cashflow"
    assistant = msgs[-1]
    assert assistant["id"] == final["message_id"] and assistant["meta"]["why"] == final["why"]


def test_feedback_rename_search_delete(client: TestClient) -> None:
    login(client, RAHIMA)
    out = client.post("/chat", json={"message": "Which financing option is cheapest?"}).json()
    tid, mid = out["thread_id"], out["message_id"]
    assert out["cards"][0]["card_type"] == "financing_comparison"

    res = client.post(f"/chat/messages/{mid}/feedback", json={"rating": "up"})
    assert res.status_code == 200 and res.json()["rating"] == "up"
    msgs = client.get(f"/chat/threads/{tid}/messages").json()["messages"]
    assert msgs[-1]["meta"]["feedback"]["rating"] == "up"
    assert client.post(f"/chat/messages/{mid}/feedback", json={"rating": "meh"}).status_code == 422

    assert (
        client.patch(f"/chat/threads/{tid}", json={"title": "  Loan  options "}).json()["title"]
        == "Loan options"
    )
    found = client.get("/chat/threads", params={"q": "loan"}).json()["threads"]
    assert [t["id"] for t in found] == [tid]
    assert client.get("/chat/threads", params={"q": "%"}).json()["threads"] == []

    assert (
        client.post(
            f"/chat/messages/{mid}/feedback", json={"rating": "up", "comment": "x" * 501}
        ).status_code
        == 422
    )
    user_msg = client.get(f"/chat/threads/{tid}/messages").json()["messages"][0]
    assert user_msg["role"] == "user"
    assert (
        client.post(f"/chat/messages/{user_msg['id']}/feedback", json={"rating": "up"}).status_code
        == 404
    )

    login(client, KARIM)
    # someone else's message looks exactly like a missing one
    assert client.post(f"/chat/messages/{mid}/feedback", json={"rating": "down"}).status_code == 404
    assert client.patch(f"/chat/threads/{tid}", json={"title": "x"}).status_code == 403
    assert client.delete(f"/chat/threads/{tid}").status_code == 403

    login(client, RAHIMA)
    assert client.delete(f"/chat/threads/{tid}").status_code == 204
    assert client.get(f"/chat/threads/{tid}/messages").status_code == 404
    saver = persistence.get_checkpointer()
    assert saver.get_tuple({"configurable": {"thread_id": tid}}) is None


def test_financing_impact_unknown_option(db: Session) -> None:
    out = run(db, RAHIMA, "financing_impact", {"option_id": "NO_SUCH_OPTION", "amount": "100"})
    assert out.ok is False and out.error["code"] == "not_found"  # type: ignore[index]


def test_admin_gets_clean_error_without_buyer_data(db: Session) -> None:
    out = run(db, "admin@demo.setu", "forecast_cashflow")
    assert out.ok is False and out.error["code"] == "bad_request"  # type: ignore[index]


def test_finance_tools_write_nothing(db: Session) -> None:
    from sqlalchemy import text

    tables = [
        "financing_applications",
        "cashflow_items",
        "alerts",
        "fx_locks",
        "approval_requests",
        "ledger_entries",
        "escrow_accounts",
        "milestones",
        "deals",
    ]

    def counts() -> dict[str, int]:
        return {t: db.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables}

    before = counts()
    code = card(run(db, RAHIMA, "match_financing"), "financing_comparison")["recommended"]["code"]
    calls = [
        ("analyze_order", {}),
        ("forecast_cashflow", {}),
        ("get_alerts", {}),
        ("match_financing", {}),
        ("match_financing", {"mode": "order"}),
        ("financing_impact", {"option_id": code, "amount": "1560.00"}),
        ("simulate_cashflow_scenario", {"loans": [{"amount": "1560.00", "on": "2026-11-05"}]}),
        ("compare_fx_route", {}),
        ("get_monthly_summary", {}),
        ("get_supplier_scorecard", {}),
        ("landed_cost_what_if", {"goods_value": "100", "quantity": "10"}),
    ]
    for name, args in calls:
        assert run(db, RAHIMA, name, args).ok, name
    db.rollback()
    assert counts() == before
