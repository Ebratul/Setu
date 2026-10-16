"""Deterministic offline chat model (AGENT_MOCK_MODE=true, or no ANTHROPIC_API_KEY).

Mimics the three ways the graph uses a model, so dev, tests and the demo run without network:
- router: `with_structured_output(...)` → keyword rules (same as the router's fallback);
- agent: with tools bound → picks a tool by keywords, then replies READY once results are in;
- respond: no tools → composes a short answer from the <tool_result> blocks in the prompt, in
  the language the system prompt asks for.
It never reads instructions from tool results; it only formats known fields.
"""

import json
import re
from collections.abc import Iterator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from app.agent.intents import DEAL_REF, keyword_intent, needs_smart
from app.agent.state import Lang

_TOOL_BLOCK = re.compile(
    r'<tool_result name="([^"]+)" ok="(true|false)"[^>]*>(.*?)</tool_result>', re.S
)
_DASHBOARD = ("dashboard", "cash", "shortfall", "balance", "ড্যাশবোর্ড", "ক্যাশ", "নগদ", "টাকা", "现金")
_HOW = ("how", "escrow", "tier", "approval", "works", "কিভাবে", "কীভাবে", "এসক্রো", "怎么", "托管")
_DEAL = ("deal", "order", "milestone", "status", "ডিল", "অর্ডার", "মাইলস্টোন", "订单")


def _text(message: BaseMessage) -> str:
    return message.text if hasattr(message, "text") else str(message.content)


