"""Layer 2 - normalisation and detection of instruction-like text.

`scan(text, source)` normalises (NFKC, Cyrillic/Greek look-alikes folded to Latin, zero-width and
other format characters removed, spaced-out letters joined, obvious base64 / URL-encoded chunks
decoded for scanning only) and applies the deterministic EN / BN / ZH rules. Output carries rule
codes, a 0-100 score and a short masked snippet, never the document. `highlights` are character
spans in the ORIGINAL text, for the attack console.

An optional fast-model second opinion (INJECTION_LLM_CHECK=true) can only raise a borderline score;
the deterministic rules win every conflict.
"""

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

from app.domain.kyb import HOMOGLYPHS

Source = Literal["hidden_text", "visible_text", "metadata", "email", "kb", "tool_result"]
SOURCES: tuple[Source, ...] = (
    "hidden_text",
    "visible_text",
    "metadata",
    "email",
    "kb",
    "tool_result",
)
INJECTION_THRESHOLD = 50
MAX_SCAN_CHARS = 60_000
SNIPPET_CHARS = 80

_HOMOGLYPH_TABLE = str.maketrans(HOMOGLYPHS)
_SPACED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][\s.\-_]){3,}[^\W\d_](?![^\W\d_])")
_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
_WS = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Normalised:
    text: str
    start: tuple[int, ...]  # start offset in the original text of each normalised character
    end: tuple[int, ...]  # end offset (exclusive)

    def original_span(self, a: int, b: int) -> tuple[int, int]:
        return self.start[a], self.end[max(a, b - 1)]


def _clusters(text: str) -> list[tuple[int, int]]:
    """Base character + following combining marks (so NFKC can compose Bangla signs)."""
    out: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        j = i + 1
        while j < n and unicodedata.category(text[j])[0] == "M":
            j += 1
        out.append((i, j))
        i = j
    return out


def _fold(text: str) -> tuple[list[str], list[int], list[int]]:
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for a, b in _clusters(text):
        folded = unicodedata.normalize("NFKC", text[a:b]).translate(_HOMOGLYPH_TABLE)
        for ch in folded:
            if unicodedata.category(ch) == "Cf":  # zero-width space / joiner, bidi marks, BOM
                continue
            chars.append(ch)
            starts.append(a)
            ends.append(b)
    return chars, starts, ends


def _collapse_spaced(chars: list[str], starts: list[int], ends: list[int]):  # type: ignore[no-untyped-def]
    flat = "".join(chars)
    keep = [True] * len(chars)
    for m in _SPACED.finditer(flat):
        for i in range(m.start(), m.end()):
            if re.fullmatch(r"[\s.\-_]", flat[i]):
                keep[i] = False
    return (
        [c for c, k in zip(chars, keep, strict=True) if k],
        [s for s, k in zip(starts, keep, strict=True) if k],
        [e for e, k in zip(ends, keep, strict=True) if k],
    )


def _squeeze(chars: list[str], starts: list[int], ends: list[int]):  # type: ignore[no-untyped-def]
    out_c: list[str] = []
    out_s: list[int] = []
    out_e: list[int] = []
    for c, s, e in zip(chars, starts, ends, strict=True):
        if c.isspace():
            if out_c and out_c[-1] == " ":
                out_e[-1] = e
                continue
            c = " "
        out_c.append(c)
        out_s.append(s)
        out_e.append(e)
    return out_c, out_s, out_e


def _decoded_chunks(original: str) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    for m in _B64.finditer(original):
        try:
            raw = base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4), validate=True)
            text = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if text and sum(ch.isprintable() or ch.isspace() for ch in text) / len(text) > 0.95:
            found.append((text, m.start(), m.end()))
    if len(re.findall(r"%[0-9A-Fa-f]{2}", original)) >= 3:  # URL-encoded text: decode it whole
        text = unquote(original, errors="replace")
        if text != original:
            found.append((text, 0, len(original)))
    return found


