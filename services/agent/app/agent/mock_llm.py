"""Deterministic offline chat model (AGENT_MOCK_MODE=true, or no ANTHROPIC_API_KEY).

Mimics the three ways the graph uses a model, so dev, tests and the demo run without network:
- router: `with_structured_output(...)` → keyword rules (same as the router's fallback);
- agent: with tools bound → picks a tool by keywords, then replies READY once results are in;
- respond: no tools → composes a short answer from the <tool_result> blocks in the prompt, in
  the language the system prompt asks for.
It never reads instructions from tool results; it only formats known fields.
"""

import html
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

_DOC_BLOCK = re.compile(
    r'<retrieved_document cite_id="(S\d+)"[^>]*>\n(.*?)\n</retrieved_document>', re.S
)
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


def _landed_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    c, unit = d["currency"], d["unit"]
    ref = d.get("deal_ref") or ("এই হিসাব" if lang == "bn" else "this calculation")
    margin = d.get("gross_margin_pct")
    if lang == "bn":
        out = [
            f"{ref}-এর landed cost {c} {_money(d['landed_cost'])} (প্রতি {unit} {c} "
            f"{_money(d['cost_per_unit'])})।"
        ]
        if margin is not None:
            out.append(
                f"Gross margin {margin}%, break-even দাম প্রতি {unit} {c} "
                f"{_money(d['break_even_price_per_unit'])}।"
            )
        if d.get("defaulted_deal"):
            out.append(f"আপনার সাম্প্রতিক সক্রিয় ডিল {ref} ধরে হিসাব করেছি।")
        return out
    out = [
        f"The landed cost of {ref} is {c} {_money(d['landed_cost'])} "
        f"({c} {_money(d['cost_per_unit'])} per {unit})."
    ]
    if margin is not None:
        out.append(
            f"Gross margin is {margin}%, and break-even is {c} "
            f"{_money(d['break_even_price_per_unit'])} per {unit}."
        )
    if d.get("defaulted_deal"):
        out.append(f"I used your most recent active deal, {ref}.")
    return out


def _cashflow_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    c = d["currency"]
    before, after = d["before"], d.get("after")
    sf = (after or before).get("first_shortfall")
    was = before.get("first_shortfall")
    out: list[str] = []
    if lang == "bn":
        if after and was and not sf:
            out.append(f"এই পরিবর্তনে {was['on']} তারিখের {c} {_money(was['amount'])} ঘাটতি থাকে না।")
        elif sf:
            out.append(f"হ্যাঁ, {sf['on']} তারিখে cash কম পড়বে — ঘাটতি {c} {_money(sf['amount'])}।")
        else:
            out.append("না, এই সময়ে cash কম পড়বে না।")
        low = after or before
        out.append(f"সর্বনিম্ন ব্যালেন্স {c} {_money(low['lowest_balance'])}, {low['lowest_on']} তারিখে।")
        return out
    if after and was and not sf:
        out.append(
            f"With this change the {c} {_money(was['amount'])} shortfall on {was['on']} goes away."
        )
    elif sf:
        out.append(f"Yes — you are short by {c} {_money(sf['amount'])} on {sf['on']}.")
    else:
        out.append("No, your cash stays above the buffer in this window.")
    low = after or before
    out.append(f"The lowest balance is {c} {_money(low['lowest_balance'])} on {low['lowest_on']}.")
    return out


def _alerts_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    alerts = d.get("alerts", [])
    top = alerts[0] if alerts else None
    if lang == "bn":
        return [f"আপনার {d['count']}টি সতর্কতা আছে।"] + (
            [f"সবচেয়ে জরুরি: {top['title_bn']}।"] if top else []
        )
    return [f"You have {d['count']} alerts."] + (
        [f"Most urgent: {top['title_en']}."] if top else []
    )


def _financing_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    c, rec = d["currency"], d.get("recommended")
    if d.get("no_financing_needed") or not rec:
        return ["এই ডিলের জন্য অর্থায়নের দরকার নেই।" if lang == "bn" else "No financing is needed."]
    opts = [o for o in d.get("options", []) if o["eligible"]]
    nxt = opts[1] if len(opts) > 1 else None
    if lang == "bn":
        out = [
            f"{c} {_money(d['amount'])}-এর জন্য সবচেয়ে সস্তা: {rec['name']}, মোট খরচ {c} "
            f"{_money(rec['total_cost'])}।"
        ]
        if nxt:
            out.append(f"পরেরটি {nxt['name']}: {c} {_money(nxt['total_cost'])}।")
        out.append("Apply করতে Financing পেজে যান।")
        return out
    out = [
        f"For {c} {_money(d['amount'])}, the cheapest option is {rec['name']} at a total cost "
        f"of {c} {_money(rec['total_cost'])}."
    ]
    if nxt:
        out.append(f"Next is {nxt['name']} at {c} {_money(nxt['total_cost'])}.")
    out.append("You can apply from the Financing page.")
    return out


