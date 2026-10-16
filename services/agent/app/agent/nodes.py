"""Graph nodes: load_context → privacy_gateway → router → agent ⇄ tools → respond.

Nodes are `(state, config) -> partial update`. Request-scoped dependencies (DB session, user)
travel in `config["configurable"]["deps"]`; they are never checkpointed. Models, the tool
registry and limits are bound when the graph is built.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

import structlog
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import merge_configs
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.agent import prompts
from app.agent.intents import SMART_INTENTS, keyword_intent, needs_smart
from app.agent.models import ModelSet
from app.agent.persistence import deals_brief
from app.agent.registry import (
    INVALID_TOOL_NAME,
    TOOL_NAME,
    AllowList,
    ToolContext,
    ToolOutcome,
    ToolRegistry,
)
from app.agent.state import (
    AgentState,
    Intent,
    Lang,
    ToolCallRecord,
    ToolResult,
    Usage,
    add_usage,
    zero_usage,
)
from app.auth.deps import CurrentUser
from app.security import privacy_gateway
from app.services.scope import party

log = structlog.get_logger("setu.agent")

PRIOR_TURN_MESSAGES = 10
RESPOND_CONTEXT_MESSAGES = 6
MONEY_CLAIM = re.compile(
    r"\b(I|we|Setu)\s+(have\s+|has\s+|just\s+)?(released|transferred|paid|sent|approved)\b", re.I
)
SIMULATED_MARKERS = ("simulated", "সিমুলেটেড", "模拟")


@dataclass(frozen=True, slots=True)
class AgentDeps:
    user: CurrentUser
    db: Session | None
    thread_id: str


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    needs_smart_model: bool


def deps_of(config: RunnableConfig) -> AgentDeps:
    return cast(AgentDeps, config["configurable"]["deps"])


def usage_of(message: BaseMessage | None) -> Usage:
    meta = getattr(message, "usage_metadata", None) or {}
    return {
        "input_tokens": int(meta.get("input_tokens", 0)),
        "output_tokens": int(meta.get("output_tokens", 0)),
        "total_tokens": int(meta.get("total_tokens", 0)),
    }


def text_of(message: BaseMessage) -> str:
    return message.text if isinstance(message.content, list) else str(message.content)


def last_human(messages: list[AnyMessage]) -> HumanMessage | None:
    return next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)


def escape_prose(text: str) -> str:
    """Conversation and user text go into the respond prompt as data: no tags can be forged."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def render_tool_result(outcome: ToolOutcome) -> str:
    # "<" is escaped so data can never close the wrapper tag.
    payload = outcome.payload().replace("<", "\\u003c")
    ok = "true" if outcome.ok else "false"
    return (
        f'<tool_result name="{outcome.name}" ok="{ok}" untrusted="true">\n{payload}\n</tool_result>'
    )


