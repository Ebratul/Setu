"""Agent tests run offline: mock mode on, tracing off, no network."""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_graph
from app.agent.mock_llm import compose_answer
from app.agent.models import ModelSet
from app.agent.nodes import AgentDeps
from app.agent.registry import ToolRegistry
from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import Role


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@dataclass
class Script:
    """What a ScriptedChatModel answers. `agent` replies are consumed in order by tool-bound
    calls; respond calls (no tools) use `respond` or the mock composer."""

    agent: list[AIMessage] = field(default_factory=list)
    respond: str | None = None
    route: dict[str, Any] | None = None
    router_error: bool = False
    fail_all: bool = False
    calls: list[tuple[tuple[str, ...], list[BaseMessage]]] = field(default_factory=list)

    def respond_prompts(self) -> list[list[BaseMessage]]:
        return [msgs for bound, msgs in self.calls if not bound]

    @property
    def agent_calls(self) -> int:
        return sum(1 for bound, _ in self.calls if bound)


class ScriptedChatModel(BaseChatModel):
    script: Any
    bound: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Runnable:
        return self.model_copy(update={"bound": tuple(t["name"] for t in tools)})

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kw: Any
    ) -> Runnable:
        script = self.script

        def route(value: Any) -> Any:
            if script.router_error or script.fail_all:
                raise RuntimeError("router model down")
            parsed = schema(**(script.route or {"intent": "cashflow", "needs_smart_model": False}))
            return {"raw": AIMessage(""), "parsed": parsed, "parsing_error": None}

        return RunnableLambda(route)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.script.calls.append((self.bound, messages))
        if self.script.fail_all:
            raise RuntimeError("model down")
        if self.bound:
            msg = self.script.agent.pop(0) if self.script.agent else AIMessage("READY")
        else:
            msg = AIMessage(self.script.respond or compose_answer(messages))
        msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        return ChatResult(generations=[ChatGeneration(message=msg)])


def tool_call(name: str, args: dict[str, Any] | None = None, call_id: str = "c1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}],
    )


def scripted_models(script: Script) -> ModelSet:
    fast, smart = ScriptedChatModel(script=script), ScriptedChatModel(script=script)
    return ModelSet(fast, smart, "fake-fast", "fake-smart")


@pytest.fixture
def buyer() -> CurrentUser:
    return CurrentUser(uuid.uuid4(), "rahima@demo.setu", "Rahima", Role.BUYER, "en", uuid.uuid4())


Runner = Callable[..., dict[str, Any]]


@pytest.fixture
def run_turn(buyer: CurrentUser) -> Runner:
    """Run one turn through a freshly built graph; returns the final state values."""

    def run(
        text: str,
        *,
        script: Script | None = None,
        registry: ToolRegistry | None = None,
        language: str | None = None,
        thread_tokens_before: int = 0,
        token_budget: int | None = None,
        graph: Any = None,
        thread_id: str = "t1",
        order: list[str] | None = None,
    ) -> dict[str, Any]:
        g = graph or build_graph(
            models=scripted_models(script) if script else None,
            registry=registry,
            checkpointer=InMemorySaver(),
            allowlist=(lambda _i: frozenset(registry.names)) if registry else None,
            token_budget=token_budget,
        )
        cfg = {"configurable": {"thread_id": thread_id, "deps": AgentDeps(buyer, None, thread_id)}}
        inp = {
            "messages": [HumanMessage(text)],
            "language": language,
            "thread_tokens_before": thread_tokens_before,
        }
        for update in g.stream(inp, cfg, stream_mode="updates"):
            if order is not None:
                order.extend(update)
        return g.get_state(cfg).values

    return run


def system_text(messages: list[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in messages if isinstance(m, SystemMessage))