def _usage(prompt: Sequence[BaseMessage], output: str) -> UsageMetadata:
    inp = max(1, sum(len(_text(m)) for m in prompt) // 4)
    out = max(1, len(output) // 4)
    return {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def _language(messages: Sequence[BaseMessage]) -> Lang:
    system = " ".join(_text(m) for m in messages if isinstance(m, SystemMessage))
    if "Answer in Bangla" in system:
        return "bn"
    if "Answer in Chinese" in system:
        return "zh"
    return "en"


def _dashboard_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    ccy = d.get("currency", "")
    cash, escrow = _money(d.get("cash_balance")), _money(d.get("in_escrow"))
    short = d.get("first_shortfall")
    if lang == "bn":
        out = [f"আপনার নগদ ব্যালেন্স {ccy} {cash}, এসক্রোতে আছে {ccy} {escrow}।"]
        if short:
            out.append(f"{short['on']} তারিখে {ccy} {_money(short['amount'])} ঘাটতি হতে পারে।")
        out.append(f"খোলা সতর্কতা: {d.get('open_alerts_count', 0)}টি।")
        return out
    out = [f"Your cash balance is {ccy} {cash}, with {ccy} {escrow} in escrow."]
    if short:
        out.append(f"You are short by {ccy} {_money(short['amount'])} on {short['on']}.")
    out.append(f"You have {d.get('open_alerts_count', 0)} open alerts.")
    return out


def _deal_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    ref, status = d.get("reference"), d.get("status")
    nxt = next(
        (m for m in d.get("milestones", []) if m["seq"] == d.get("next_milestone_seq")), None
    )
    if lang == "bn":
        out = [f"ডিল {ref} এর অবস্থা: {status}।"]
        if nxt:
            out.append(
                f"পরবর্তী মাইলস্টোন {nxt['seq']}: {nxt['currency']} {_money(nxt['amount'])}, "
                f"{nxt['due_on']} তারিখে।"
            )
        return out
    out = [f"Deal {ref} is {status}."]
    if nxt:
        out.append(
            f"Next is milestone {nxt['seq']}: {nxt['currency']} {_money(nxt['amount'])} "
            f"due on {nxt['due_on']}."
        )
    return out


def _how_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    facts = d.get("facts", [])[:2]
    if lang == "bn":
        return ["Setu মাইলস্টোন এসক্রোতে সাপ্লায়ারের টাকা রাখে এবং ঝুঁকির স্তর অনুযায়ী মানুষের অনুমোদন চায়।"]
    return list(facts)


_FORMATTERS = {
    "get_dashboard_snapshot": _dashboard_sentences,
    "get_deal_summary": _deal_sentences,
    "explain_how_setu_works": _how_sentences,
}
_WHY = {
    "en": "Why: these figures come from Setu's {tools} results.",
    "bn": "কারণ: এই তথ্য Setu-র {tools} থেকে এসেছে।",
    "zh": "原因：这些数据来自 Setu 的 {tools} 结果。",
}
_GREETING = {
    "en": "Hello! I'm Setu, your import-finance copilot. Ask me about your cash flow, a deal, "
    "financing or how escrow works.",
    "bn": "হ্যালো! আমি Setu, আপনার আমদানি-অর্থায়ন সহকারী। ক্যাশ ফ্লো, ডিল, অর্থায়ন বা এসক্রো নিয়ে জিজ্ঞেস করুন।",
    "zh": "您好！我是 Setu，您的进口融资助手。可以问我现金流、交易、融资或托管的问题。",
}


_UNAVAILABLE = {
    "en": "I couldn't get that data right now, so I won't guess any numbers.",
    "bn": "এই মুহূর্তে তথ্যটি পাওয়া যায়নি, তাই আমি কোনো সংখ্যা অনুমান করব না।",
    "zh": "暂时无法获取该数据，所以我不会猜测任何数字。",
}


def compose_answer(messages: Sequence[BaseMessage]) -> str:
    lang = _language(messages)
    prompt = "\n".join(_text(m) for m in messages if not isinstance(m, SystemMessage))
    sentences: list[str] = []
    used: list[str] = []
    failed = 0
    for name, ok, payload in _TOOL_BLOCK.findall(prompt):
        if ok != "true" or name not in _FORMATTERS:
            failed += 1
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        sentences.extend(_FORMATTERS[name](data, lang))
        used.append(name)
    if not used:
        return _UNAVAILABLE[lang] if failed else _GREETING[lang]
    return " ".join(sentences) + "\n\n" + _WHY[lang].format(tools=", ".join(used))


def _pick_tool(
    messages: Sequence[BaseMessage], tools: Sequence[str]
) -> tuple[str, dict[str, Any]] | None:
    human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    q = _text(human).lower() if human else ""
    system = " ".join(_text(m) for m in messages if isinstance(m, SystemMessage))
    ref = DEAL_REF.search(q) or DEAL_REF.search(system)
    if any(k in q for k in _DASHBOARD) and "get_dashboard_snapshot" in tools:
        return "get_dashboard_snapshot", {}
    if (DEAL_REF.search(q) or any(k in q for k in _DEAL)) and ref and "get_deal_summary" in tools:
        return "get_deal_summary", {"deal_id": ref.group(0).upper()}
    if any(k in q for k in _HOW) and "explain_how_setu_works" in tools:
        return "explain_how_setu_works", {}
    if "get_dashboard_snapshot" in tools and keyword_intent(q) in (
        "cashflow",
        "financing",
        "analysis",
    ):
        return "get_dashboard_snapshot", {}
    return None


class MockChatModel(BaseChatModel):
    model_name: str = "mock-fast"
    bound_tools: tuple[str, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "setu-mock"

    def bind_tools(
        self, tools: Sequence[Any], **kwargs: Any
    ) -> Runnable[LanguageModelInput, AIMessage]:
        names = tuple(
            t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools
        )
        return self.model_copy(update={"bound_tools": names})

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        def route(value: Any) -> Any:
            messages = value if isinstance(value, list) else value.to_messages()
            human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
            text = _text(human) if human else ""
            intent = keyword_intent(text)
            parsed = schema(intent=intent, needs_smart_model=needs_smart(intent, text))
            raw = AIMessage(content="", usage_metadata=_usage(messages, intent))
            return {"raw": raw, "parsed": parsed, "parsing_error": None} if include_raw else parsed

        return RunnableLambda(route, name="mock_router")

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        if self.bound_tools:
            last_human = max(
                (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1
            )
            if any(isinstance(m, ToolMessage) for m in messages[last_human + 1 :]):
                return AIMessage(content="READY", usage_metadata=_usage(messages, "READY"))
            pick = _pick_tool(messages, self.bound_tools)
            if pick is None:
                return AIMessage(content="READY", usage_metadata=_usage(messages, "READY"))
            name, args = pick
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": name,
                        "args": args,
                        "id": f"mock_call_{len(messages)}",
                        "type": "tool_call",
                    }
                ],
                usage_metadata=_usage(messages, name + json.dumps(args)),
            )
        text = compose_answer(messages)
        return AIMessage(content=text, usage_metadata=_usage(messages, text))

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        msg = self._decide(messages)
        if msg.tool_calls:
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(msg.tool_calls)
                ],
                usage_metadata=msg.usage_metadata,
            )
            yield ChatGenerationChunk(message=chunk)
            return
        pieces = re.findall(r"\S+\s*", str(msg.content)) or [""]
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            chunk = AIMessageChunk(
                content=piece, usage_metadata=msg.usage_metadata if last else None
            )
            gen = ChatGenerationChunk(message=chunk)
            if run_manager:
                run_manager.on_llm_new_token(piece, chunk=gen)
            yield gen
