"""Record/replay of model calls: stable keys, hit, miss, record, strict runs."""

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field

from app.agent.mock_llm import MockChatModel
from app.config import get_settings
from app.llm import replay


class Decision(BaseModel):
    intent: str
    needs_smart_model: bool = False


class FakeReal(BaseChatModel):
    """Stands in for a provider model; counts the calls it receives."""

    calls: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-real"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self.model_copy(update={})

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        self.calls.append(str(messages[-1].content))
        msg = AIMessage(content=f"real answer to: {messages[-1].content}")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        from langchain_core.runnables import RunnableLambda

        def run(value: Any) -> Any:
            self.calls.append("structured")
            parsed = schema(intent="analysis", needs_smart_model=True)
            return {"raw": AIMessage(content=""), "parsed": parsed, "parsing_error": None}

        return RunnableLambda(run)


@pytest.fixture
def fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path))
    get_settings.cache_clear()
    return tmp_path


def model(real: BaseChatModel | None = None) -> replay.ReplayChatModel:
    return replay.wrap(real, "claude-haiku-5-5", fallback=MockChatModel(model_name="mock-fast"))


def msgs(text: str = "total cost?") -> list[Any]:
    return [SystemMessage("You are Setu."), HumanMessage(text)]


def test_keys_ignore_ids_and_timestamps_but_not_content() -> None:
    def key(wrap_id: str, ts: str, uid: str, text: str = "x") -> str:
        body = (
            f'<untrusted src="tool:a" id="{wrap_id}">{{"at": "{ts}", "id": "{uid}", "n": "{text}"}}'
            f'</untrusted id="{wrap_id}">'
        )
        return replay.fixture_key("chat", "m", [SystemMessage("s"), HumanMessage(body)], ["a"])

    base = key("f43d", "2026-10-20T04:25:16.749892Z", "989e0a9b-9c87-4fc1-83bd-0865a169592a")
    assert base == key("46db", "2026-10-21 09:00:01+06:00", "11111111-2222-3333-4444-555555555555")
    assert base != key("f43d", "2026-10-20T04:25:16Z", "989e0a9b-9c87-4fc1-83bd-0865a169592a", "y")
    assert base != replay.fixture_key("chat", "other-model", [SystemMessage("s")], ["a"])
    assert replay.fixture_key("chat", "m", [HumanMessage("a")], ["t1"]) != replay.fixture_key(
        "chat", "m", [HumanMessage("a")], ["t2"]
    )
    assert replay.fixture_key("chat", "m", [HumanMessage("a")]) != replay.fixture_key(
        "structured", "m", [HumanMessage("a")]
    )


def test_tool_calls_are_part_of_the_key() -> None:
    ai1 = AIMessage(content="", tool_calls=[{"name": "t", "args": {"a": 1}, "id": "call_aaaaaa"}])
    ai2 = AIMessage(content="", tool_calls=[{"name": "t", "args": {"a": 1}, "id": "call_bbbbbb"}])
    ai3 = AIMessage(content="", tool_calls=[{"name": "t", "args": {"a": 2}, "id": "call_aaaaaa"}])
    k = lambda ai: replay.fixture_key(  # noqa: E731
        "chat", "m", [HumanMessage("q"), ai, ToolMessage("r", tool_call_id=ai.tool_calls[0]["id"])]
    )
    assert k(ai1) == k(ai2) != k(ai3)