class Nodes:
    def __init__(
        self,
        models: ModelSet,
        registry: ToolRegistry,
        allowlist: AllowList,
        max_tool_steps: int,
        token_budget: int,
    ) -> None:
        self.models = models
        self.registry = registry
        self.allowlist = allowlist
        self.max_tool_steps = max_tool_steps
        self.token_budget = token_budget

    # --- helpers ----------------------------------------------------------------------------

    def _over_budget(self, state: AgentState) -> bool:
        return state.thread_tokens_before + state.token_usage["total_tokens"] >= self.token_budget

    def _tools_for(self, intent: Intent | None) -> list[str]:
        return self.registry.llm_tools(self.allowlist(intent))

    @staticmethod
    def _tagged(config: RunnableConfig, state: AgentState, node: str) -> RunnableConfig:
        tags = [f"node:{node}", f"intent:{state.intent}", f"model:{state.model_used}"]
        return merge_configs(config, {"tags": tags})

    # --- nodes ------------------------------------------------------------------------------

    def load_context(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        d = deps_of(config)
        u = d.user
        party_name = None
        deals = []
        if d.db is not None and u.party_id is not None:
            party_name = party(d.db, u.party_id).legal_name
            deals = deals_brief(d.db, u.party_id)
        return {
            "user": {
                "id": str(u.id),
                "role": str(u.role),
                "party_id": str(u.party_id) if u.party_id else None,
                "display_name": u.display_name,
                "party_name": party_name,
            },
            "language": state.language or "en",
            "active_deals": deals,
            "turn_start": max(0, len(state.messages) - 1),
            "privacy_checked": False,
            "intent": None,
            "needs_smart_model": False,
            "model_tier": "fast",
            "model_used": None,
            "route_source": None,
            "pending_tool_calls": False,
            "tool_steps": 0,
            "tool_calls_made": [],
            "tool_results": [],
            "injection_flags": [],
            "token_usage": zero_usage(),
            "citations": [],
            "stop_reason": "budget" if state.thread_tokens_before >= self.token_budget else None,
            "answer": None,
        }

    def privacy_gateway(self, state: AgentState) -> dict[str, Any]:
        # TODO(P18): real masking. Wired here so no LLM call happens before the gateway.
        update: dict[str, Any] = {"privacy_checked": True}
        human = last_human(state.messages)
        if human is not None:
            masked = privacy_gateway.mask(text_of(human))
            if masked.changed:
                update["messages"] = [HumanMessage(content=masked.text, id=human.id)]
        return update

    def router(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        if state.stop_reason:
            return {}
        human = last_human(state.messages)
        text = text_of(human) if human else ""
        usage = zero_usage()
        try:
            structured = self.models.fast.with_structured_output(
                RouterDecision, method="json_schema", include_raw=True
            )
            res = structured.invoke(
                [SystemMessage(prompts.ROUTER_PROMPT), HumanMessage(text)],
                config=merge_configs(config, {"tags": ["node:router"]}),
            )
            parsed = res["parsed"] if isinstance(res, dict) else res
            if not isinstance(parsed, RouterDecision):
                raise ValueError("router returned no decision")
            decision, source = parsed, "model"
            usage = usage_of(res.get("raw") if isinstance(res, dict) else None)
        except Exception as exc:
            log.warning("router_fallback", error=type(exc).__name__)
            intent = keyword_intent(text)
            decision = RouterDecision(intent=intent, needs_smart_model=needs_smart(intent, text))
            source = "keywords"
        smart = decision.needs_smart_model or decision.intent in SMART_INTENTS
        tier = "smart" if smart else "fast"
        return {
            "intent": decision.intent,
            "needs_smart_model": smart,
            "model_tier": tier,
            "model_used": self.models.id_for(tier),
            "route_source": source,
            "token_usage": add_usage(state.token_usage, usage),
        }

    def _agent_history(self, state: AgentState) -> list[AnyMessage]:
        prior = [
            m
            for m in state.messages[: state.turn_start]
            if isinstance(m, HumanMessage)
            or (isinstance(m, AIMessage) and not m.tool_calls and text_of(m).strip())
        ]
        return [*prior[-PRIOR_TURN_MESSAGES:], *state.messages[state.turn_start :]]

    def agent(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        if self._over_budget(state):
            return {"stop_reason": "budget", "pending_tool_calls": False}
        if state.tool_steps >= self.max_tool_steps:
            return {"stop_reason": "tool_cap", "pending_tool_calls": False}
        user = state.user
        deals = ", ".join(f"{d['reference']}: {d['status']}" for d in state.active_deals) or "none"
        system = prompts.AGENT_PROMPT.format(
            user_name=user["display_name"] if user else "unknown",
            role=user["role"] if user else "unknown",
            party=f", business {user['party_name']}" if user and user["party_name"] else "",
            deals=deals,
            deal_focus=f"The user is looking at deal {state.deal_id}.\n" if state.deal_id else "",
            language=prompts.LANGUAGE_NAMES[cast(Lang, state.language or "en")],
        )
        model = self.models.for_tier(state.model_tier)
        names = self._tools_for(state.intent)
        bound = model.bind_tools(self.registry.definitions(names)) if names else model
        messages = [
            SystemMessage(f"{prompts.SYSTEM_PROMPT}\n\n{system}"),
            *self._agent_history(state),
        ]
        try:
            ai = bound.invoke(messages, config=self._tagged(config, state, "agent"))
        except Exception as exc:
            log.warning("agent_model_failed", error=type(exc).__name__)
            return {"stop_reason": "model_error", "pending_tool_calls": False}
        usage = add_usage(state.token_usage, usage_of(ai))
        if isinstance(ai, AIMessage) and ai.tool_calls:
            return {"messages": [ai], "pending_tool_calls": True, "token_usage": usage}
        return {"pending_tool_calls": False, "token_usage": usage}

    def tools(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        d = deps_of(config)
        ai = state.messages[-1]
        calls = ai.tool_calls if isinstance(ai, AIMessage) else []
        ctx = ToolContext(caller="llm", user=d.user, db=d.db, thread_id=d.thread_id)
        allowed = self.allowlist(state.intent)
        steps = state.tool_steps
        out: list[ToolMessage] = []
        records: list[ToolCallRecord] = list(state.tool_calls_made)
        results: list[ToolResult] = list(state.tool_results)
        flags: list[str] = list(state.injection_flags)
        for call in calls:
            name, args, call_id = call["name"], call.get("args") or {}, call.get("id") or ""
            if steps >= self.max_tool_steps:
                outcome = ToolOutcome(
                    name=name if TOOL_NAME.fullmatch(name or "") else INVALID_TOOL_NAME,
                    ok=False,
                    args_summary="",
                    error={"code": "tool_step_limit", "message": "tool step limit reached"},
                )
            else:
                outcome = self.registry.guard(name, args, ctx, config, allowed)
                steps += 1
            out.append(
                ToolMessage(
                    content=render_tool_result(outcome),
                    tool_call_id=call_id,
                    name=outcome.name,
                    status="success" if outcome.ok else "error",
                )
            )
            records.append(
                {
                    "id": call_id,
                    "name": outcome.name,
                    "args_summary": outcome.args_summary,
                    "ok": outcome.ok,
                    "error_code": (outcome.error or {}).get("code"),
                }
            )
            results.append({"name": outcome.name, "ok": outcome.ok, "payload": outcome.payload()})
            flags.extend(c for c in outcome.injection if c not in flags)
        stop = state.stop_reason
        if flags:
            stop = (
                "injection"  # SR-3: no further tool calls in a turn once data carried instructions
            )
        elif steps >= self.max_tool_steps:
            stop = "tool_cap"
        return {
            "messages": out,
            "tool_steps": steps,
            "tool_calls_made": records,
            "tool_results": results,
            "injection_flags": flags,
            "pending_tool_calls": False,
            "stop_reason": stop,
        }

    def _respond_input(self, state: AgentState) -> str:
        prior = [
            m
            for m in state.messages[: state.turn_start]
            if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and not m.tool_calls)
        ][-RESPOND_CONTEXT_MESSAGES:]
        parts: list[str] = []
        if prior:
            lines = [
                ("user: " if isinstance(m, HumanMessage) else "assistant: ")
                + escape_prose(text_of(m))
                for m in prior
            ]
            parts.append("<conversation>\n" + "\n".join(lines) + "\n</conversation>")
        user = state.user
        if user:
            deals = ", ".join(d["reference"] for d in state.active_deals) or "none"
            parts.append(f"User: {user['display_name']} ({user['role']}). Active deals: {deals}.")
        current = [m for m in state.messages[state.turn_start :] if isinstance(m, ToolMessage)]
        if current:
            parts.extend(text_of(m) for m in current)
        else:
            parts.append("(No tool results for this question.)")
        human = last_human(state.messages)
        parts.append("User's message:\n" + (escape_prose(text_of(human)) if human else ""))
        return "\n\n".join(parts)

    def _finalize(self, text: str, state: AgentState, lang: Lang) -> str:
        parts = [text.strip()]
        if any(r["ok"] for r in state.tool_results) and not any(
            m in text.lower() for m in SIMULATED_MARKERS
        ):
            parts.append(prompts.STATIC["simulated"][lang])
        if state.injection_flags:
            codes = ", ".join(state.injection_flags)
            parts.append(prompts.STATIC["injection"][lang].format(codes=codes))
        if state.stop_reason == "tool_cap":
            parts.append(prompts.STATIC["tool_cap"][lang])
        if MONEY_CLAIM.search(text):
            parts.append(prompts.STATIC["no_money_moved"][lang])
        return "\n\n".join(p for p in parts if p)

    def respond(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        lang = cast(Lang, state.language or "en")
        usage = state.token_usage
        stop = state.stop_reason
        if stop == "budget":
            answer = prompts.STATIC["budget"][lang]
        elif state.intent == "out_of_scope":
            answer = prompts.STATIC["out_of_scope"][lang]
        elif stop == "model_error" and not state.tool_results:
            answer = prompts.STATIC["model_error"][lang]
        else:
            messages = [
                SystemMessage(prompts.respond_system_prompt(lang, bool(state.injection_flags))),
                HumanMessage(self._respond_input(state)),
            ]
            try:
                ai = self.models.for_tier(state.model_tier).invoke(
                    messages, config=self._tagged(config, state, "respond")
                )
                text = text_of(ai)
                usage = add_usage(usage, usage_of(ai))
            except Exception as exc:
                log.warning("respond_model_failed", error=type(exc).__name__)
                text, stop = prompts.STATIC["model_error"][lang], "model_error"
            answer = self._finalize(text, state, lang)
        return {
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "token_usage": usage,
            "stop_reason": stop,
        }


# --- edges ----------------------------------------------------------------------------------

Route = Callable[[AgentState], str]


def after_router(state: AgentState) -> str:
    if state.stop_reason or state.intent in ("greeting", "out_of_scope"):
        return "respond"
    return "agent"


def after_agent(state: AgentState) -> str:
    return "tools" if state.pending_tool_calls else "respond"


def after_tools(state: AgentState) -> str:
    return "respond" if state.stop_reason else "agent"
