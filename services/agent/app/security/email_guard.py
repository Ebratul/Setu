"""Deterministic reader for pasted e-mails ("Check a suspicious email", SR-6).

E-mail text is data. This module never changes anything: it only says whether the text asks to
move money to a different account. Such a request is always BLOCKED, whatever else the text says;
the only way to change a receiving account is the supplier portal plus the buyer's Tier 3 approval.
No model is involved and no raw text leaves this function (callers store a hash and codes only).
"""

import re
from dataclasses import dataclass, field

from app.security.injection import Finding, detect_instructions, normalize

MAX_CHARS = 20_000

_ACCOUNT_CHANGE = re.compile(
    r"(new|changed?|updated?|different|another|alternative|replacement)\W+(\w+\W+){0,3}"
    r"(bank|banking|account|a/c|acct|beneficiary|swift|iban)"
    r"|(bank|banking|account|beneficiary|payment|remittance)\W+(\w+\W+){0,3}"
    r"(details?|information|instructions?|particulars)\W+(\w+\W+){0,2}"
    r"(changed?|updated?|revised|new)"
    r"|(bank|account|a/c|beneficiary|payment)\W+(\w+\W+){0,3}(details?|number|information)\W+"
    r"(has|have|are|is)?\W*(changed?|updated?|new)"
    r"|(pay|remit|transfer|send|wire|deposit)\W+(\w+\W+){0,8}"
    r"(to|into)\W+(\w+\W+){0,4}(new|another|different|hong\s*kong|hk)\W+(\w+\W+){0,3}"
    r"(account|bank)"
    r"|(account|bank)\W+(\w+\W+){0,5}(closed|frozen|suspended|audit)",
    re.IGNORECASE,
)
_ACCOUNT_CHANGE_NON_LATIN = re.compile(
    r"(汇入|汇款到|转入|付款到).{0,8}(香港|新|境外).{0,6}(账户|账号)|(নতুন|পরিবর্তিত|বদলে)\s*(ব্যাংক\s*)?(অ্যাকাউন্ট|একাউন্ট)|(新|更换|变更).{0,6}(账户|账号|银行)"
)
_ACCOUNT_NO = re.compile(r"\b(?:SIM-)?[A-Z]{0,4}[-\s]?\d{3,}(?:[-\s]\d{2,}){1,5}\b|\b\d{10,18}\b")
_SWIFT = re.compile(r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")
_URGENCY = re.compile(
    r"\b(urgent|today|immediately|asap|right away|vessel will leave|shipment will be held)\b",
    re.IGNORECASE,
)
_NO_VERIFY = re.compile(
    r"(do not|don't|dont|no need to)\W+(\w+\W+){0,3}(call|phone|verify|confirm|contact)"
    r"|reply to this email only|only (by )?email",
    re.IGNORECASE,
)
_REF = re.compile(r"\bSETU-\d{4}-\d{4}\b")


@dataclass(frozen=True, slots=True)
class EmailReading:
    beneficiary_change: bool
    signals: list[str] = field(default_factory=list)  # stable codes
    deal_refs: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)  # instruction patterns (SR-3)

    @property
    def verdict(self) -> str:
        if self.beneficiary_change:
            return "BLOCKED"
        return "SUSPICIOUS" if self.findings or self.signals else "NO_PAYMENT_CHANGE_FOUND"


def read_email(text: str) -> EmailReading:
    text = normalize(text[:MAX_CHARS])
    signals: list[str] = []
    change = bool(_ACCOUNT_CHANGE.search(text) or _ACCOUNT_CHANGE_NON_LATIN.search(text))
    if change:
        signals.append("ACCOUNT_CHANGE_REQUEST")
        if _ACCOUNT_NO.search(text) or _SWIFT.search(text):
            signals.append("NEW_ACCOUNT_DETAILS")
    if _URGENCY.search(text):
        signals.append("URGENCY_PRESSURE")
    if _NO_VERIFY.search(text):
        signals.append("DISCOURAGES_VERIFICATION")
    refs = sorted(set(_REF.findall(text)))
    return EmailReading(change, signals, refs, detect_instructions(text))
