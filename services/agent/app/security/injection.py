"""Instruction detector for untrusted text (SR-3).

P08 scope: plain-text patterns (EN/BN/ZH) applied to tool results before the model sees them.
Phase 5.x adds base64/homoglyph decoding and hidden-text findings from forensics.
"""

import re
import unicodedata
from dataclasses import dataclass

EXCERPT_CHARS = 60

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ROLE_MARKER", re.compile(r"(^|[\s\[<(])(system|assistant|developer)\s*[:\uff1a]", re.I)),
    (
        "OVERRIDE",
        re.compile(
            r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|all)\b"
            r".{0,20}\b(instructions?|rules?|prompts?)\b",
            re.I,
        ),
    ),
    (
        "MONEY_TO_ACCOUNT",
        re.compile(
            # A payment request: the verb starts a sentence or follows a request word, and an
            # amount/currency/account follows ("Pay USD 48,000 …", "Kindly pay ¥320,000 …").
            r"(^|[.!?\n]\s*|\b(please|kindly|urgent(ly)?|immediately|asap)\b\W{0,3}(\w+\s+){0,2})"
            r"(wire|transfer|send|remit|pay)\b.{0,40}"
            r"(\b(usd|cny|rmb|bdt)\b|[$¥৳]|\baccount\b|\bbeneficiary\b)"
            # … to/into/via a new or named destination
            r"|\b(wire|transfer|send|remit|pay)\b.{0,40}\b(to|into|via)\b.{0,40}"
            r"\b(account|a/c|beneficiary|iban|swift|wallet|new bank|account details)\b"
            # … or an account number (spaces and dashes allowed)
            r"|\b(wire|transfer|send|remit|pay)\b.{0,60}\d[\d \-]{6,}\d",
            re.I | re.M,
        ),
    ),
    (
        "APPROVAL_COMMAND",
        re.compile(
            r"\b(mark|treat|flag)\b.{0,30}\b(as\s+)?(verified|approved|cleared)\b"
            r"|\bapprove\b.{0,30}\b(release|payment|transfer|milestone|tranche|change)\b",
            re.I,
        ),
    ),
    (
        "MONEY_COMMAND",
        re.compile(
            r"\b(release|transfer|send|wire|pay(\s+out)?|approve)\b\s+(the\s+)?"
            r"(full|all|entire|remaining|whole)?\s*(payment|funds?|money|tranche|escrow|balance)",
            re.I,
        ),
    ),
    ("ROLE_PLAY", re.compile(r"\byou are now\b|\bact as (an? )?(admin|system)\b", re.I)),
    ("TOOL_CALL_JSON", re.compile(r"[{,]\s*\"(tool|function|tool_name|action)\"\s*:", re.I)),
    ("BN_COMMAND", re.compile(r"নির্দেশ(না)?\s*(উপেক্ষা|বাদ)|(পেমেন্ট|টাকা)\s*(ছাড়|পাঠাও|ট্রান্সফার)")),
    (
        "ZH_COMMAND",
        re.compile(
            r"(忽略|无视).{0,8}(指令|指示|规则)|(释放|转账|支付).{0,6}(全部|款项|资金)|系统\s*[:\uff1a]"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    excerpt: str


def normalize(text: str) -> str:
    """NFKC (full-width to ASCII) and drop format characters (zero-width spaces/joiners)."""
    folded = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")


def detect_instructions(text: str) -> list[Finding]:
    text = normalize(text)
    findings: list[Finding] = []
    for code, pattern in _PATTERNS:
        m = pattern.search(text)
        if m:
            start = max(0, m.start() - 10)
            excerpt = " ".join(text[start : start + EXCERPT_CHARS].split())
            findings.append(Finding(code, excerpt))
    return findings
