"""Chat API against the seeded demo world, mock model (offline), Postgres checkpointer."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.agent import persistence
from app.config import get_settings
from tests.api.conftest import login

pytestmark = pytest.mark.db

RAHIMA, KARIM, JUDGE = "rahima@demo.setu", "karim@demo.setu", "judge@demo.setu"


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()
    yield
    persistence.close_checkpointers()
    get_settings.cache_clear()


def chat(client: TestClient, message: str, **extra: object) -> dict:
    res = client.post("/chat", json={"message": message, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def sse_events(client: TestClient, body: dict) -> list[tuple[str, dict]]:
    with client.stream("POST", "/chat/stream", json=body) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert res.headers["x-accel-buffering"] == "no"
        raw = res.read().decode()
    events = []
    for block in raw.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_hello_works_offline(client: TestClient) -> None:
    out = chat(login(client, RAHIMA), "hello")
    assert out["intent"] == "greeting"
    assert out["model_used"] == "mock-fast"
    assert out["answer"].startswith("Hello")
    assert out["tool_calls"] == [] and out["trace_url"] is None
    assert out["simulated"] is True


def test_dashboard_answer_uses_tool_numbers(client: TestClient) -> None:
    out = chat(login(client, RAHIMA), "What's on my dashboard?")
    assert out["intent"] == "cashflow"
    assert out["tool_calls"] == [{"name": "get_dashboard_snapshot", "args_summary": "", "ok": True}]
    assert "1,560.00" in out["answer"] and "2026-11-07" in out["answer"]
    assert "simulated" in out["answer"].lower()
    assert "instruction-like" not in out["answer"], "real dashboard data must not look injected"
    assert out["usage"]["total_tokens"] > 0
    assert out["usage"]["thread_total"] == out["usage"]["total_tokens"]


def test_bangla_dashboard(client: TestClient) -> None:
    out = chat(login(client, RAHIMA), "আমার এই মাসে cash কম পড়বে?")
    assert out["language"] == "bn" and out["intent"] == "cashflow"
    assert "1,560.00" in out["answer"] and "ঘাটতি" in out["answer"]


def test_deal_summary_respects_buyer_isolation(client: TestClient) -> None:
    out = chat(login(client, RAHIMA), "status of SETU-2026-0001")
    assert out["tool_calls"][0]["ok"] is True and "SETU-2026-0001" in out["answer"]
    karim = chat(login(client, KARIM), "status of SETU-2026-0001")
    assert karim["tool_calls"][0]["ok"] is False
    assert "2,880" not in karim["answer"]
    res = client.post("/chat", json={"message": "hi", "deal_id": "SETU-2026-0001"})
    assert res.status_code == 404


def test_sse_emits_meta_tokens_final_in_order(client: TestClient) -> None:
    login(client, RAHIMA)
    events = sse_events(client, {"message": "What's on my dashboard?", "language": "en"})
    names = [e for e, _ in events]
    assert names[0] == "meta" and names[-1] == "final"
    assert names.index("tool_start") < names.index("tool_end") < names.index("token")
    tokens = [d["text"] for e, d in events if e == "token"]
    assert len(tokens) > 1
    final = events[-1][1]
    assert "".join(tokens) == final["answer"]
    assert events[0][1]["thread_id"] == final["thread_id"]
    assert events[0][1]["intent"] == "cashflow"


def test_sse_static_answer_still_streams_a_token(client: TestClient) -> None:
    login(client, RAHIMA)
    names = [e for e, _ in sse_events(client, {"message": "who won the football match"})]
    assert names == ["meta", "token", "final"]


def test_thread_persisted_and_resumable(client: TestClient) -> None:
    login(client, RAHIMA)
    first = chat(client, "What's on my dashboard?")
    tid = first["thread_id"]
    second = chat(client, "and how does escrow work?", thread_id=tid)
    assert second["thread_id"] == tid
    assert second["usage"]["thread_total"] > first["usage"]["thread_total"]
    msgs = client.get(f"/chat/threads/{tid}/messages").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "tool", "assistant", "user", "tool", "assistant"]
    assert msgs[1]["meta"]["tool"] == "get_dashboard_snapshot"
    assert '"1560.00"' in msgs[1]["content"]
    assert msgs[2]["meta"]["intent"] == "cashflow"
    threads = client.get("/chat/threads").json()["threads"]
    assert tid in [t["id"] for t in threads]

    from app.agent.graph import build_graph

    state = build_graph(checkpointer=persistence.get_checkpointer()).get_state(
        {"configurable": {"thread_id": tid}}
    )
    humans = [m.content for m in state.values["messages"] if m.type == "human"]
    assert humans == ["What's on my dashboard?", "and how does escrow work?"]


def test_thread_isolation(client: TestClient) -> None:
    tid = chat(login(client, RAHIMA), "hello")["thread_id"]
    rahima_id = client.get("/auth/me").json()["id"]
    login(client, KARIM)
    assert client.get(f"/chat/threads/{tid}/messages").status_code == 403
    assert client.post("/chat", json={"message": "hi", "thread_id": tid}).status_code == 403
    res = client.post("/chat/stream", json={"message": "hi", "thread_id": tid})
    assert res.status_code == 403
    assert client.get("/chat/threads", params={"user_id": rahima_id}).status_code == 403
    assert tid not in [t["id"] for t in client.get("/chat/threads").json()["threads"]]


def test_budget_exceeded_friendly_stop(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client, RAHIMA)
    tid = chat(client, "hello")["thread_id"]
    monkeypatch.setenv("THREAD_TOKEN_BUDGET", "10")
    get_settings.cache_clear()
    out = chat(client, "What's on my dashboard?", thread_id=tid)
    assert out["stopped"] == "budget"
    assert "usage limit" in out["answer"]
    assert out["tool_calls"] == []


def test_trace_url_only_for_admin_and_judge(client: TestClient) -> None:
    assert chat(login(client, JUDGE), "hello")["trace_url"] is None  # tracing off in tests
    assert client.post("/chat", json={"message": "  "}).status_code == 422
    assert client.post("/chat", json={"message": "x", "evil": 1}).status_code == 422


def test_chat_requires_login(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/chat", json={"message": "hello"}).status_code == 401


def _current(email: str):  # type: ignore[no-untyped-def]
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.auth.deps import to_current
    from app.db.models import User
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        return to_current(db.scalars(select(User).where(User.email == email)).one())


def _thread_tokens(thread_id: str) -> int:
    from sqlalchemy.orm import Session

    from app.db.models import ChatThread
    from app.db.session import get_engine

    with Session(get_engine()) as db:
        return db.get(ChatThread, thread_id).tokens_used  # type: ignore[union-attr]


def test_sse_disconnect_still_charges_tokens(client: TestClient) -> None:
    import uuid as _uuid

    from app.agent import runner
    from app.schemas.chat import ChatRequest

    tid = chat(login(client, RAHIMA), "hello")["thread_id"]
    before = _thread_tokens(tid)
    gen = runner.stream(
        _current(RAHIMA), ChatRequest(thread_id=_uuid.UUID(tid), message="What's on my dashboard?")
    )
    for frame in gen:
        if frame.startswith(b"event: token"):
            break
    gen.close()  # client went away before `final`
    assert _thread_tokens(tid) > before
    msgs = client.get(f"/chat/threads/{tid}/messages").json()["messages"]
    assert msgs[-1]["role"] == "assistant"
    assert msgs[-1]["meta"]["aborted"] == "disconnected_or_error"


def test_add_tokens_is_atomic_across_sessions(client: TestClient) -> None:
    from sqlalchemy.orm import Session

    from app.db.models import ChatThread
    from app.db.session import get_engine

    tid = chat(login(client, RAHIMA), "hello")["thread_id"]
    start = _thread_tokens(tid)
    with Session(get_engine()) as a, Session(get_engine()) as b:
        ta, tb = a.get(ChatThread, tid), b.get(ChatThread, tid)  # both read the same total
        persistence.add_tokens(a, ta, 100)  # type: ignore[arg-type]
        a.commit()
        persistence.add_tokens(b, tb, 50)  # type: ignore[arg-type]
        b.commit()
    assert _thread_tokens(tid) == start + 150


def test_trace_url_gated_by_role_when_tracing_on(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    from app.agent import runner

    monkeypatch.setattr(runner.tracing, "callbacks", lambda: [BaseCallbackHandler()])
    monkeypatch.setattr(runner.tracing, "langsmith_client", lambda: None)
    monkeypatch.setattr(runner.tracing, "tag_run", lambda *_a, **_k: None)
    monkeypatch.setattr(
        runner.tracing, "run_url", lambda run_id: f"https://smith.example/r/{run_id}"
    )
    assert chat(login(client, JUDGE), "hello")["trace_url"].startswith("https://smith.example/r/")
    assert chat(login(client, "admin@demo.setu"), "hello")["trace_url"]
    assert chat(login(client, RAHIMA), "hello")["trace_url"] is None


def test_dashboard_tool_has_no_party_oracle(client: TestClient) -> None:
    import uuid as _uuid

    from sqlalchemy.orm import Session

    from app.agent.registry import ToolContext
    from app.agent.tools.readonly import REGISTRY
    from app.db.session import get_engine

    rahima, karim = _current(RAHIMA), _current(KARIM)
    with Session(get_engine()) as db:
        ctx = ToolContext(caller="llm", user=rahima, db=db, thread_id="t")
        errors = {
            json.dumps(REGISTRY.guard("get_dashboard_snapshot", {"party_id": pid}, ctx).error)
            for pid in (str(karim.party_id), str(_uuid.uuid4()), "not-a-uuid")
        }
        assert len(errors) == 1 and '"not_found"' in errors.pop()
        own = REGISTRY.guard("get_dashboard_snapshot", {"party_id": str(rahima.party_id)}, ctx)
        assert own.ok


def test_tool_db_error_is_graceful_and_turn_is_saved() -> None:
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from pydantic import BaseModel, ConfigDict
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.agent.graph import build_graph
    from app.agent.nodes import AgentDeps
    from app.agent.registry import ToolContext, ToolRegistry
    from app.db.session import get_engine
    from app.security.tiers import Tier

    class NoArgs(BaseModel):
        model_config = ConfigDict(extra="forbid")

    reg = ToolRegistry()

    @reg.tool(name="get_dashboard_snapshot", tier=Tier.T0, args_schema=NoArgs, output_schema=NoArgs)
    def broken(args: NoArgs, ctx: ToolContext) -> NoArgs:
        """Broken tool."""
        ctx.db.execute(text("SELECT * FROM no_such_table"))  # type: ignore[union-attr]
        return NoArgs()

    user = _current(RAHIMA)
    with Session(get_engine()) as db:
        g = build_graph(registry=reg, checkpointer=InMemorySaver())
        cfg = {"configurable": {"thread_id": "x", "deps": AgentDeps(user, db, "x")}}
        g.invoke({"messages": [HumanMessage("What's on my dashboard?")], "language": "en"}, cfg)
        values = g.get_state(cfg).values
        assert values["tool_calls_made"][0]["error_code"] == "tool_failed"
        assert "won't guess" in values["answer"]
        assert db.execute(text("SELECT 1")).scalar() == 1  # session still usable