def _fx_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    cheap = d["cheaper"]
    if lang == "bn":
        return [
            f"{d['basis']}-এ {cheap}-তে pay করলে BDT {_money(d['saving'])} "
            f"({d['saving_pct']}%) বাঁচবে।"
        ]
    return [
        f"For {d['basis']}, paying in {cheap} saves BDT {_money(d['saving'])} ({d['saving_pct']}%)."
    ]


def _monthly_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    c, m = d["currency"], d.get("average_margin_pct")
    if lang == "bn":
        return [
            f"{d['month']}-এ {d['deals_count']}টি ডিল, landed cost {c} "
            f"{_money(d['total_landed_cost'])}" + (f", গড় margin {m}%।" if m else "।")
        ]
    return [
        f"In {d['month']} you had {d['deals_count']} deals with a landed cost of {c} "
        f"{_money(d['total_landed_cost'])}" + (f" and an average margin of {m}%." if m else ".")
    ]


def _scorecard_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    sups = d.get("suppliers", [])
    best = next((s for s in sups if not s["weak"] and s["score"]), None)
    weak = [s["name"] for s in sups if s["weak"]]
    if lang == "bn":
        return ([f"সেরা সাপ্লায়ার {best['name']} (স্কোর {best['score']})।"] if best else []) + (
            [f"সতর্ক থাকুন: {', '.join(weak)}।"] if weak else []
        )
    return (
        [f"Your strongest supplier is {best['name']} (score {best['score']})."] if best else []
    ) + ([f"Be careful with {', '.join(weak)}."] if weak else [])


_FORMATTERS = {
    "get_dashboard_snapshot": _dashboard_sentences,
    "get_deal_summary": _deal_sentences,
    "explain_how_setu_works": _how_sentences,
}


def _citations_sentences(d: dict[str, Any], lang: Lang) -> list[str]:
    snippets = d.get("snippets", [])
    if not snippets:
        return [
            "এ বিষয়ে Setu-র knowledge base-এ কিছু পাইনি।"
            if lang == "bn"
            else "I couldn't find this in Setu's knowledge base."
        ]
    top = snippets[0]
    lines = top["content"].split("\n")
    # retrieved blocks are "heading path\nheading\nbody"; quote the body only
    body = " ".join(lines[2:] if len(lines) > 2 else lines[1:]) or top["content"]
    sentences = re.split(r"(?<=[.!?।])\s+", body.strip())
    lead = " ".join(sentences[:2]).strip()
    note = (
        "এটি সহজ করা সারসংক্ষেপ; সরকারি উৎসে যাচাই করুন।"
        if lang == "bn"
        else "This is a simplified summary; verify with the official source."
    )
    return [f"{lead} [{top['cite_id']}]", note]