def normalise(text: str) -> Normalised:
    """The scanning view of `text` with an index map back into it."""
    text = text[:MAX_SCAN_CHARS]
    chars, starts, ends = _fold(text)
    chars, starts, ends = _collapse_spaced(chars, starts, ends)
    for decoded, a, b in _decoded_chunks(text):
        d_chars, _, _ = _fold(decoded)
        d_chars, d_s, d_e = _collapse_spaced(d_chars, [a] * len(d_chars), [b] * len(d_chars))
        chars += ["\n", *d_chars]
        starts += [b, *d_s]
        ends += [b, *d_e]
    chars, starts, ends = _squeeze(chars, starts, ends)
    return Normalised("".join(chars), tuple(starts), tuple(ends))


def _nfc_pattern(p: str) -> str:
    return unicodedata.normalize("NFKC", p)


# (code, weight, pattern). Weight is the score of the rule alone; >= INJECTION_THRESHOLD is enough
# to call the text an injection. Weak rules need a companion (or hidden/metadata placement).
_RULES: tuple[tuple[str, int, re.Pattern[str]], ...] = tuple(
    (code, weight, re.compile(_nfc_pattern(pattern), re.I | re.M))
    for code, weight, pattern in (
        ("ROLE_MARKER", 70, r"(^|[\s\[<(])(system|assistant|developer)\s*[:：]"),
        (
            "OVERRIDE",
            80,
            r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|"
            r"your)\b.{0,20}\b(instructions?|rules?|prompts?|guidelines?)\b",
        ),
        ("ROLE_PLAY", 60, r"\byou are now\b|\bact as (an? )?(admin|system|developer)\b"),
        ("DEVELOPER_MODE", 70, r"\b(developer|debug|god|jailbreak|unrestricted)\s+mode\b"),
        (
            "CONCEAL_FROM_USER",
            70,
            r"\b(do\s*n[o']?t|never|without)\b.{0,12}\b(tell|inform|notify|alert|warn|mention|"
            r"show)\b.{0,20}\b(the\s+)?(user|buyer|customer|owner|anyone)\b",
        ),
        (
            "MONEY_COMMAND",
            75,
            r"\b(release|transfer|send|wire|pay(\s+out)?|approve|disburse)\b\s+(the\s+|this\s+)?"
            r"(full|all|entire|remaining|whole)?\s*(payment|funds?|money|tranche|escrow|balance)",
        ),
        (
            "MONEY_TO_ACCOUNT",
            75,
            r"(^|[.!?\n]\s*|\b(please|kindly|urgent(ly)?|immediately|asap)\b\W{0,3}(\w+\s+){0,2})"
            r"(wire|transfer|send|remit|pay)\b.{0,40}"
            r"(\b(usd|cny|rmb|bdt)\b|[$¥৳]|\baccount\b|\bbeneficiary\b)"
            r"|\b(wire|transfer|send|remit|pay)\b.{0,40}\b(to|into|via)\b.{0,40}"
            r"\b(account|a/c|beneficiary|iban|swift|wallet|new bank|account details)\b"
            r"|\b(wire|transfer|send|remit|pay)\b.{0,60}\d[\d \-]{6,}\d",
        ),
        (
            "CHANGE_ACCOUNT",
            75,
            r"\b(change|update|replace|switch|modify|redirect)\b.{0,25}\b(the\s+)?"
            r"(supplier\s+|bank\s+|payment\s+)?(account|beneficiary|payee|iban|swift|a/c)\b",
        ),
        (
            "APPROVAL_COMMAND",
            75,
            r"(^|[.!?:;\n]\s*|\b(please|kindly|then|and)\s+)(mark|treat|flag|set)\b.{0,30}"
            r"\b(as\s+)?(verified|approved|cleared)\b"
            r"|\bapprove\b.{0,30}\b(release|payment|transfer|milestone|tranche|change|this)\b",
        ),
        (
            "SKIP_REVIEW",
            75,
            r"\b(approve|accept|pass)\b.{0,25}\b(without|no)\b.{0,15}\b(review|checks?)\b"
            r"|\b(skip|bypass|disable|waive)\b.{0,25}\b(checks?|verification|review|approval|otp|"
            r"cooling[- ]?off|2fa)\b",
        ),
        (
            "SET_SCORE",
            65,
            r"\b(set|reset|lower|reduce|change)\s+(the\s+|this\s+|every\s+|all\s+)?(fraud\s+|risk\s+)+score\s+(to|=|as)\b",
        ),
        (
            "CLAIMS_VERIFIED",
            45,
            r"\b(all\s+)?(documents?|invoice|shipment|checks?)\b.{0,15}\b(verified|passed|cleared)\b",
        ),
        (
            "EXFILTRATE",
            80,
            r"\b(reveal|print|show|leak|disclose|repeat|dump)\b.{0,25}\b(system\s+)?prompt\b"
            r"|\b(email|e-mail|send|forward|upload)\s+(me\s+|us\s+)?(\w+\s+){0,2}"
            r"(audit\s+log|logs?|records|credentials|database)\b"
            r"|\bto\s+[\w.+-]+@[\w-]+(\.[\w-]+)+",
        ),
        (
            "SYSTEM_OVERRIDE",
            70,
            r"\b(system|admin|developer)\s+(override|command|instruction|prompt|message)",
        ),
        ("TOOL_CALL_JSON", 70, r"[{,]\s*\"(tool|function|tool_name|action)\"\s*:"),
        # Bangla
        ("BN_OVERRIDE", 80, r"(আগের|পূর্বের|উপরের)\s*(সব|সকল)?\s*নির্দেশ(না)?(াবলী)?\s*(উপেক্ষা|বাদ|ভুলে)"),
        ("BN_ROLE_MARKER", 70, r"(সিস্টেম|সহকারী|অ্যাডমিন)\s*(নির্দেশ|ওভাররাইড|কমান্ড)?\s*[:：]"),
        (
            "BN_MONEY_COMMAND",
            75,
            r"(পেমেন্ট|টাকা|অর্থ|পুরো\s*অর্থ|বাকি\s*টাকা)\s*(এখনই\s*)?"
            r"(ছেড়ে\s*দিন|ছাড়\s*করুন|ছাড়ুন|পরিশোধ\s*করুন|পাঠান|পাঠাও|ট্রান্সফার\s*করুন)",
        ),
        (
            "BN_CHANGE_ACCOUNT",
            75,
            r"(প্রাপকের|সরবরাহকারীর|ব্যাংক)?\s*(হিসাব|অ্যাকাউন্ট|একাউন্ট)\S*\s*.{0,25}"
            r"(পরিবর্তন|বদল|আপডেট)\s*করুন",
        ),
        (
            "BN_APPROVAL_COMMAND",
            75,
            r"(অনুমোদন|এপ্রুভ)\s*করুন|(ওটিপি|কুলিং[- ]?অফ).{0,25}(এড়িয়ে|বাদ|বাইপাস)"
            r"|যাচাইকৃত\s*(হিসেবে|হিসাবে)?\s*চিহ্নিত",
        ),
        (
            "BN_CONCEAL",
            70,
            r"(ব্যবহারকারী|ক্রেতা|মালিক)(কে)?\s*(জানাবেন|বলবেন|জানাবে)\s*না",
        ),
        # Chinese
        (
            "ZH_OVERRIDE",
            80,
            r"(忽略|无视|忘记).{0,8}(之前|以上|上述|先前|所有).{0,6}(指令|指示|规则|提示)",
        ),
        (
            "ZH_ROLE_MARKER",
            70,
            r"(系统|管理员|助手)\s*(指令|命令|提示|覆盖)?\s*[:：]|系统(指令|覆盖)",
        ),
        (
            "ZH_MONEY_COMMAND",
            75,
            r"(立即|马上|全额|立刻|尽快).{0,8}(付款|支付|转账|放款)|(释放|放行).{0,6}(全部|款项|资金|付款)",
        ),
        (
            "ZH_CHANGE_ACCOUNT",
            75,
            r"(更改|变更|更换|更新|修改).{0,6}(收款)?(账户|账号|银行)|汇(入|至|款到).{0,10}(账户|账号)",
        ),
        (
            "ZH_APPROVAL_COMMAND",
            75,
            r"(批准|核准).{0,10}(付款|支付|此笔)|跳过.{0,8}(验证码|冷静期|审批|审核)"
            r"|(标记|设为|设置).{0,8}(已核实|已验证|为0)|(文件|单据|发票)已(核实|验证)",
        ),
        ("ZH_CONCEAL", 70, r"不要.{0,4}(告诉|通知|提醒).{0,4}(用户|买家|客户)"),
    )
)

