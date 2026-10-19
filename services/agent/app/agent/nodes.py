"""Graph nodes: load_context → privacy_gateway → router → agent ⇄ tools → respond.

Nodes are `(state, config) -> partial update`. Request-scoped dependencies (DB session, user)
travel in `config["configurable"]["deps"]`; they are never checkpointed. Models, the tool
registry and limits are bound when the graph is built.
"""

import html
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
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
from sqlalchemy import select
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
    args_summary,
)
from app.agent.state import (
    AgentState,
    Intent,
    Lang,
    SecurityCheck,
    ToolCallRecord,
    ToolResult,
    Usage,
    add_usage,
    zero_usage,
)
from app.auth.deps import CurrentUser
from app.db.models import Deal
from app.privacy.gateway import PrivacyGateway
from app.security.injection import events as injection_events
from app.security.injection.gating import MONEY_TOOLS, gate_call
from app.security.injection.guard import guard_answer
from app.security.injection.switch import defences_on, layer_on
from app.security.injection.wrap import new_boundary, wrap_untrusted
from app.services.scope import party

log = structlog.get_logger("setu.agent")

PRIOR_TURN_MESSAGES = 10
RESPOND_CONTEXT_MESSAGES = 6
MONEY_CLAIM = re.compile(
    r"\b(I|we|Setu)\s+(have\s+|has\s+|just\s+)?(released|transferred|paid|sent|approved)\b", re.I
)
WHY_LINE = re.compile(r"^(\*\*|_)?(why|কারণ|原因)\s*[:\uff1a]", re.I)
SIMULATED_MARKERS = ("simulated", "সিমুলেটেড", "模拟")
# Tools whose results can carry text that came from a document, an e-mail or the knowledge base.
UNTRUSTED_TOOLS = frozenset(
    {"check_documents", "registry_status", "search_knowledge", "verify_party"}
)


@dataclass(frozen=True, slots=True)
class AgentDeps:
    user: CurrentUser
    db: Session | None
    thread_id: str
    gateway: PrivacyGateway = field(default_factory=PrivacyGateway)  # per request, never stored
    boundary: str = field(default_factory=new_boundary)  # layer 1: random per request


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: Intent
    needs_smart_model: bool


def _deal_uuid(db: Session | None, reference: str | None) -> uuid.UUID | None:
    if db is None or not reference:
        return None
    return db.scalar(select(Deal.id).where(Deal.reference == reference))


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


CITE = re.compile(r"\[(S\d{1,3})\]")


def _output_text(res: Any) -> str:
    raw = res.get("raw") if isinstance(res, dict) else res
    parsed = res.get("parsed") if isinstance(res, dict) else None
    if isinstance(raw, BaseMessage):
        content = text_of(raw)
        if content:
            return content
    return str(parsed) if parsed is not None else ""


def render_tool_result(
    outcome: ToolOutcome, gateway: PrivacyGateway | None = None, boundary: str | None = None
) -> str:
    """The tool result as the model gets it: identifiers masked, then wrapped as untrusted."""
    # "<" is escaped so data can never close the wrapper tag.
    gw = gateway or PrivacyGateway()
    ok = "true" if outcome.ok else "false"
    data = outcome.data or {}
    src = f"tool:{outcome.name}"
    if outcome.ok and data.get("card_type") == "citations":
        src = "kb"
        docs = [
            f'<retrieved_document cite_id="{html.escape(s["cite_id"], quote=True)}" '
            f'source_id="{html.escape(s["source_id"], quote=True)}">\n'
            + escape_prose(gw.mask_text(f"{s['heading_path']}\n{s['content']}"))
            + "\n</retrieved_document>"
            for s in data["data"]["snippets"]
        ]
        body = "\n".join(docs) or "(no matching passages)"
    else:
        body = gw.mask_payload(outcome.model_payload()).replace("<", "\\u003c")
    block = (
        f'<tool_result name="{outcome.name}" ok="{ok}" untrusted="true">\n{body}\n</tool_result>'
    )
    return wrap_untrusted(block, src, boundary)


def renumber_citations(outcome: ToolOutcome, start: int) -> int:
    """Give this result's passages turn-unique cite ids S{start+1}…; returns the new count."""
    data = outcome.data or {}
    if not outcome.ok or data.get("card_type") != "citations":
        return start
    for snippet in data["data"]["snippets"]:
        start += 1
        snippet["cite_id"] = f"S{start}"
    return start


