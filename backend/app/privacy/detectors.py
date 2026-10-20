"""Identifier detectors for the Privacy Gateway (SR-4).

Text is first normalised into a *view* (NFKC, Bangla/Chinese digits → ASCII, zero-width
characters dropped, optionally spaced digits collapsed) with an index map back to the original,
so obfuscated values such as "০১৭১১ ২২৩ ৩৪৪" or "0 1 7 1 1 …" are still found and the span that
is replaced is the one the user actually typed. Detectors are regex + validation; every hit has a
type, a span in the original text and a confidence.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.onboarding_validation import uscc_valid

NID = "NID"
PASSPORT = "PASSPORT"
PHONE = "PHONE"
ACCT = "ACCT"
IBAN = "IBAN"
SWIFT = "SWIFT"
EMAIL = "EMAIL"
NAME = "NAME"
AMT = "AMT"
BIZID = "BIZID"  # trade licence, IRC, TIN/BIN, USCC

TYPES = (NID, PASSPORT, PHONE, ACCT, IBAN, SWIFT, EMAIL, NAME, AMT, BIZID)
# Higher wins when two hits overlap (an account number never beats the phone it contains).
PRIORITY = {
    EMAIL: 9,
    IBAN: 8,
    SWIFT: 7,
    PASSPORT: 7,
    BIZID: 7,
    NID: 6,
    PHONE: 5,
    ACCT: 4,
    NAME: 3,
    AMT: 2,
}
LABELS = {
    NID: ("national ID", "জাতীয় পরিচয়পত্র"),
    PASSPORT: ("passport", "পাসপোর্ট"),
    PHONE: ("phone", "ফোন নম্বর"),
    ACCT: ("account", "অ্যাকাউন্ট নম্বর"),
    IBAN: ("IBAN", "IBAN"),
    SWIFT: ("SWIFT code", "SWIFT কোড"),
    EMAIL: ("email", "ইমেইল"),
    NAME: ("person name", "ব্যক্তির নাম"),
    AMT: ("amount", "পরিমাণ"),
    BIZID: ("business registration number", "ব্যবসা নিবন্ধন নম্বর"),
}

_ZERO_WIDTH = frozenset(chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD, 0x180E))
_SEPARATORS = frozenset(chr(c) for c in (0x20, 0xA0, 0x2009, 0x202F, 0x2D, 0x2010, 0x2011, 0x2212))


@dataclass(frozen=True, slots=True)
class Hit:
    type: str
    start: int  # span in the ORIGINAL text, end exclusive
    end: int
    confidence: float
    normalized: str  # canonical form: digits only for numbers, lower-case for names/emails
    obfuscated: bool = (
        False  # the original differs from the canonical form (spaces, Bangla digits…)
    )


@dataclass(slots=True)
class View:
    text: str
    index: list[int]  # view position → original position
    original: str

    def span(self, start: int, end: int) -> tuple[int, int]:
        return self.index[start], self.index[end - 1] + 1


def _digit(ch: str) -> str | None:
    if ch.isascii():
        return ch if ch.isdigit() else None
    if unicodedata.category(ch) == "Nd":
        return str(unicodedata.digit(ch))
    return None


# Cyrillic letters that look like Latin ones (code points), folded so a spoofed label still matches.
_HOMOGLYPHS = {
    cyr: lat
    for cyr, lat in zip(
        (
            0x410,
            0x412,
            0x421,
            0x415,
            0x41D,
            0x41A,
            0x41C,
            0x41E,
            0x420,
            0x422,
            0x425,
            0x430,
            0x435,
            0x43E,
            0x440,
            0x441,
            0x443,
            0x445,
            0x456,
            0x458,
            0x455,
        ),
        "ABCEHKMOPTXaeopcyxijs",
        strict=True,
    )
}
_LOOSE_SEPARATORS = frozenset(".()/")


def build_view(text: str, *, collapse: bool, loose: bool = False) -> View:
    """Normalised copy of `text`. With `collapse`, a single space or hyphen between two digits is
    dropped so grouped / spaced numbers become one run."""
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if ch in _ZERO_WIDTH:
            continue
        d = _digit(ch)
        piece = d if d is not None else unicodedata.normalize("NFKC", ch).translate(_HOMOGLYPHS)
        for c in piece:
            out.append(c)
            idx.append(i)
    if collapse:
        out, idx = _collapse(out, idx, _SEPARATORS | (_LOOSE_SEPARATORS if loose else frozenset()))
    return View("".join(out), idx, text)


def _collapse(
    chars: list[str], idx: list[int], seps: frozenset[str]
) -> tuple[list[str], list[int]]:
    """Drop runs of 1-2 separator characters that sit between two digits."""
    keep = [True] * len(chars)
    n, i = len(chars), 0
    while i < n:
        if chars[i] in seps:
            j = i
            while j < n and chars[j] in seps:
                j += 1
            if j - i <= 2 and i > 0 and j < n and chars[i - 1].isdigit() and chars[j].isdigit():
                for k in range(i, j):
                    keep[k] = False
            i = j
        else:
            i += 1
    return (
        [c for c, k in zip(chars, keep, strict=True) if k],
        [x for x, k in zip(idx, keep, strict=True) if k],
    )


# --- patterns ---------------------------------------------------------------------------------

_NID_CTX = (
    r"(?:NID|N\.I\.D|National\s*ID(?:entity)?(?:\s*Card)?|জাতীয়\s*পরিচয়\s*পত্র|এনআইডি|身份证|身份證)"
)
_ACCT_CTX = (
    r"(?:A/C|AC\s*No|Acct|Account(?:\s*(?:No|Number|Num|#))?|ACCT|账号|账户|帐号|帐户|賬號|賬戶|"
    r"হিসাব\s*(?:নম্বর|নং|নাম্বার)|অ্যাকাউন্ট(?:\s*(?:নম্বর|নং))?|একাউন্ট(?:\s*(?:নম্বর|নং))?|"
    r"অ্যাকাউন্ট|হিসাব)"
)
_PASSPORT_CTX = r"(?:passport|পাসপোর্ট|护照|護照)"
_SWIFT_CTX = r"(?:SWIFT|BIC)(?:\s*(?:code|/BIC))?"
_GAP = r"[^\d]{0,28}?"
_BIZ_CTX = (
    r"(?:trade\s*licen[cs]e(?:\s*(?:no|number|#))?|licen[cs]e\s*(?:no|number|#)|\bIRC(?:\s*(?:no|number|#))?|"
    r"import\s*registration(?:\s*certificate)?(?:\s*(?:no|number|#))?|\bTIN(?:\s*(?:no|number|#))?|\bBIN\b|"
    r"\bUSCC\b|unified\s*social\s*credit\s*code|统一社会信用代码|社会信用代码|营业执照(?:号|编号)?|"
    r"ট্রেড\s*লাইসেন্স|টিআইএন|আইআরসি)"
)
BIZ_LABELLED = re.compile(
    rf"{_BIZ_CTX}\.?[\s:\uff1a#-]{{0,6}}([A-Z0-9][A-Z0-9/\-]{{4,30}}[A-Z0-9])(?![A-Z0-9])", re.I
)
USCC_RE = re.compile(r"(?<![A-Za-z0-9])[0-9A-HJ-NP-RT-UW-Y]{18}(?![A-Za-z0-9])")

NID_BEFORE = re.compile(rf"{_NID_CTX}{_GAP}(?<!\d)(\d{{17}}|\d{{13}}|\d{{10}})(?!\d)", re.I)
NID_AFTER = re.compile(rf"(?<!\d)(\d{{17}}|\d{{13}}|\d{{10}})(?!\d)[^\d\n]{{0,6}}{_NID_CTX}", re.I)
ACCT_BEFORE = re.compile(rf"{_ACCT_CTX}{_GAP}(?<![\d])(\d{{8,20}})(?!\d)", re.I)
# Labelled alphanumeric / partly starred account ids ("Account no.: SIM-CN-9713-****-5170").
ACCT_ALNUM = re.compile(
    rf"{_ACCT_CTX}{_GAP}(?<![\w*])([A-Z0-9*][A-Z0-9*\-]{{6,30}}[A-Z0-9*])(?![\w*])"
)
# Labelled account holder / beneficiary: the rest of the line is a name, known or not.
HOLDER_RE = re.compile(
    r"(?:account\s*holder(?:\s*name)?|beneficiary(?:\s*name)?|holder\s*name|户名|收款人|收款方|"
    r"হিসাবধারী|প্রাপক)\s*[:\uff1a]\s*([^\n]{3,80}?)\s*(?=\n|$)",
    re.I,
)
PASSPORT_RE = re.compile(rf"{_PASSPORT_CTX}{_GAP}\b([A-Z]{{1,2}}\s?\d{{7,9}})\b", re.I)
PHONE_BD = re.compile(r"(?<![\w.])(\+?880|0)1[3-9]\d{8}(?!\d)")
PHONE_CN = re.compile(r"(?<![\w.])(\+?86)?1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?![A-Za-z0-9])"
)
SWIFT_RE = re.compile(
    rf"{_SWIFT_CTX}[\s:#-]{{0,6}}\b([A-Z]{{4}}[A-Z]{{2}}[A-Z0-9]{{2}}(?:[A-Z0-9]{{3}})?)\b"
)

_CCY = r"(?:USD|US\$|CNY|RMB|BDT|EUR|GBP|HKD|JPY|INR|Tk\.?|TK\.?|Taka)"
_SYM = r"[$¥￥৳€£]"
_NUM = r"\d[\d,]*(?:\.\d+)?"
AMT_BEFORE = re.compile(rf"(?:(?<![A-Za-z]){_CCY}|{_SYM})\s*({_NUM})", re.I)
AMT_AFTER = re.compile(rf"({_NUM})\s*(?:{_CCY}(?![A-Za-z])|টাকা|元|块|塊|万元|万)")


LONG_DIGITS = re.compile(r"(?<![\d.])\d{13,18}(?![\d])")
DATE_RUN = re.compile(r"\d{4}[-/.]\d{2}[-/.]\d{2}")


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _canonical_phone(raw: str) -> str:
    d = _digits(raw)
    if d.startswith("880") and len(d) == 13:
        return "0" + d[3:]
    if d.startswith("86") and len(d) == 13:
        return d[2:]
    return d


def _iban_ok(raw: str) -> bool:
    s = re.sub(r"\s", "", raw).upper()
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    try:
        return int("".join(str(int(c, 36)) for c in rearranged)) % 97 == 1
    except ValueError:
        return False


def _hit(view: View, kind: str, start: int, end: int, conf: float, canon: str) -> Hit:
    s, e = view.span(start, end)
    raw = view.original[s:e]
    obf = (
        not raw.isascii()
        or any(ch in _ZERO_WIDTH for ch in raw)
        or (kind not in (NAME, EMAIL, AMT) and any(ch in _SEPARATORS for ch in raw))
    )
    return Hit(kind, s, e, conf, canon, obf)


def _group(m: re.Match[str]) -> tuple[int, int]:
    return m.start(1), m.end(1)


def _detect_numbers(view: View) -> Iterable[Hit]:
    t = view.text
    for m in EMAIL_RE.finditer(t):
        yield _hit(view, EMAIL, m.start(), m.end(), 0.99, m.group().lower())
    for m in IBAN_RE.finditer(t):
        if _iban_ok(m.group()):
            yield _hit(view, IBAN, m.start(), m.end(), 0.97, re.sub(r"\s", "", m.group()).upper())
    for m in SWIFT_RE.finditer(t):
        s, e = _group(m)
        yield _hit(view, SWIFT, s, e, 0.9, m.group(1).upper())
    for m in PASSPORT_RE.finditer(t):
        s, e = _group(m)
        yield _hit(view, PASSPORT, s, e, 0.85, re.sub(r"\s", "", m.group(1)).upper())
    for pat, conf in ((NID_BEFORE, 0.95), (NID_AFTER, 0.9)):
        for m in pat.finditer(t):
            s, e = _group(m)
            yield _hit(view, NID, s, e, conf, m.group(1))
    loose = build_view(view.original, collapse=True, loose=True)
    for pat, conf in ((PHONE_BD, 0.97), (PHONE_CN, 0.9)):
        for m in pat.finditer(loose.text):
            yield _hit(loose, PHONE, m.start(), m.end(), conf, _canonical_phone(m.group()))
    for m in BIZ_LABELLED.finditer(t):
        s_, e_ = _group(m)
        if sum(c.isdigit() for c in m.group(1)) >= 4:
            yield _hit(view, BIZID, s_, e_, 0.9, re.sub(r"[^A-Za-z0-9]", "", m.group(1)).upper())
    for m in USCC_RE.finditer(t):  # a valid check character makes a bare USCC unmistakable
        if uscc_valid(m.group()):
            yield _hit(view, BIZID, m.start(), m.end(), 0.95, m.group())
    for m in LONG_DIGITS.finditer(t):  # unlabelled 13-18 digit numbers: treated as accounts
        raw = view.original[view.span(m.start(), m.end())[0] : view.span(m.start(), m.end())[1]]
        if not DATE_RUN.fullmatch(raw):
            yield _hit(view, ACCT, m.start(), m.end(), 0.6, m.group())
    for m in HOLDER_RE.finditer(t):
        s, e = _group(m)
        if "⟦" in m.group(1):  # already a token
            continue
        yield _hit(view, NAME, s, e, 0.85, " ".join(m.group(1).casefold().split()))
    for m in ACCT_ALNUM.finditer(t):
        s, e = _group(m)
        raw = view.original[view.span(s, e)[0] : view.span(s, e)[1]]
        if sum(c.isdigit() for c in m.group(1)) >= 4 and not DATE_RUN.fullmatch(raw):
            yield _hit(view, ACCT, s, e, 0.85, re.sub(r"[\s-]", "", m.group(1)).upper())
    for m in ACCT_BEFORE.finditer(t):
        s, e = _group(m)
        if DATE_RUN.fullmatch(view.original[view.span(s, e)[0] : view.span(s, e)[1]]):
            continue
        yield _hit(view, ACCT, s, e, 0.9, m.group(1))


def _detect_amounts(view: View) -> Iterable[Hit]:
    for pat in (AMT_BEFORE, AMT_AFTER):
        for m in pat.finditer(view.text):
            s, e = _group(m)
            yield _hit(view, AMT, s, e, 0.9, m.group(1).replace(",", ""))


def _detect_known(text: str, known: dict[str, set[str]]) -> Iterable[Hit]:
    """Values the platform already holds (account holders, stored account numbers/phones)."""
    for kind, values in known.items():
        for value in values:
            v = value.strip()
            if len(v) < 4:
                continue
            canon = v.casefold() if kind == NAME else _digits(v) or v
            if kind == NAME:
                pat = re.compile(rf"(?<![\w]){re.escape(v).replace(r'\ ', r'\s+')}(?![\w])", re.I)
                for m in pat.finditer(text):
                    yield Hit(NAME, m.start(), m.end(), 0.9, canon)
            else:
                view = build_view(text, collapse=True)
                needle = _digits(v)
                if len(needle) < 6:
                    continue
                for m in re.finditer(rf"(?<!\d){re.escape(needle)}(?!\d)", view.text):
                    s, e = view.span(m.start(), m.end())
                    yield Hit(kind, s, e, 0.95, needle, view.original[s:e] != needle)


def _resolve(hits: list[Hit]) -> list[Hit]:
    """Non-overlapping hits: higher priority first, then longer, then earlier."""
    ordered = sorted(hits, key=lambda h: (-PRIORITY[h.type], -(h.end - h.start), h.start))
    taken: list[Hit] = []
    for h in ordered:
        if all(h.end <= t.start or h.start >= t.end for t in taken):
            taken.append(h)
    return sorted(taken, key=lambda h: h.start)


def detect(
    text: str,
    *,
    mask_amounts: bool = True,
    known: dict[str, set[str]] | None = None,
) -> list[Hit]:
    """All identifier hits in `text`, sorted by position, no overlaps."""
    if not text:
        return []
    hits: list[Hit] = list(_detect_numbers(build_view(text, collapse=True)))
    if mask_amounts:
        hits.extend(_detect_amounts(build_view(text, collapse=False)))
    if known:
        hits.extend(_detect_known(text, known))
    return _resolve(hits)