_CARD_FORMATTERS = {
    "citations": _citations_sentences,
    "landed_cost": _landed_sentences,
    "cashflow": _cashflow_sentences,
    "alerts": _alerts_sentences,
    "financing_comparison": _financing_sentences,
    "fx_compare": _fx_sentences,
    "monthly_summary": _monthly_sentences,
    "scorecard": _scorecard_sentences,
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
    """Short answer from tool JSON. The "Why:" line is added by the respond node."""
    lang = _language(messages)
    prompt = "\n".join(_text(m) for m in messages if not isinstance(m, SystemMessage))
    sentences: list[str] = []
    failed = 0
    for name, ok, payload in _TOOL_BLOCK.findall(prompt):
        docs = _DOC_BLOCK.findall(payload) if ok == "true" else []
        try:
            data = json.loads(payload) if ok == "true" and not docs else None
        except json.JSONDecodeError:
            data = None
        if docs:
            data = {
                "card_type": "citations",
                "data": {
                    "snippets": [{"cite_id": c, "content": html.unescape(b)} for c, b in docs]
                },
            }
        fmt = _CARD_FORMATTERS.get(data.get("card_type", "")) if isinstance(data, dict) else None
        if data is not None and fmt is not None:
            sentences.extend(fmt(data["data"], lang))
        elif data is not None and name in _FORMATTERS:
            sentences.extend(_FORMATTERS[name](data, lang))
        else:
            failed += 1
    if not sentences:
        return _UNAVAILABLE[lang] if failed else _GREETING[lang]
    return " ".join(sentences)


_ALERTS = ("alert", "সতর্ক", "অ্যালার্ট")
_LANDED = ("landed", "margin", "break-even", "break even", "ল্যান্ডেড", "মার্জিন", "লাভ")
_FX = ("usd", "cny", "rmb", "currency", "exchange", "fx", "বাঁচবে")
_FINANCING = (
    "financ",
    "loan",
    "credit",
    "cheapest",
    "lender",
    "ঋণ",
    "লোন",
    "অর্থায়ন",
    "ফাইন্যান্সিং",
    "সস্তা",
)
_SUPPLIERS = ("scorecard", "supplier", "সাপ্লায়ার")
_CASH = ("cash", "shortfall", "short", "balance", "forecast", "কম পড়বে", "ক্যাশ", "নগদ", "现金")
_MONTHLY = ("monthly", "summary", "month summary", "মাসিক", "সারাংশ", "সারসংক্ষেপ")
_DASH_ONLY = ("dashboard", "ড্যাশবোর্ড")
_KB_STRONG = (
    "fob",
    "cif",
    "cfr",
    "exw",
    "dap",
    "ddp",
    "incoterm",
    "advance payment",
    "bangladesh bank",
    "regulation",
    "circular",
    "must match",
    "fields",
    "how does setu",
    "escrow work",
    "মানে",
    "সীমা",
    "নিয়ম",
    "কীভাবে কাজ",
    "নিজে টাকা",
)
_DEFINITION = ("what is", "what are", "what does", "define", "meaning", "explain", "কী?", "কি?")
_PERSONAL = (" my ", "my ", " i ", "i'm", "আমার", "আমি")


def _query_lang(q: str) -> str:
    return "bn" if re.search(r"[\u0980-\u09ff]", q) else "en"


def _pick_tool(
    messages: Sequence[BaseMessage], tools: Sequence[str]
) -> tuple[str, dict[str, Any]] | None:
    human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    q = _text(human).lower() if human else ""
    system = " ".join(_text(m) for m in messages if isinstance(m, SystemMessage))
    in_q = DEAL_REF.search(q)
    ref = in_q or DEAL_REF.search(system)
    deal = {"deal_id": in_q.group(0).upper()} if in_q else {}

    def has(keys: tuple[str, ...]) -> bool:
        return any(k in q for k in keys)

    personal = in_q is not None or any(w in q for w in _PERSONAL)
    knowledge = has(_KB_STRONG) or (has(_DEFINITION) and not personal)
    kb_args = {"query": _text(human)[:300] if human else q, "language": _query_lang(q)}
    rules: list[tuple[bool, str, dict[str, Any]]] = [
        (has(_DASH_ONLY), "get_dashboard_snapshot", {}),
        (knowledge, "search_knowledge", kb_args),
        (has(_ALERTS), "get_alerts", {}),
        (has(_LANDED), "analyze_order", deal),
        (has(_FX), "compare_fx_route", deal),
        (
            has(_FINANCING),
            "match_financing",
            {**deal, "mode": "order" if in_q or "order" in q else "shortfall"},
        ),
        (has(_SUPPLIERS), "get_supplier_scorecard", {}),
        (has(_CASH), "forecast_cashflow", {}),
        (has(_MONTHLY), "get_monthly_summary", {}),
        (has(_CASH), "get_dashboard_snapshot", {}),
        (
            (in_q is not None or has(_DEAL)) and ref is not None,
            "get_deal_summary",
            {"deal_id": ref.group(0).upper()} if ref else {},
        ),
        (has(_HOW), "explain_how_setu_works", {}),
    ]
    for hit, name, args in rules:
        if hit and name in tools:
            return name, args
    fallback = {
        "cashflow": "forecast_cashflow",
        "financing": "match_financing",
        "analysis": "analyze_order",
    }.get(keyword_intent(q))
    for name in (fallback, "get_dashboard_snapshot"):
        if name and name in tools:
            return name, {}
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