def retrieved_ids(results: list[Any]) -> list[str]:
    ids: list[str] = []
    for r in results:
        if not r["ok"] or r.get("flags"):
            continue
        try:
            data = json.loads(r["payload"])
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("card_type") == "citations":
            ids += [s["cite_id"] for s in data["data"]["snippets"]]
    return ids


def _hidden_source(state: AgentState) -> bool:
    sources = {str(d.get("source")) for d in state.security.get("detections", [])}
    return "hidden_text" in sources or "HIDDEN_TEXT" in state.injection_flags


def _flagged_snippets(state: AgentState) -> list[str]:
    return [
        " ".join(str(d.get("snippet", "")).lower().split())
        for d in state.security.get("detections", [])
        if d.get("snippet")
    ]


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
            "security": SecurityCheck(
                defences=defences_on(), checked=[], detections=[], blocked_tools=[], guard=[]
            ),
            "token_usage": zero_usage(),
            "citations": [],
            "stop_reason": "budget" if state.thread_tokens_before >= self.token_budget else None,
            "answer": None,
            "why": None,
            "notes": [],
        }

    def privacy_gateway(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Masks the user's message before any model sees it (the runner already masked the graph
        input, so this is idempotent) and keeps new tokens from reusing ones in earlier turns."""
        gw = deps_of(config).gateway
        for m in state.messages:
            gw.vault.reserve_from(text_of(m))
        update: dict[str, Any] = {"privacy_checked": True}
        human = last_human(state.messages)
        if human is not None:
            masked = gw.mask_text(text_of(human))
            if masked != text_of(human):
                update["messages"] = [HumanMessage(content=masked, id=human.id)]
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
            sent, call = deps_of(config).gateway.protect(
                [SystemMessage(prompts.ROUTER_PROMPT), HumanMessage(text)],
                node="router",
                model=self.models.fast_id,
            )
            res = structured.invoke(sent, config=merge_configs(config, {"tags": ["node:router"]}))
            call.output = _output_text(res)
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
        # Earlier answers may quote tool data: re-send them escaped, never as markup.
        prior: list[AnyMessage] = []
        for m in state.messages[: state.turn_start]:
            if isinstance(m, HumanMessage):
                prior.append(m)
            elif isinstance(m, AIMessage) and not m.tool_calls and text_of(m).strip():
                prior.append(AIMessage(content=escape_prose(text_of(m)), id=m.id))
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
            messages, call = deps_of(config).gateway.protect(
                messages, node="agent", model=state.model_used
            )
            ai = bound.invoke(messages, config=self._tagged(config, state, "agent"))
            call.output = _output_text(ai)
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
        ctx = ToolContext(
            caller="llm", user=d.user, db=d.db, thread_id=d.thread_id, deal_ref=state.deal_id
        )
        on = layer_on(4)  # layer 4; layer 3 below never reads any switch
        allowed = self.allowlist(state.intent)
        steps = state.tool_steps
        out: list[ToolMessage] = []
        records: list[ToolCallRecord] = list(state.tool_calls_made)
        results: list[ToolResult] = list(state.tool_results)
        flags: list[str] = list(state.injection_flags)
        security: SecurityCheck = cast(SecurityCheck, dict(state.security))
        security["defences"] = on
        checked = list(security.get("checked", []))
        detections = list(security.get("detections", []))
        blocked = list(security.get("blocked_tools", []))
        user_text = text_of(last_human(state.messages)) if last_human(state.messages) else ""
        deal_id = _deal_uuid(d.db, state.deal_id)
        cites = len(retrieved_ids(results))
        gw = d.gateway
        linked_deal = False
        for call in calls:
            name, call_id = call["name"], call.get("id") or ""
            args = gw.unmask(
                call.get("args") or {}, canonical=True
            )  # tools work on the real values
            safe_name = name if TOOL_NAME.fullmatch(name or "") else INVALID_TOOL_NAME
            gate = (
                gate_call(
                    safe_name,
                    intent_allowed=allowed,
                    user_text=user_text,
                    untrusted_seen=bool(results) or bool(out),
                    turn_flagged=bool(flags),
                )
                if on
                else None
            )
            if steps >= self.max_tool_steps:
                outcome = ToolOutcome(
                    name=safe_name,
                    ok=False,
                    args_summary="",
                    error={"code": "tool_step_limit", "message": "tool step limit reached"},
                )
            elif gate is not None and not gate.allowed:
                # Layer 4: dropped before any service sees it; reported, logged, flagged.
                steps += 1
                outcome = ToolOutcome(
                    name=safe_name,
                    ok=False,
                    args_summary=args_summary(gw.mask(args)),
                    error={"code": "blocked_by_injection_gate", "message": gate.reason},
                )
                blocked.append({"name": safe_name, "code": gate.code})
                injection_events.record(
                    d.db,
                    kind="BLOCKED_TOOL",
                    source="tool_result" if results or out else "visible_text",
                    rules=[gate.code],
                    action_taken=injection_events.ACTION_BLOCKED_TOOL,
                    layer=4,
                    deal_id=deal_id,
                    user_id=d.user.id,
                    tool=safe_name,
                    flags_deal=safe_name in MONEY_TOOLS and gate.code != "NOT_FOR_THIS_REQUEST",
                    alert=False,
                    durable=True,
                )
                if safe_name in MONEY_TOOLS and "BLOCKED_TOOL" not in flags:
                    flags.append("BLOCKED_TOOL")
            else:
                outcome = self.registry.guard(name, args, ctx, config, allowed if on else None)
                cites = renumber_citations(outcome, cites)
                steps += 1
            raw_payload = outcome.payload()
            out.append(
                ToolMessage(
                    content=render_tool_result(outcome, gw, d.boundary),
                    tool_call_id=call_id,
                    name=outcome.name,
                    status="success" if outcome.ok else "error",
                )
            )
            records.append(
                {
                    "id": call_id,
                    "name": outcome.name,
                    "args_summary": gw.mask_text(args_summary(gw.mask(args))),
                    "ok": outcome.ok,
                    "error_code": (outcome.error or {}).get("code"),
                }
            )
            gw.raw_results.append(raw_payload)  # real values for the UI card only
            results.append(
                {
                    "name": outcome.name,
                    "ok": outcome.ok,
                    "payload": gw.mask_payload(raw_payload),
                    "flags": list(outcome.injection),
                }
            )
            if outcome.ok and outcome.name in UNTRUSTED_TOOLS and outcome.name not in checked:
                checked.append(outcome.name)
            call_deal = _deal_uuid(d.db, str(args.get("deal_id") or "")) if outcome.ok else None
            call_deal = call_deal or deal_id
            if (call_deal or (d.db is None and state.deal_id)) and (
                outcome.detections or outcome.injection
            ):
                linked_deal = True  # no database (evaluation harness): the chat's deal counts
            for det in outcome.detections:
                detections.append(
                    {
                        "source": det["source"],
                        "rules": det["matched_rules"],
                        "score": det["score"],
                        "snippet": det["snippet"],
                    }
                )
                injection_events.record(
                    d.db,
                    kind="DETECTED",
                    source=str(det["source"]),
                    rules=list(det["matched_rules"]),
                    score=int(det["score"]),
                    snippet=str(det["snippet"]),
                    action_taken=injection_events.ACTION_FLAGGED
                    if call_deal
                    else injection_events.ACTION_IGNORED,
                    layer=3 if call_deal else 2,
                    deal_id=call_deal,
                    user_id=d.user.id,
                    tool=outcome.name,
                    flags_deal=call_deal is not None,
                    durable=True,
                )
            if outcome.injection and not outcome.detections:
                # A tool that reports its own findings (check_documents: the upload pipeline
                # already recorded the event and flagged the deal).
                declared = list(outcome.injection)
                detections.append(
                    {
                        "source": "hidden_text" if "HIDDEN_TEXT" in declared else "visible_text",
                        "rules": declared,
                        "score": 0,
                        "snippet": "",
                    }
                )
            flags.extend(c for c in outcome.injection if c not in flags)
        security.update(
            checked=checked,
            detections=detections,
            blocked_tools=blocked,
            deal_flagged=linked_deal or bool(security.get("deal_flagged", False)),
        )
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
            "security": security,
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

    @staticmethod
    def _card_explanation(state: AgentState, lang: Lang) -> str | None:
        if state.injection_flags:
            return None  # never copy text from a turn with flagged data into the answer
        for r in state.tool_results:
            if not r["ok"] or r.get("flags"):
                continue
            try:
                data = json.loads(r["payload"])
            except ValueError:
                continue
            text = data.get("explanation_bn" if lang == "bn" else "explanation_en")
            if isinstance(text, str) and text.strip():
                return text.strip()
        return None

    def _finalize(
        self, text: str, state: AgentState, lang: Lang
    ) -> tuple[str, str | None, list[str]]:
        """(answer, why, notes). The model's text is kept verbatim (streamed tokens stay a prefix
        of the answer); a missing "Why:" line is added from the tools' deterministic explanation."""
        text = text.strip()
        claim = bool(MONEY_CLAIM.search(text))
        if layer_on(5):  # layer 5
            guarded = guard_answer(
                text,
                lang=lang,
                detected=bool(state.injection_flags),
                hidden=_hidden_source(state),
                deal_linked=bool(state.security.get("deal_flagged")),
                prompts=[prompts.SYSTEM_PROMPT, prompts.AGENT_PROMPT, prompts.ROUTER_PROMPT],
                injected_snippets=_flagged_snippets(state),
            )
            if guarded.violations:
                state.security["guard"] = sorted(set(guarded.violations))
            text = guarded.text.strip()
        label = prompts.WHY_LABEL[lang]
        why = next((ln.strip() for ln in text.splitlines() if WHY_LINE.match(ln.strip())), None)
        parts = [text]
        tools_ok = [r["name"] for r in state.tool_results if r["ok"]]
        if why is None and tools_ok:
            explanation = self._card_explanation(state, lang)
            why = f"{label} " + (
                explanation or prompts.WHY_FALLBACK[lang].format(tools=", ".join(tools_ok))
            )
            parts.append(why)
        notes: list[str] = []
        figures = [
            n for n in tools_ok if n != "search_knowledge"
        ]  # KB answers carry no Setu figures
        if figures and not any(m in text.lower() for m in SIMULATED_MARKERS):
            notes.append(prompts.STATIC["simulated"][lang])
        if state.injection_flags and not layer_on(5):
            codes = ", ".join(state.injection_flags)
            notes.append(prompts.STATIC["injection"][lang].format(codes=codes))
        if state.stop_reason == "tool_cap":
            notes.append(prompts.STATIC["tool_cap"][lang])
        if claim:
            notes.append(prompts.STATIC["no_money_moved"][lang])
        return "\n\n".join(p for p in [*parts, *notes] if p), why, notes

    def respond(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        lang = cast(Lang, state.language or "en")
        usage = state.token_usage
        stop = state.stop_reason
        why: str | None = None
        notes: list[str] = []
        if stop == "budget":
            answer = prompts.STATIC["budget"][lang]
        elif state.intent == "out_of_scope":
            answer = prompts.STATIC["out_of_scope"][lang]
        elif stop == "model_error" and not state.tool_results:
            answer = prompts.STATIC["model_error"][lang]
        else:
            messages = [
                SystemMessage(
                    prompts.respond_system_prompt(
                        lang, bool(state.injection_flags), bool(retrieved_ids(state.tool_results))
                    )
                ),
                HumanMessage(self._respond_input(state)),
            ]
            try:
                messages, call = deps_of(config).gateway.protect(
                    messages, node="respond", model=state.model_used
                )
                tagged = self._tagged(config, state, "respond")
                if layer_on(5) and (state.injection_flags or state.security.get("checked")):
                    # Layer 5 needs the whole answer: hold the tokens back, the final text is sent
                    tagged = merge_configs(tagged, {"tags": ["nostream"]})
                ai = self.models.for_tier(state.model_tier).invoke(messages, config=tagged)
                text = text_of(ai)
                call.output = text
                usage = add_usage(usage, usage_of(ai))
            except Exception as exc:
                log.warning("respond_model_failed", error=type(exc).__name__)
                text, stop = prompts.STATIC["model_error"][lang], "model_error"
            answer, why, notes = self._finalize(text, state, lang)
        retrieved = retrieved_ids(state.tool_results)
        cited = list(dict.fromkeys(c for c in CITE.findall(answer) if c in retrieved))
        return {
            "citations": cited,
            "messages": [AIMessage(content=answer)],
            "answer": answer,
            "why": why,
            "notes": notes,
            "security": state.security,
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
