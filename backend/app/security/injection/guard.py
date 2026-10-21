"""Layer 5 - output guard on the final answer.

The answer must not (a) claim a payment was approved, released or changed (the service confirms
that, never the model; no model-callable tool moves money), (b) reveal the system prompt, or
(c) repeat an injected instruction as advice. Offending sentences are removed; when the turn
carried a detection the answer says so plainly.
"""

import re
from dataclasses import dataclass, field

from app.security.injection.detector import scan

_SENTENCE = re.compile(r"(?<=[.!?।。！？])\s+")

_MONEY_CLAIM = re.compile(
    r"\b(I|we|Setu)\b(?:'ve|’ve)?\s+(?:(?:have|has|just|already)\s+)*"
    r"(released|transferred|paid|sent|approved|wired|changed|updated|marked|set)\b"
    r"|\b(payment|funds?|tranche|money|beneficiary|account|bank details?)\b.{0,40}"
    r"\b(has|have|was|were|is|been)\b\s+(now\s+|successfully\s+|already\s+)?"
    r"(been\s+)?(released|transferred|approved|paid|sent|wired|changed|updated)\b"
    r"|(পেমেন্ট|টাকা|অর্থ|হিসাব|অ্যাকাউন্ট).{0,25}(ছাড়\s*করা\s*হয়েছে|পরিশোধ\s*করা\s*হয়েছে|"
    r"অনুমোদন\s*করা\s*হয়েছে|পাঠানো\s*হয়েছে|পরিবর্তন\s*করা\s*হয়েছে)"
    r"|(已|已经).{0,3}(放款|付款|支付|批准|释放|转账|更改|变更)",
    re.I,
)
_NEGATED = re.compile(
    r"\b(not|never|no|nothing|without|isn't|wasn't|hasn't|haven't|didn't|cannot|can't)\b"
    r"|নয়|না\b|কোনো|没有|未|不会|没",
    re.I,
)
_SHINGLE = 7

REFUSAL = {
    "en": "I can't share my internal instructions. I can help with your import finance questions.",
    "bn": "আমার অভ্যন্তরীণ নির্দেশনা শেয়ার করতে পারি না। আপনার আমদানি অর্থায়নের প্রশ্নে সাহায্য করতে পারি।",
    "zh": "我无法分享内部指令。我可以帮助您处理进口融资方面的问题。",
}
NO_DEAL = {
    "en": "This content contains an instruction. Setu ignored it and did not act on it.",
    "bn": "এই বিষয়বস্তুতে একটি নির্দেশ আছে। Setu তা উপেক্ষা করেছে এবং তার ভিত্তিতে কিছু করেনি।",
    "zh": "该内容包含一条指令。Setu 已忽略它，没有据此执行任何操作。",
}
DETECTED = {
    "hidden": {
        "en": "This document contains a hidden instruction. Setu ignored it and flagged the deal "
        "for extra verification.",
        "bn": "এই নথিতে একটি লুকানো নির্দেশ আছে। Setu তা উপেক্ষা করেছে এবং অতিরিক্ত যাচাইয়ের জন্য "
        "ডিলটি চিহ্নিত করেছে।",
        "zh": "该文件包含一条隐藏指令。Setu 已忽略它，并将该交易标记为需要额外核查。",
    },
    "plain": {
        "en": "This content contains an instruction. Setu ignored it and flagged the deal for "
        "extra verification.",
        "bn": "এই বিষয়বস্তুতে একটি নির্দেশ আছে। Setu তা উপেক্ষা করেছে এবং অতিরিক্ত যাচাইয়ের জন্য "
        "ডিলটি চিহ্নিত করেছে।",
        "zh": "该内容包含一条指令。Setu 已忽略它，并将该交易标记为需要额外核查。",
    },
}


@dataclass(slots=True)
class GuardResult:
    text: str
    violations: list[str] = field(default_factory=list)
    changed: bool = False


def claims_money(sentence: str) -> bool:
    """The text says a payment / account change happened (and does not negate it)."""
    return bool(_MONEY_CLAIM.search(sentence) and not _NEGATED.search(sentence))


def claims_money_anywhere(text: str) -> bool:
    """Any sentence of `text` claims that a payment or account change happened."""
    return any(claims_money(s) for line in text.split("\n") for s in _SENTENCE.split(line))


def _norm_words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def _prompt_shingles(prompts: list[str]) -> set[tuple[str, ...]]:
    out: set[tuple[str, ...]] = set()
    for p in prompts:
        w = _norm_words(p)
        out.update(tuple(w[i : i + _SHINGLE]) for i in range(max(0, len(w) - _SHINGLE + 1)))
    return out


def leaks_prompt(answer: str, prompts: list[str]) -> bool:
    shingles = _prompt_shingles(prompts)
    w = _norm_words(answer)
    return any(tuple(w[i : i + _SHINGLE]) in shingles for i in range(max(0, len(w) - _SHINGLE + 1)))


def guard_answer(
    text: str,
    *,
    lang: str,
    detected: bool,
    hidden: bool = False,
    deal_linked: bool = True,
    prompts: list[str] | None = None,
    money_confirmed: bool = False,
    injected_snippets: list[str] | None = None,
) -> GuardResult:
    """`detected`: a detection happened this turn. `money_confirmed`: the service confirmed a
    money action (never true for model-callable tools). `injected_snippets` are normalised pieces
    of the flagged content the answer must not echo."""
    res = GuardResult(text)
    if prompts and leaks_prompt(text, prompts):
        res.text = REFUSAL.get(lang, REFUSAL["en"])
        res.violations.append("PROMPT_LEAK")
        res.changed = True
        return res
    snippets = [s for s in (injected_snippets or []) if len(s) >= 12]
    lines: list[str] = []
    for line in text.split("\n"):
        kept: list[str] = []
        for sentence in _SENTENCE.split(line):
            s = sentence.strip()
            if not s:
                continue
            if not money_confirmed and claims_money(s):
                res.violations.append("MONEY_CLAIM")
                continue
            if detected and not _is_notice(s):
                plain = " ".join(s.lower().split())
                if (
                    any(sn in plain for sn in snippets)
                    or scan(s, "tool_result", use_llm=False).is_injection
                ):
                    res.violations.append("ECHOED_INSTRUCTION")
                    continue
            kept.append(s)
        if kept or not line.strip():
            lines.append(" ".join(kept) if kept else line)
    out = "\n".join(lines) if res.violations else text
    if detected:
        table = DETECTED["hidden" if hidden else "plain"] if deal_linked else NO_DEAL
        notice = table.get(lang) or table["en"]
        if notice not in out:
            out = f"{out.rstrip()}\n\n{notice}"
    res.changed = out != text
    res.text = out
    return res


def _is_notice(sentence: str) -> bool:
    return any(sentence.strip() == v.get(k) for v in (*DETECTED.values(), NO_DEAL) for k in v)