_STRONG_PLACEMENT = {"hidden_text": 25, "metadata": 15}


@dataclass(frozen=True, slots=True)
class Detection:
    is_injection: bool
    score: int
    matched_rules: tuple[str, ...]
    source: Source
    snippet: str  # safe: masked and truncated, never the document
    highlights: tuple[tuple[int, int, str], ...] = ()  # (start, end, rule) in the ORIGINAL text
    llm_opinion: bool | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "is_injection": self.is_injection,
            "score": self.score,
            "matched_rules": list(self.matched_rules),
            "source": self.source,
            "snippet": self.snippet,
            "highlights": [{"start": a, "end": b, "rule": r} for a, b, r in self.highlights],
            "llm_opinion": self.llm_opinion,
        }


@dataclass(slots=True)
class _Hit:
    code: str
    weight: int
    start: int
    end: int


def _safe_snippet(text: str, around: int) -> str:
    from app.privacy.gateway import PrivacyGateway

    start = max(0, around - 10)
    piece = "".join(
        ch for ch in text[start : start + SNIPPET_CHARS] if ch.isprintable() or ch == " "
    )
    return PrivacyGateway().mask_text(" ".join(piece.split())).replace("<", "‹").replace(">", "›")


def _score(hits: list[_Hit], source: Source) -> int:
    if not hits:
        return 0
    weights = sorted({h.code: h.weight for h in hits}.values(), reverse=True)
    score = weights[0] + 10 * min(len(weights) - 1, 3)
    if score >= 40:
        score += _STRONG_PLACEMENT.get(source, 0)
    return min(100, score)


