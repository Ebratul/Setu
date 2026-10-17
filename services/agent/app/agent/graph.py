"""build_graph(): the LangGraph agent.

    load_context → privacy_gateway → router ─┬─→ agent ⇄ tools
                                              │      ↓
                                              └──→ respond → END
(greeting, out_of_scope and budget stops go straight from router to respond.)
"""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.models import ModelSet, get_models
from app.agent.nodes import Nodes, after_agent, after_router, after_tools
from app.agent.registry import AllowList, ToolRegistry, default_registry, intent_allowlist
from app.agent.state import AgentState
from app.config import get_settings

NODE_ORDER = ("load_context", "privacy_gateway", "router", "agent", "tools", "respond")


def build_graph(
    *,
    models: ModelSet | None = None,
    registry: ToolRegistry | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    allowlist: AllowList | None = None,
    max_tool_steps: int | None = None,
    token_budget: int | None = None,
) -> CompiledStateGraph:
    settings = get_settings()
    nodes = Nodes(
        models=models or get_models(),
        registry=registry or default_registry(),
        allowlist=allowlist or intent_allowlist,
        max_tool_steps=max_tool_steps or settings.agent_max_tool_steps,
        token_budget=token_budget or settings.thread_token_budget,
    )
    g = StateGraph(AgentState)
    g.add_node("load_context", nodes.load_context)
    g.add_node("privacy_gateway", nodes.privacy_gateway)
    g.add_node("router", nodes.router)
    g.add_node("agent", nodes.agent)
    g.add_node("tools", nodes.tools)
    g.add_node("respond", nodes.respond)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "privacy_gateway")
    g.add_edge("privacy_gateway", "router")
    g.add_conditional_edges("router", after_router, {"agent": "agent", "respond": "respond"})
    g.add_conditional_edges("agent", after_agent, {"tools": "tools", "respond": "respond"})
    g.add_conditional_edges("tools", after_tools, {"agent": "agent", "respond": "respond"})
    g.add_edge("respond", END)
    return g.compile(checkpointer=checkpointer, name="setu-agent")
