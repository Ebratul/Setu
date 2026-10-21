"""A tracer attached to the graph (what LangSmith would be) never receives a raw identifier."""

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_graph
from app.agent.nodes import AgentDeps
from app.privacy.gateway import PrivacyGateway
from tests.agent.conftest import Script, scripted_models, tool_call
from tests.agent.test_graph import fake_registry

RAW = (
    "6222 0021 4455 7788",
    "62220021445577",
    "+8801711223344",
    "1990123456789",
    "1,560.00",
    "1560.00",
    "6000.00",
    "8640.00",
)
QUESTION = (
    "আমার supplier-এর account নম্বর 6222 0021 4455 7788-এ কি টাকা যাবে? "
    "NID 1990123456789, ফোন +8801711223344. What's on my dashboard?"
)


class FakeTracer(BaseCallbackHandler):
    """Records everything a tracing backend would be sent."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def on_chain_start(self, serialized: Any, inputs: Any, **kw: Any) -> None:
        self.seen.append(repr(inputs))

    def on_chain_end(self, outputs: Any, **kw: Any) -> None:
        self.seen.append(repr(outputs))

    def on_chat_model_start(self, serialized: Any, messages: Any, **kw: Any) -> None:
        self.seen.append(repr(messages))

    def on_llm_end(self, response: Any, **kw: Any) -> None:
        self.seen.append(repr(response))

    def on_tool_start(self, serialized: Any, input_str: Any, **kw: Any) -> None:
        self.seen.append(repr(input_str))

    def on_tool_end(self, output: Any, **kw: Any) -> None:
        self.seen.append(repr(output))


def test_tracer_receives_only_tokens(buyer) -> None:  # type: ignore[no-untyped-def]
    script = Script(agent=[tool_call("get_dashboard_snapshot")])
    registry = fake_registry([])
    g = build_graph(
        models=scripted_models(script),
        registry=registry,
        checkpointer=InMemorySaver(),
        allowlist=lambda _i: frozenset(registry.names),
    )
    gw = PrivacyGateway()
    tracer = FakeTracer()
    cfg = {
        "configurable": {"thread_id": "t", "deps": AgentDeps(buyer, None, "t", gw)},
        "callbacks": [tracer],
    }
    g.invoke({"messages": [HumanMessage(gw.mask_text(QUESTION))]}, cfg)
    trace = "\n".join(tracer.seen)
    assert tracer.seen and "⟦ACCT_1⟧" in trace
    for raw in RAW:
        assert raw not in trace, raw
    # ...while the person still gets real values back, restored by code
    state = g.get_state(cfg).values
    assert "1,560.00" not in state["answer"] and "⟦AMT_" in state["answer"]
    assert "1,560.00" in gw.unmask(state["answer"])
    # every model call is recorded masked, with zero leaks
    assert len(gw.calls) >= 2
    assert all(c.stats.leaked_count == 0 for c in gw.calls)
    assert all(raw not in c.payload for c in gw.calls for raw in RAW)