def test_record_then_replay_without_the_real_model(fixtures: Path) -> None:
    real = FakeReal()
    with replay.forced_mode("record"), replay.strict_run() as run:
        first = model(real).invoke(msgs())
    assert first.content == "real answer to: total cost?" and real.calls == ["total cost?"]
    assert len(run.hits) == 1
    files = list(fixtures.glob("llm/*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["source"] == "real" and saved["model"] == "claude-haiku-5-5"
    assert saved["request"]["last_user"] == "total cost?"

    # offline: no real model at all
    with replay.forced_mode("replay"), replay.strict_run() as run:
        again = model(None).invoke(msgs())
    assert again.content == first.content and run.misses == [] and len(run.hits) == 1
    assert real.calls == ["total cost?"]  # not called again


def test_a_miss_is_counted_and_answered_offline(fixtures: Path) -> None:
    with replay.forced_mode("replay"), replay.strict_run() as run:
        out = model(None).invoke(msgs("something nobody recorded"))
    assert isinstance(out, AIMessage)  # the deterministic offline model answered
    assert len(run.misses) == 1 and run.misses[0]["kind"] == "chat"
    assert "nobody recorded" in run.misses[0]["last_user"]


def test_structured_output_round_trip(fixtures: Path) -> None:
    real = FakeReal()
    with replay.forced_mode("record"):
        got = (
            model(real).with_structured_output(Decision, include_raw=True).invoke(msgs("route me"))
        )
    assert got["parsed"] == Decision(intent="analysis", needs_smart_model=True)
    with replay.forced_mode("replay"), replay.strict_run() as run:
        plain = model(None).with_structured_output(Decision).invoke(msgs("route me"))
        raw = (
            model(None).with_structured_output(Decision, include_raw=True).invoke(msgs("route me"))
        )
    assert plain == Decision(intent="analysis", needs_smart_model=True)
    assert raw["parsed"] == plain and run.misses == []
    with replay.forced_mode("replay"), replay.strict_run() as run:
        model(None).with_structured_output(Decision).invoke(msgs("different"))
    assert run.misses and run.misses[0]["kind"] == "structured"


def test_streaming_replays_the_text_in_pieces(fixtures: Path) -> None:
    real = FakeReal()
    with replay.forced_mode("record"):
        model(real).invoke(msgs("stream me"))
    with replay.forced_mode("replay"):
        chunks = list(model(None).stream(msgs("stream me")))
    assert "".join(str(c.content) for c in chunks) == "real answer to: stream me"
    assert len(chunks) >= 4


def test_off_mode_is_the_plain_model(fixtures: Path) -> None:
    real = FakeReal()
    with replay.forced_mode("off"):
        out = model(real).invoke(msgs("plain"))
    assert out.content == "real answer to: plain" and not list(fixtures.glob("llm/*.json"))


def test_record_without_a_real_model_fails_loudly(fixtures: Path) -> None:
    with replay.forced_mode("record"), pytest.raises(replay.ReplayError):
        model(None).invoke(msgs())


def test_a_fixture_for_another_key_is_not_served(fixtures: Path) -> None:
    key = replay.fixture_key("chat", "claude-haiku-5-5", msgs())
    replay.save_fixture(
        {
            "key": "0" * 64,
            "kind": "chat",
            "model": "m",
            "response": {"content": "x"},
            "source": "real",
        }
    )
    assert replay.load_fixture(key) is None
    path = replay.fixture_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": "f" * 64, "kind": "chat"}), encoding="utf-8")
    assert replay.load_fixture(key) is None  # same filename prefix, different key: refused


def test_mode_follows_the_sandbox_and_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import datetime
    import uuid

    from app.demo.context import SandboxInfo, use_sandbox

    assert replay.current_mode() == "off"
    monkeypatch.setenv("DEMO_REPLAY", "true")
    get_settings.cache_clear()
    assert replay.current_mode() == "replay"
    exp = datetime.datetime.now(datetime.UTC)
    with use_sandbox(SandboxInfo(uuid.uuid4(), "sbx_0123456789ab", True, exp)):
        assert replay.current_mode() == "live"
    with use_sandbox(SandboxInfo(uuid.uuid4(), "sbx_0123456789ab", False, exp)):
        assert replay.current_mode() == "replay"
    monkeypatch.setenv("DEMO_RECORD", "true")
    get_settings.cache_clear()
    assert replay.current_mode() == "record"
