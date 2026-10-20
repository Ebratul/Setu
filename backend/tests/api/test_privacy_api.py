"""Privacy transparency API against the seeded world (mock model, real Postgres)."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import persistence
from app.config import get_settings
from app.db.models import ChatMessage, PrivacyRecord
from app.db.session import get_engine
from tests.api.conftest import login
from tests.api.test_chat_api import sse_events

pytestmark = pytest.mark.db

RAHIMA, KARIM, JUDGE = "rahima@demo.setu", "karim@demo.setu", "judge@demo.setu"
QUESTION = "আমার supplier-এর account নম্বর 6222 0021 4455 7788-এ কি টাকা যাবে? cash shortfall কত?"
RAW = ("6222 0021 4455 7788", "62220021445577", "1,560.00", "1560.00")


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()
    yield
    persistence.close_checkpointers()
    get_settings.cache_clear()


def record_count() -> int:
    with Session(get_engine()) as s:
        return s.scalar(select(func.count()).select_from(PrivacyRecord)) or 0


def test_chat_answer_is_correct_and_the_xray_shows_tokens(client: TestClient) -> None:
    c = login(client, RAHIMA)
    out = c.post("/chat", json={"message": QUESTION}).json()
    assert "1,560" in out["answer"] and "⟦" not in out["answer"]  # restored by code
    xray = c.get(f"/privacy/messages/{out['message_id']}").json()
    assert xray["available"] and xray["kind"] == "message"
    sent = "".join(s["text"] for b in xray["right"] for s in b["segments"])
    assert "⟦ACCT_1⟧" in sent
    for raw in RAW:
        assert raw not in sent
    left = "".join(s["text"] for b in xray["left"] for s in b["segments"])
    assert "6222 0021 4455 7788" in left  # the person sees their real text
    assert any(s["type"] == "ACCT" for b in xray["left"] for s in b["segments"])
    assert xray["stats"]["masked_by_type"]["ACCT"] == 1 and xray["stats"]["leaked_count"] == 0
    assert {b["node"] for b in xray["right"]} >= {"respond"}
    summary = c.get("/privacy/summary", params={"thread_id": out["thread_id"]}).json()
    assert summary["protected"] >= 2 and summary["leaked"] == 0


def test_stored_records_contain_no_raw_identifiers(client: TestClient) -> None:
    c = login(client, RAHIMA)
    c.post("/chat", json={"message": QUESTION + " NID 1990123456789 +8801711223344"})
    with Session(get_engine()) as s:
        blob = " ".join(
            r.masked_payload + (r.masked_output or "") for r in s.scalars(select(PrivacyRecord))
        )
    for raw in (*RAW, "1990123456789", "8801711223344", "01711223344"):
        assert raw not in blob


def test_stream_never_shows_tokens_and_ends_with_real_values(client: TestClient) -> None:
    c = login(client, RAHIMA)
    events = sse_events(c, {"message": QUESTION})
    text = "".join(d["text"] for e, d in events if e == "token")
    final = next(d for e, d in events if e == "final")
    assert "⟦" not in text and "⟦" not in final["answer"]
    assert final["answer"].startswith(text) and "1,560" in final["answer"]
    card = next(d["card"] for e, d in events if e == "tool_end")
    assert "1560.00" in json.dumps(card)  # cards keep real numbers


def test_history_and_follow_up_turns_keep_working(client: TestClient) -> None:
    c = login(client, RAHIMA)
    first = c.post("/chat", json={"message": QUESTION}).json()
    second = c.post(
        "/chat", json={"message": "and A/C 9999 8888 7777 now?", "thread_id": first["thread_id"]}
    ).json()
    xray = c.get(f"/privacy/messages/{second['message_id']}").json()
    sent = "".join(s["text"] for b in xray["right"] for s in b["segments"])
    assert "⟦ACCT_2⟧" in sent and "9999 8888 7777" not in sent  # new value, new token


def test_xray_is_private_to_the_owner(client: TestClient) -> None:
    out = login(client, RAHIMA).post("/chat", json={"message": QUESTION}).json()
    other = login(TestClient(client.app), KARIM)
    assert other.get(f"/privacy/messages/{out['message_id']}").status_code in (403, 404)
    assert other.get("/privacy/admin/overview").status_code == 403
    assert other.post("/privacy/dry-run", json={"text": "x"}).status_code == 403
    assert client.get("/privacy/messages/00000000-0000-0000-0000-000000000000").status_code == 404


def test_dry_run_masks_restores_and_stores_nothing(client: TestClient) -> None:
    c = login(client, JUDGE)
    before = record_count()
    text = "NID 1990123456789, A/C 6222 0021 4455 7788, USD 11,200.00, 0 1 7 1 1 2 2 3 3 4 4"
    body = c.post("/privacy/dry-run", json={"text": text, "mask_amounts": True}).json()
    assert body["simulated"] is True
    assert {h["type"] for h in body["hits"]} == {"NID", "ACCT", "AMT", "PHONE"}
    assert next(h for h in body["hits"] if h["type"] == "PHONE")["obfuscated"] is True
    assert "1990123456789" not in body["masked"] and "⟦NID_1⟧" in body["masked"]
    assert "1990123456789" in body["restored_answer"] and "⟦" not in body["restored_answer"]
    assert "".join(s["text"] for s in body["source_segments"]) == text
    off = c.post("/privacy/dry-run", json={"text": text, "mask_amounts": False}).json()
    assert "AMT" not in {h["type"] for h in off["hits"]}
    assert record_count() == before


def test_admin_overview_shows_zero_leaks(client: TestClient) -> None:
    login(client, RAHIMA).post("/chat", json={"message": QUESTION})
    ov = login(client, JUDGE).get("/privacy/admin/overview").json()
    assert ov["totals"]["protected"] > 0 and ov["totals"]["leaked"] == 0
    assert ov["by_type"]["ACCT"] >= 1 and len(ov["series"]) == 14
    assert ov["recent"] and len(ov["recent"]) <= 20
    assert ov["trace"]["enabled"] is False and ov["config"]["mask_amounts"] is True
    blob = " ".join(r["masked_payload"] for r in ov["recent"])
    assert "62220021445577" not in blob.replace(" ", "")


def test_numeric_answers_are_equally_correct_with_masking_on_and_off(client: TestClient) -> None:
    from app.privacy import eval as peval

    with Session(get_engine()) as s:
        result = peval.run_chat(s)
    assert result["on"]["correct"] == result["on"]["cases"] == result["off"]["correct"]


def test_assistant_messages_exist_for_history(client: TestClient) -> None:
    c = login(client, RAHIMA)
    out = c.post("/chat", json={"message": "hello"}).json()
    with Session(get_engine()) as s:
        assert s.get(ChatMessage, out["message_id"]) is not None


def test_roles_and_tenant_scoping(client: TestClient) -> None:
    judge = login(client, JUDGE)
    assert judge.post("/privacy/dry-run", json={"text": "x"}).status_code == 200
    assert judge.get("/privacy/admin/overview").status_code == 200
    # a buyer's gateway only knows values of parties that buyer can read
    from app.auth.deps import to_current
    from app.db.models import User
    from app.privacy.records import load_known

    with Session(get_engine()) as s:
        karim = to_current(s.scalars(select(User).where(User.email == KARIM)).one())
        everyone = load_known(s)
        scoped = load_known(s, karim)
    assert len(scoped["ACCT"]) < len(everyone["ACCT"])
    assert "Karim" in " ".join(scoped["NAME"]) or karim.display_name in scoped["NAME"]
