"""Instruction-like text in documents (SR-3): the shared detector plus document-specific
patterns and de-obfuscation (spaced letters, Cyrillic/Greek look-alikes, zero-width characters).

Only codes and short excerpts leave this module; callers never forward the text to a model.
"""

import re
import unicodedata
from collections.abc import Iterable

from app.domain.kyb import HOMOGLYPHS
from app.security.injection import Finding, detect_instructions

_HOMOGLYPH_TABLE = str.maketrans(HOMOGLYPHS)
_SPACED = re.compile(r"(?<![^\W\d_])(?:[^\W\d_][\s.\-_]){3,}[^\W\d_](?![^\W\d_])")
_DOC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("CLAIMS_VERIFIED", re.compile(r"\b(documents?|invoice|shipment)\b.{0,15}\bverified\b", re.I)),
    (
        "RELEASE_PAYMENT",
        re.compile(r"\brelease\b.{0,15}\b(full\s+)?(payment|funds?|escrow|tranche)", re.I),
    ),
    (
        "SKIP_REVIEW",
        re.compile(
            r"\b(approve|accept|pass)\b.{0,25}\b(without|no)\b.{0,15}\b(review|checks?)\b"
            r"|\b(skip|bypass|disable)\b.{0,20}\b(checks?|verification|review|approval)\b",
            re.I,
        ),
    ),
    (
        "EXFILTRATE",
        re.compile(
            r"\b(reveal|print|show|leak|disclose|repeat|dump)\b.{0,25}\b(system\s+)?prompt\b"
            r"|\b(email|e-mail|send|forward|upload)\b.{0,40}\b(audit\s+log|logs?|records|"
            r"credentials|database|data)\b"
            r"|\bto\s+[\w.+-]+@[\w-]+(\.[\w-]+)+",
            re.I,
        ),
    ),
    (
        "SYSTEM_OVERRIDE",
        re.compile(r"\b(system|admin|developer)\s+(override|command|instruction)", re.I),
    ),
    (
        "ZH_INSTRUCTION",
        re.compile(
            r"(系统|管理员)\s*(指令|命令|提示)|(文件|单据|发票)已(核实|验证)"
            r"|(立即|全额|马上).{0,8}(付款|支付|转账|放款)"
        ),
    ),
)


def deobfuscate(text: str) -> str:
    """NFKC, no format characters, Latin look-alikes, spaced-out words joined."""
    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    folded = folded.translate(_HOMOGLYPH_TABLE)
    return _SPACED.sub(lambda m: re.sub(r"[\s.\-_]", "", m.group(0)), folded)


def scan_text(text: str) -> list[Finding]:
    """Findings for one text; empty when it looks like ordinary document content."""
    if not text or not text.strip():
        return []
    seen: dict[str, Finding] = {}
    variants = [text]
    plain = deobfuscate(text)
    if plain != text:
        variants.append(plain)
    for variant in variants:
        for f in detect_instructions(variant):
            seen.setdefault(f.code, f)
        flat = " ".join(variant.split())
        for code, pattern in _DOC_PATTERNS:
            m = pattern.search(flat)
            if m and code not in seen:
                start = max(0, m.start() - 10)
                seen[code] = Finding(code, flat[start : start + 60])
    return list(seen.values())


def scan_many(texts: Iterable[str]) -> list[Finding]:
    out: dict[str, Finding] = {}
    for t in texts:
        for f in scan_text(t):
            out.setdefault(f.code, f)
    return list(out.values())
