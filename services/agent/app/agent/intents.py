"""Deterministic routing helpers: keyword intent rules (router fallback and mock model) and
script-based language detection. Pure functions, no I/O."""

import re

from app.agent.state import Intent, Lang

DEAL_REF = re.compile(r"\bSETU-\d{4}-\d{4}\b", re.I)
_BENGALI = re.compile(r"[ঀ-৿]")
_CJK = re.compile(r"[一-鿿]")

# Checked in order; the first rule with a matching keyword wins.
_RULES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        "documents",
        (
            "bill of lading",
            "b/l",
            "invoice",
            "packing list",
            "certificate of origin",
            "document",
            "forensic",
            "forged",
            "tamper",
            "ডকুমেন্ট",
            "চালান",
            "বিল অফ লেডিং",
            "提单",
            "发票",
            "文件",
        ),
    ),
    (
        "out_of_scope",
        (
            "football",
            "cricket",
            "match",
            "weather",
            "movie",
            "song",
            "recipe",
            "election",
            "joke",
            "ফুটবল",
            "ক্রিকেট",
            "আবহাওয়া",
            "足球",
            "天气",
        ),
    ),
    (
        "cashflow",
        (
            "cash",
            "dashboard",
            "shortfall",
            "balance",
            "forecast",
            "liquidity",
            "alert",
            "সতর্ক",
            "অ্যালার্ট",
            "ক্যাশ",
            "নগদ",
            "টাকা কম",
            "ড্যাশবোর্ড",
            "现金",
        ),
    ),
    (
        "financing",
        (
            "loan",
            "financ",
            "credit",
            "lender",
            "borrow",
            "ঋণ",
            "লোন",
            "অর্থায়ন",
            "ফাইন্যান্সিং",
            "সস্তা",
            "贷款",
            "融资",
        ),
    ),
    (
        "analysis",
        (
            "margin",
            "landed",
            "break-even",
            "break even",
            "profit",
            "duty",
            "price",
            "fx",
            "exchange rate",
            "usd",
            "cny",
            "rmb",
            "currency",
            "scorecard",
            "supplier score",
            "best supplier",
            "monthly summary",
            "summary",
            "সারাংশ",
            "সারসংক্ষেপ",
            "this month's summary",
            "what if",
            "মার্জিন",
            "ল্যান্ডেড",
            "খরচ",
            "লাভ",
            "বাঁচবে",
            "সাপ্লায়ার",
            "মাসিক",
            "成本",
            "利润",
            "汇率",
        ),
    ),
    (
        "deal_status",
        (
            "deal",
            "order",
            "milestone",
            "shipment",
            "status",
            "due",
            "ডিল",
            "অর্ডার",
            "মাইলস্টোন",
            "订单",
        ),
    ),
    (
        "how_it_works",
        (
            "how does",
            "how do",
            "how it works",
            "escrow",
            "tier",
            "approval",
            "what is setu",
            "fob",
            "cif",
            "incoterm",
            "advance payment",
            "bangladesh bank",
            "মানে",
            "নিয়ম",
            "কিভাবে",
            "কীভাবে",
            "এসক্রো",
            "怎么",
            "托管",
        ),
    ),
)
_GREETINGS = (
    "hello",
    "hi",
    "hey",
    "good morning",
    "good evening",
    "salam",
    "assalamu",
    "হ্যালো",
    "নমস্কার",
    "আসসালামু",
    "你好",
)
SMART_INTENTS: frozenset[Intent] = frozenset({"documents"})
GREETING_MAX_WORDS = 4


def _has(q: str, key: str) -> bool:
    # ASCII keys match at a word start ("loan" ~ "loans"); Bangla/Chinese keys as substrings.
    return bool(re.search(r"\b" + re.escape(key), q)) if key.isascii() else key in q


def keyword_intent(text: str) -> Intent:
    q = text.lower()
    for intent, keys in _RULES:
        if any(_has(q, k) for k in keys):
            return intent
    if DEAL_REF.search(q):
        return "deal_status"
    words = re.findall(r"\w+", q)
    if len(words) <= GREETING_MAX_WORDS and any(_has(q, g) for g in _GREETINGS):
        return "greeting"
    return "analysis"


def needs_smart(intent: Intent, text: str) -> bool:
    return intent in SMART_INTENTS


def detect_language(text: str) -> Lang | None:
    """Script of the message: any Bangla → bn, any Chinese → zh, Latin letters → en."""
    if _BENGALI.search(text):
        return "bn"
    if _CJK.search(text):
        return "zh"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None