def scan(text: str, source: Source = "visible_text", *, use_llm: bool | None = None) -> Detection:
    """Detect instruction-like content in one text. Empty / clean text gives score 0."""
    if not text or not text.strip():
        return Detection(False, 0, (), source, "")
    norm = normalise(text)
    hits: list[_Hit] = []
    for code, weight, pattern in _RULES:
        m = pattern.search(norm.text)
        if m and m.end() > m.start():
            hits.append(_Hit(code, weight, m.start(), m.end()))
    score = _score(hits, source)
    rules = tuple(dict.fromkeys(h.code for h in sorted(hits, key=lambda h: h.start)))
    highlights = tuple(
        (*norm.original_span(h.start, h.end), h.code)
        for h in sorted(hits, key=lambda h: h.start)
        if h.end <= len(norm.text)
    )
    opinion: bool | None = None
    if use_llm is None:
        from app.config import get_settings

        use_llm = get_settings().injection_llm_check
    if use_llm and 15 <= score < INJECTION_THRESHOLD + 20:
        from app.security.injection.llm_check import second_opinion

        opinion = second_opinion(text)
        if opinion and score < INJECTION_THRESHOLD:  # may only escalate a borderline text
            score = INJECTION_THRESHOLD
            rules = (*rules, "LLM_SECOND_OPINION")
    return Detection(
        is_injection=score >= INJECTION_THRESHOLD,
        score=score,
        matched_rules=rules,
        source=source,
        snippet=_safe_snippet(norm.text, hits[0].start) if hits else "",
        highlights=highlights,
        llm_opinion=opinion,
    )


def scan_document(
    visible: str, hidden: list[str], metadata: dict[str, str], *, use_llm: bool | None = None
) -> list[Detection]:
    """One Detection per placement that carries an injection (visible, hidden, metadata)."""
    out: list[Detection] = []
    for source, text in (
        ("hidden_text", "\n".join(hidden)),
        ("visible_text", visible),
        ("metadata", "\n".join(f"{v}" for v in metadata.values())),
    ):
        d = scan(text, source, use_llm=use_llm)  # type: ignore[arg-type]
        if d.is_injection:
            out.append(d)
    return out
