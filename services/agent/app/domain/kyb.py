"""FR-4 supplier KYB: pure, deterministic checks (no I/O, no LLM).

Per bank account, `assess()` runs these checks (PASS | WARN | FAIL, bilingual detail, evidence):

  LICENSE_VS_INVOICE_NAME   licence name vs seller name on the invoice (fuzzy score)
  LICENSE_VS_ACCOUNT_HOLDER licence name vs account holder name (fuzzy score)
  ACCOUNT_TYPE              PERSONAL account for a company supplier -> FAIL
  ACCOUNT_AGE               first seen < 7 days FAIL, < 30 days WARN
  ACCOUNT_COUNTRY           bank country (or a BDT account) inconsistent with the registered country
  PENDING_BENEFICIARY_CHANGE  (pending accounts only) a change is awaiting review -> WARN
  REGISTRY_HISTORY          completed deals and disputes in our own registry
  SANCTIONS_SCREEN          supplier, invoice and holder names vs the mock sanctions list

Name match: names are normalised (case-fold, punctuation, company suffixes to canonical tokens,
small CJK map), then score = floor2((token_set_ratio + token_sort_ratio) / 2). token_set alone
scores 100 when one name is a subset of the other, so token_sort pulls "Huaxin Textile" down
against "Shaoxing Huaxin Textile Co Ltd". Bands: score >= 92 match (PASS), 80 <= score < 92
partial (WARN), score < 80 mismatch (FAIL).

Score = 100 - sum(weight x severity) over the checks, severity FAIL 1, WARN 1/2, rounded half up;
SANCTIONS_SCREEN FAIL forces score 0. Weights sum to 100 (see WEIGHTS).
Status: BLOCKED if the sanctions check fails, else WARNING if any check is WARN/FAIL, else VERIFIED.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any, Literal

from rapidfuzz import fuzz

from app.domain.narrative import bn

CheckStatus = Literal["PASS", "WARN", "FAIL"]
Overall = Literal["VERIFIED", "WARNING", "BLOCKED"]
Band = Literal["match", "partial", "mismatch"]

MATCH_THRESHOLD = 92.0
PARTIAL_THRESHOLD = 80.0
AGE_FAIL_DAYS = 7
AGE_WARN_DAYS = 30
MAX_DISPUTED_DEALS = 2

WEIGHTS: dict[str, int] = {
    "LICENSE_VS_INVOICE_NAME": 15,
    "LICENSE_VS_ACCOUNT_HOLDER": 25,
    "ACCOUNT_TYPE": 20,
    "ACCOUNT_AGE": 15,
    "ACCOUNT_COUNTRY": 10,
    "PENDING_BENEFICIARY_CHANGE": 5,
    "REGISTRY_HISTORY": 10,
    "RECEIVING_ACCOUNT": 25,
    "DOC_INSTRUCTION": 20,
}
HOLD_SCORE_CAP = 20  # sanctions hit on the invoice name only: a hold, not a block
SEVERITY: dict[str, Decimal] = {"PASS": Decimal("0"), "WARN": Decimal("0.5"), "FAIL": Decimal("1")}
CHECK_ORDER = (
    "SANCTIONS_SCREEN",
    "DOC_INSTRUCTION",
    "LICENSE_VS_ACCOUNT_HOLDER",
    "ACCOUNT_TYPE",
    "ACCOUNT_AGE",
    "LICENSE_VS_INVOICE_NAME",
    "ACCOUNT_COUNTRY",
    "RECEIVING_ACCOUNT",
    "PENDING_BENEFICIARY_CHANGE",
    "REGISTRY_HISTORY",
)

# --- name normalisation -------------------------------------------------------------------

SUFFIX_TOKENS: dict[str, str] = {
    "co": "co",
    "company": "co",
    "corp": "co",
    "corporation": "co",
    "inc": "co",
    "ltd": "ltd",
    "limited": "ltd",
    "llc": "ltd",
    "trading": "trading",
    "trade": "trading",
}
# Tiny pinyin-free fallback for the company words and demo cities that appear in Chinese names.
CJK_WORDS: tuple[tuple[str, str], ...] = (
    ("股份有限公司", " co ltd "),
    ("有限责任公司", " co ltd "),
    ("有限公司", " ltd "),
    ("公司", " co "),
    ("贸易", " trading "),
    ("纺织", " textile "),
    ("集团", " group "),
    ("香港", " hk "),
    ("绍兴", " shaoxing "),
    ("宁波", " ningbo "),
    ("广州", " guangzhou "),
)
# Cyrillic / Greek lookalikes folded to Latin so they cannot dodge the sanctions screen.
HOMOGLYPHS: dict[str, str] = {
    **dict(zip("асеіјорѕхуԁԛԝ", "aceijopsxydqw", strict=True)),  # noqa: RUF001
    **dict(zip("кмнтвгп", "kmhtbrn", strict=True)),
    **dict(zip("αβεικνορτυχωηѵ", "abeiknoptuxwhv", strict=True)),
}
_HOMOGLYPH_TABLE = str.maketrans(HOMOGLYPHS)
CODE_LABELS: dict[str, tuple[str, str]] = {
    "LICENSE_VS_INVOICE_NAME": (
        "Invoice seller name does not match the licence",
        "ইনভয়েসের বিক্রেতার নাম লাইসেন্সের সাথে মেলেনি",
    ),
    "LICENSE_VS_ACCOUNT_HOLDER": (
        "Account holder name does not match the licence",
        "অ্যাকাউন্ট হোল্ডারের নাম লাইসেন্সের সাথে মেলেনি",
    ),
    "ACCOUNT_TYPE": ("Receiving account is a personal account", "প্রাপক অ্যাকাউন্টটি ব্যক্তিগত"),
    "ACCOUNT_AGE": ("Receiving account is new", "প্রাপক অ্যাকাউন্টটি নতুন"),
    "ACCOUNT_COUNTRY": (
        "Bank country or currency is unusual for this supplier",
        "ব্যাংকের দেশ বা মুদ্রা এই সরবরাহকারীর জন্য অস্বাভাবিক",
    ),
    "PENDING_BENEFICIARY_CHANGE": ("A beneficiary change is pending", "একটি প্রাপক-পরিবর্তন অপেক্ষমাণ"),
    "REGISTRY_HISTORY": ("Disputes in the deal registry", "ডিল রেজিস্ট্রিতে বিরোধ আছে"),
    "SANCTIONS_SCREEN": (
        "A screened name matches the sanctions list",
        "একটি নাম নিষেধাজ্ঞা তালিকার সাথে মিলেছে",
    ),
    "RECEIVING_ACCOUNT": ("No active receiving account", "কোনো সক্রিয় প্রাপক অ্যাকাউন্ট নেই"),
    "DOC_INSTRUCTION": (
        "Document text looked like an instruction and was ignored",
        "ডকুমেন্টের লেখা নির্দেশের মতো ছিল, তাই উপেক্ষা করা হয়েছে",
    ),
}
_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)


def normalise_name(name: str, *, ascii_fold: bool = True) -> str:
    """Case-fold, strip punctuation, collapse whitespace, canonicalise company suffixes."""
    text = unicodedata.normalize("NFKC", name).casefold().replace("&", " and ")
    text = "".join(c for c in text if unicodedata.category(c) != "Cf").translate(_HOMOGLYPH_TABLE)
    for word, token in CJK_WORDS:
        text = text.replace(word, token)
    if ascii_fold:
        text = "".join(
            c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
        )
    tokens = _PUNCT.sub(" ", text).split()
    return " ".join(SUFFIX_TOKENS.get(t, t) for t in tokens)


def _floor2(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def band_for(score: float | Decimal, match: float, partial: float) -> Band:
    value = float(score)
    if value >= match:
        return "match"
    return "partial" if value >= partial else "mismatch"


@dataclass(frozen=True, slots=True)
class NameMatch:
    score: Decimal
    band: Band
    token_set: Decimal
    token_sort: Decimal
    partial: Decimal
    left: str
    right: str

    def evidence(self) -> dict[str, Any]:
        return {
            "score": str(self.score),
            "band": self.band,
            "token_set_ratio": str(self.token_set),
            "token_sort_ratio": str(self.token_sort),
            "partial_ratio": str(self.partial),
            "left_normalised": self.left,
            "right_normalised": self.right,
        }


def match_names(
    a: str, b: str, *, match: float = MATCH_THRESHOLD, partial: float = PARTIAL_THRESHOLD
) -> NameMatch:
    left, right = normalise_name(a), normalise_name(b)
    if not left or not right:
        zero = Decimal("0.00")
        return NameMatch(zero, "mismatch", zero, zero, zero, left, right)
    ts = fuzz.token_set_ratio(left, right)
    so = fuzz.token_sort_ratio(left, right)
    score = (ts + so) / 2
    return NameMatch(
        _floor2(score),
        band_for(score, match, partial),
        _floor2(ts),
        _floor2(so),
        _floor2(fuzz.partial_ratio(left, right)),
        left,
        right,
    )


# --- inputs ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartyFacts:
    legal_name: str
    license_name: str | None
    country: str


@dataclass(frozen=True, slots=True)
class AccountFacts:
    holder_name: str
    account_type: str  # CORPORATE | PERSONAL
    first_seen_on: date
    bank_country: str
    currency: str
    pending: bool = False
    change_requested_via: str | None = None


@dataclass(frozen=True, slots=True)
class HistoryFacts:
    total_deals: int = 0
    completed_deals: int = 0
    disputed_deals: int = 0
    previous: tuple[tuple[str, str], ...] = ()  # (checked_at iso, status), newest first


@dataclass(frozen=True, slots=True)
class SanctionEntry:
    id: str
    names: tuple[str, ...]
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Thresholds:
    match: float = MATCH_THRESHOLD
    partial: float = PARTIAL_THRESHOLD


# --- results --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Check:
    code: str
    status: CheckStatus
    detail_en: str
    detail_bn: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def weight(self) -> int:
        return WEIGHTS.get(self.code, 0)


@dataclass(frozen=True, slots=True)
class Assessment:
    status: Overall
    score: int
    checks: tuple[Check, ...]
    reason_codes: tuple[str, ...]
    explanation_en: str
    explanation_bn: str


# --- checks ---------------------------------------------------------------------------------


def _name_check(
    code: str, label_en: str, label_bn: str, left: str, right: str, th: Thresholds
) -> Check:
    m = match_names(left, right, match=th.match, partial=th.partial)
    status: CheckStatus = {"match": "PASS", "partial": "WARN", "mismatch": "FAIL"}[m.band]
    ev = {
        **m.evidence(),
        "left": left,
        "right": right,
        "match_at": th.match,
        "partial_at": th.partial,
    }
    if status == "PASS":
        en = f"{label_en} matches (score {m.score}): '{left}' and '{right}'."
        bn_ = f"{label_bn} মিলেছে (স্কোর {m.score}): '{left}' ও '{right}'।"
    elif status == "WARN":
        en = f"{label_en} only partly matches (score {m.score}): '{left}' vs '{right}'."
        bn_ = f"{label_bn} আংশিক মিলেছে (স্কোর {m.score}): '{left}' বনাম '{right}'।"
    else:
        en = f"{label_en} does not match (score {m.score}): '{left}' vs '{right}'."
        bn_ = f"{label_bn} মেলেনি (স্কোর {m.score}): '{left}' বনাম '{right}'।"
    return Check(code, status, en, bn(bn_), ev)


def _type_check(account: AccountFacts) -> Check:
    personal = account.account_type == "PERSONAL"
    return Check(
        "ACCOUNT_TYPE",
        "FAIL" if personal else "PASS",
        "The receiving account is a PERSONAL account, not a company account."
        if personal
        else "The receiving account is a corporate account.",
        "প্রাপক অ্যাকাউন্টটি কোম্পানির নয়, ব্যক্তিগত (PERSONAL) অ্যাকাউন্ট।"
        if personal
        else "প্রাপক অ্যাকাউন্টটি কর্পোরেট অ্যাকাউন্ট।",
        {"account_type": account.account_type},
    )


def _age_check(account: AccountFacts, today: date) -> Check:
    days = (today - account.first_seen_on).days
    status: CheckStatus = (
        "FAIL" if days < AGE_FAIL_DAYS else "WARN" if days < AGE_WARN_DAYS else "PASS"
    )
    en = {
        "FAIL": f"The account was first seen {days} days ago (less than {AGE_FAIL_DAYS} days).",
        "WARN": f"The account was first seen {days} days ago (less than {AGE_WARN_DAYS} days).",
        "PASS": f"The account has been known for {days} days.",
    }[status]
    bn_ = {
        "FAIL": f"অ্যাকাউন্টটি মাত্র {days} দিন আগে প্রথম দেখা গেছে ({AGE_FAIL_DAYS} দিনের কম)।",
        "WARN": f"অ্যাকাউন্টটি {days} দিন আগে প্রথম দেখা গেছে ({AGE_WARN_DAYS} দিনের কম)।",
        "PASS": f"অ্যাকাউন্টটি {days} দিন ধরে পরিচিত।",
    }[status]
    return Check(
        "ACCOUNT_AGE",
        status,
        en,
        bn(bn_),
        {
            "age_days": days,
            "first_seen_on": account.first_seen_on.isoformat(),
            "warn_below_days": AGE_WARN_DAYS,
            "fail_below_days": AGE_FAIL_DAYS,
        },
    )


def _country_check(party: PartyFacts, account: AccountFacts) -> Check:
    off_country = account.bank_country != party.country
    bdt = account.currency == "BDT"
    bad = off_country or bdt
    if off_country:
        en = (
            f"The bank is in {account.bank_country} ({account.currency}) but the supplier is "
            f"registered in {party.country}."
        )
        bn_ = (
            f"ব্যাংকটি {account.bank_country}-এ ({account.currency}), কিন্তু সরবরাহকারী "
            f"{party.country}-এ নিবন্ধিত।"
        )
    elif bdt:
        en = (
            f"A {account.currency} account is unusual for a supplier registered in {party.country}."
        )
        bn_ = f"{party.country}-এ নিবন্ধিত সরবরাহকারীর জন্য {account.currency} অ্যাকাউন্ট অস্বাভাবিক।"
    else:
        en = f"The bank country ({account.bank_country}) matches the registered country."
        bn_ = f"ব্যাংকের দেশ ({account.bank_country}) নিবন্ধিত দেশের সাথে মেলে।"
    return Check(
        "ACCOUNT_COUNTRY",
        "WARN" if bad else "PASS",
        en,
        bn_,
        {
            "bank_country": account.bank_country,
            "currency": account.currency,
            "registered_country": party.country,
        },
    )


def _pending_check(account: AccountFacts) -> Check:
    via = account.change_requested_via
    return Check(
        "PENDING_BENEFICIARY_CHANGE",
        "WARN",
        "This account is a pending beneficiary change"
        + (f" requested via {via}" if via else "")
        + "; it is not trusted until a human approves it.",
        "এটি একটি অপেক্ষমাণ প্রাপক-পরিবর্তন"
        + (f" ({via} মাধ্যমে অনুরোধ)" if via else "")
        + "; মানুষের অনুমোদন ছাড়া এটি বিশ্বাসযোগ্য নয়।",
        {"change_requested_via": via},
    )


def _history_check(history: HistoryFacts) -> Check:
    bad = history.disputed_deals >= MAX_DISPUTED_DEALS or (
        history.total_deals > 0 and history.disputed_deals * 2 > history.total_deals
    )
    ev = {
        "total_deals": history.total_deals,
        "completed_deals": history.completed_deals,
        "disputed_deals": history.disputed_deals,
        "previous_checks": [{"checked_at": at, "status": st} for at, st in history.previous[:3]],
    }
    if bad:
        en = (
            f"{history.disputed_deals} of {history.total_deals} deals in our registry were "
            "disputed."
        )
        bn_ = (
            f"আমাদের রেজিস্ট্রির {history.total_deals}টি ডিলের মধ্যে "
            f"{history.disputed_deals}টি বিতর্কিত।"
        )
    else:
        en = (
            f"{history.completed_deals} completed and {history.disputed_deals} disputed deals "
            f"out of {history.total_deals} in our registry."
        )
        bn_ = (
            f"আমাদের রেজিস্ট্রিতে {history.total_deals}টি ডিলের মধ্যে {history.completed_deals}টি "
            f"সম্পন্ন, {history.disputed_deals}টি বিতর্কিত।"
        )
    return Check("REGISTRY_HISTORY", "WARN" if bad else "PASS", en, bn(bn_), ev)


Screened = str | tuple[str, str]


def screen_sanctions(
    names: Sequence[Screened], entries: Sequence[SanctionEntry], th: Thresholds
) -> list[dict[str, Any]]:
    """Hits: a screened name (plain, or (role, name)) whose match score against any listed name
    reaches the match band. Each hit records the role of the name that matched."""
    hits: list[dict[str, Any]] = []
    for item in names:
        role, name = item if isinstance(item, tuple) else ("name", item)
        for entry in entries:
            for listed in entry.names:
                m = match_names(name, listed, match=th.match, partial=th.partial)
                if m.band == "match":
                    hits.append(
                        {
                            "entry_id": entry.id,
                            "role": role,
                            "name": name,
                            "listed_as": listed,
                            "score": str(m.score),
                            "reason": entry.reason,
                        }
                    )
                    break
    return hits


def _sanctions_check(
    names: Sequence[tuple[str, str]], entries: Sequence[SanctionEntry], th: Thresholds
) -> Check:
    hits = screen_sanctions(names, entries, th)
    screened = [n for _, n in names]
    if hits:
        blocking = any(h["role"] != "invoice_name" for h in hits)
        shown = ", ".join(f"'{h['name']}'" for h in hits)
        ev = {"hits": hits, "screened": screened, "list": "MOCK", "blocking": blocking}
        if blocking:
            return Check(
                "SANCTIONS_SCREEN",
                "FAIL",
                f"{shown} matches an entry on the sanctions list (mock list).",
                f"{shown} নিষেধাজ্ঞা তালিকার (মক তালিকা) একটি এন্ট্রির সাথে মিলেছে।",
                ev,
            )
        return Check(
            "SANCTIONS_SCREEN",
            "FAIL",
            f"The invoice seller name {shown} matches the sanctions list (mock list); this deal "
            "is on hold, the supplier and its accounts are not blocked.",
            f"ইনভয়েসের বিক্রেতার নাম {shown} নিষেধাজ্ঞা তালিকার (মক তালিকা) সাথে মিলেছে; এই ডিল স্থগিত, "
            "সরবরাহকারী ও তার অ্যাকাউন্ট অবরুদ্ধ নয়।",
            ev,
        )
    return Check(
        "SANCTIONS_SCREEN",
        "PASS",
        "No screened name matches the sanctions list (mock list).",
        "কোনো যাচাইকৃত নাম নিষেধাজ্ঞা তালিকার (মক তালিকা) সাথে মেলেনি।",
        {"hits": [], "screened": screened, "list": "MOCK", "blocking": False},
    )


# --- aggregation ----------------------------------------------------------------------------


def _sanctions_fail(checks: Sequence[Check]) -> Check | None:
    return next((c for c in checks if c.code == "SANCTIONS_SCREEN" and c.status == "FAIL"), None)


def is_blocking(checks: Sequence[Check]) -> bool:
    """Sanctions hit on the supplier, licence or holder name. Invoice-name-only is a hold."""
    hit = _sanctions_fail(checks)
    return hit is not None and bool(hit.evidence.get("blocking", True))


def score_of(checks: Sequence[Check]) -> int:
    if is_blocking(checks):
        return 0
    penalty = sum((Decimal(c.weight) * SEVERITY[c.status] for c in checks), Decimal(0))
    score = int(max(Decimal(0), Decimal(100) - penalty).quantize(Decimal("1"), ROUND_HALF_UP))
    return min(score, HOLD_SCORE_CAP) if _sanctions_fail(checks) else score


def overall_status(checks: Sequence[Check]) -> Overall:
    if is_blocking(checks):
        return "BLOCKED"
    return "WARNING" if any(c.status != "PASS" for c in checks) else "VERIFIED"


def _rank(c: Check) -> tuple[int, int]:
    order = CHECK_ORDER.index(c.code) if c.code in CHECK_ORDER else len(CHECK_ORDER)
    return (0 if c.status == "FAIL" else 1, order)


def explain(status: Overall, score: int, checks: Sequence[Check]) -> tuple[str, str]:
    flagged = sorted((c for c in checks if c.status != "PASS"), key=_rank)
    if status == "VERIFIED":
        n = len(checks)
        return (
            f"Verified: all {n} checks passed (score {score}/100).",
            bn(f"যাচাইকৃত: সব {n}টি পরীক্ষা সফল (স্কোর {score}/১০০)।"),
        )
    en_parts = " ".join(c.detail_en for c in flagged[:3])
    bn_parts = " ".join(c.detail_bn for c in flagged[:3])
    if status == "BLOCKED":
        return (
            f"Blocked (score {score}/100): {en_parts} No payment should be sent to this supplier.",
            bn(f"অবরুদ্ধ (স্কোর {score}/১০০): ") + bn_parts + " অর্থ পাঠানো থেকে বিরত থাকুন।",
        )
    return (
        f"Warning (score {score}/100): {en_parts} Review before any payment.",
        bn(f"সতর্কতা (স্কোর {score}/১০০): ") + bn_parts + " কোনো অর্থ প্রদানের আগে পর্যালোচনা করুন।",
    )


def aggregate(checks: Sequence[Check]) -> Assessment:
    ordered = tuple(sorted(checks, key=lambda c: CHECK_ORDER.index(c.code)))
    status, score = overall_status(ordered), score_of(ordered)
    reasons = tuple(c.code for c in sorted((c for c in ordered if c.status != "PASS"), key=_rank))
    en, bn_ = explain(status, score, ordered)
    return Assessment(status, score, ordered, reasons, en, bn_)


def _doc_instruction_check(codes: Sequence[str]) -> Check:
    return Check(
        "DOC_INSTRUCTION",
        "FAIL",
        "The seller name on the invoice contained instruction-like text. It was ignored and the "
        "registered legal name was used instead.",
        "ইনভয়েসের বিক্রেতার নামে নির্দেশের মতো লেখা ছিল। তা উপেক্ষা করে নিবন্ধিত আইনি নাম ব্যবহার করা হয়েছে।",
        {"finding_codes": sorted(codes)},
    )


def assess(
    *,
    party: PartyFacts,
    invoice_name: str | None,
    account: AccountFacts | None,
    history: HistoryFacts,
    sanctions: Sequence[SanctionEntry],
    today: date,
    thresholds: Thresholds | None = None,
    invoice_flags: Sequence[str] = (),
) -> Assessment:
    """`invoice_name=None` assesses only party and account facts (no invoice check, no invoice
    screening): that is what Party.kyb_status and BankAccount.verified are based on."""
    th = thresholds or Thresholds()
    licence = party.license_name or party.legal_name
    screened = [("legal_name", party.legal_name), ("licence_name", licence)]
    checks = [_history_check(history)]
    if invoice_name is not None:
        screened.append(("invoice_name", invoice_name))
        checks.append(
            _name_check(
                "LICENSE_VS_INVOICE_NAME",
                "The invoice seller name",
                "ইনভয়েসের বিক্রেতার নাম",
                licence,
                invoice_name,
                th,
            )
        )
        if invoice_flags:
            checks.append(_doc_instruction_check(invoice_flags))
    if account is None:
        checks.append(
            Check(
                "RECEIVING_ACCOUNT",
                "WARN",
                "No active receiving account is on file for this supplier.",
                "এই সরবরাহকারীর কোনো সক্রিয় প্রাপক অ্যাকাউন্ট নেই।",
                {},
            )
        )
    else:
        screened.append(("account_holder", account.holder_name))
        checks += [
            _name_check(
                "LICENSE_VS_ACCOUNT_HOLDER",
                "The account holder name",
                "অ্যাকাউন্ট হোল্ডারের নাম",
                licence,
                account.holder_name,
                th,
            ),
            _type_check(account),
            _age_check(account, today),
            _country_check(party, account),
        ]
        if account.pending:
            checks.append(_pending_check(account))
    checks.append(_sanctions_check(screened, sanctions, th))
    return aggregate(checks)
