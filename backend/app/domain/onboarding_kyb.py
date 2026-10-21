"""Self-service onboarding KYB: pure, deterministic checks (no I/O, no LLM).

`assess()` runs these checks (PASS | WARN | FAIL) on what the applicant submitted:

  SANCTIONS_SCREEN   legal name, licence name and bank holder name vs the sanctions list
                     (same engine as supplier KYB); any hit FAILs, forces score 0 and BLOCKs
  HOLDER_NAME_MATCH  CORPORATE account: holder name vs legal name (kyb name-match bands)
  ACCOUNT_TYPE       a PERSONAL account for a company -> WARN (an admin decides)
  LICENSE_NAME_MATCH legal name vs the name on the licence, only when a licence name was given
  COUNTRY_ALLOWED    registration country must be on the allow-list, else FAIL
  BANK_COUNTRY       bank country on the allow-list, else WARN
  TAX_ID_FORMAT      BD: 9-13 digits (TIN/BIN) else FAIL; elsewhere 5-32 letters/digits else WARN

Score = 100 - sum(weight x severity), severity FAIL 1, WARN 1/2, rounded half up, clamped to
0..100; a sanctions hit forces 0. Recommendation: BLOCK on a sanctions hit, AUTO_CLEAR when every
check passes, otherwise NEEDS_REVIEW. Name matching and bands are `app.domain.kyb.match_names`.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.domain.kyb import SanctionEntry, Thresholds, match_names, screen_sanctions

Status = Literal["PASS", "WARN", "FAIL"]
Recommendation = Literal["AUTO_CLEAR", "NEEDS_REVIEW", "BLOCK"]

WEIGHTS: dict[str, int] = {
    "HOLDER_NAME_MATCH": 30,
    "ACCOUNT_TYPE": 20,
    "LICENSE_NAME_MATCH": 25,
    "COUNTRY_ALLOWED": 30,
    "BANK_COUNTRY": 10,
    "TAX_ID_FORMAT": 15,
    "DUPLICATE_COMPANY": 40,
    "DOC_PRESENT": 25,
    "DOC_HASH_REUSE": 40,
    "PHONE_VERIFIED": 15,
    "LICENSE_EXPIRY": 30,
    "KYB_HOLDER_NAME": 30,
    "KYB_ACCOUNT_TYPE": 20,
    "KYB_COUNTRY": 15,
}
COMPANY_MARKERS = re.compile(
    r"\b(?:co|company|corp|corporation|inc|ltd|limited|llc|trading|industr(?:y|ies)|group|"
    r"enterprise[s]?|factory|manufactur\w*)\b|有限公司|有限责任公司|公司|集团|工厂|厂",
    re.I,
)
SEVERITY: dict[str, Decimal] = {"PASS": Decimal("0"), "WARN": Decimal("0.5"), "FAIL": Decimal("1")}
BD_TAX_ID = re.compile(r"^\d{9,13}$")
OTHER_TAX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{3,30}[A-Za-z0-9]$")


@dataclass(frozen=True, slots=True)
class OnboardingFacts:
    legal_name: str
    license_name: str | None
    tax_id: str
    country: str
    holder_name: str
    account_type: str  # CORPORATE | PERSONAL
    bank_country: str


@dataclass(frozen=True, slots=True)
class OnboardingCheck:
    code: str
    status: Status
    detail: str


@dataclass(frozen=True, slots=True)
class OnboardingAssessment:
    checks: tuple[OnboardingCheck, ...]
    score: int
    recommendation: Recommendation


def _name_status(left: str, right: str, th: Thresholds) -> tuple[Status, str]:
    m = match_names(left, right, match=th.match, partial=th.partial)
    status: Status = {"match": "PASS", "partial": "WARN", "mismatch": "FAIL"}[m.band]
    return status, f"name match score {m.score} ({m.band})"


def _sanctions(
    facts: OnboardingFacts, entries: Sequence[SanctionEntry], th: Thresholds
) -> OnboardingCheck:
    names: list[tuple[str, str]] = [
        ("legal_name", facts.legal_name),
        ("holder_name", facts.holder_name),
    ]
    if facts.license_name:
        names.append(("license_name", facts.license_name))
    hits = screen_sanctions(names, entries, th)
    if hits:
        roles = sorted({h["role"] for h in hits})
        ids = sorted({h["entry_id"] for h in hits})
        return OnboardingCheck(
            "SANCTIONS_SCREEN",
            "FAIL",
            f"match on the sanctions list (mock list): entries {', '.join(ids)}; "
            f"fields {', '.join(roles)}",
        )
    return OnboardingCheck(
        "SANCTIONS_SCREEN", "PASS", "no screened name matches the sanctions list"
    )


def _tax_id(facts: OnboardingFacts) -> OnboardingCheck:
    tin = facts.tax_id.strip()
    if facts.country == "BD":
        ok = bool(BD_TAX_ID.match(tin))
        return OnboardingCheck(
            "TAX_ID_FORMAT",
            "PASS" if ok else "FAIL",
            "BD TIN/BIN has 9-13 digits" if ok else "BD TIN/BIN must be 9-13 digits",
        )
    ok = bool(OTHER_TAX_ID.match(tin))
    return OnboardingCheck(
        "TAX_ID_FORMAT",
        "PASS" if ok else "WARN",
        "tax id format looks valid" if ok else "tax id format could not be validated",
    )


def assess(
    facts: OnboardingFacts,
    sanctions: Sequence[SanctionEntry],
    allowed_countries: Sequence[str],
    thresholds: Thresholds | None = None,
) -> OnboardingAssessment:
    th = thresholds or Thresholds()
    allowed = {c.upper() for c in allowed_countries}
    checks: list[OnboardingCheck] = [_sanctions(facts, sanctions, th)]
    if facts.account_type == "CORPORATE":
        status, detail = _name_status(facts.legal_name, facts.holder_name, th)
        checks.append(OnboardingCheck("HOLDER_NAME_MATCH", status, f"holder vs legal: {detail}"))
    else:
        checks.append(
            OnboardingCheck(
                "ACCOUNT_TYPE", "WARN", "a personal bank account was given for a company"
            )
        )
    if facts.license_name:
        status, detail = _name_status(facts.legal_name, facts.license_name, th)
        checks.append(OnboardingCheck("LICENSE_NAME_MATCH", status, f"licence vs legal: {detail}"))
    in_list = facts.country.upper() in allowed
    checks.append(
        OnboardingCheck(
            "COUNTRY_ALLOWED",
            "PASS" if in_list else "FAIL",
            "registration country is supported"
            if in_list
            else "registration country not supported",
        )
    )
    bank_ok = facts.bank_country.upper() in allowed
    checks.append(
        OnboardingCheck(
            "BANK_COUNTRY",
            "PASS" if bank_ok else "WARN",
            "bank country is supported"
            if bank_ok
            else "bank country is outside the supported list",
        )
    )
    checks.append(_tax_id(facts))
    return OnboardingAssessment(tuple(checks), score_of(checks), recommend(checks))


def blocked(checks: Sequence[OnboardingCheck]) -> bool:
    return any(c.code == "SANCTIONS_SCREEN" and c.status == "FAIL" for c in checks)


def score_of(checks: Sequence[OnboardingCheck]) -> int:
    if blocked(checks):
        return 0
    penalty = sum(
        (Decimal(WEIGHTS.get(c.code, 0)) * SEVERITY[c.status] for c in checks), Decimal(0)
    )
    value = (Decimal(100) - penalty).quantize(Decimal("1"), ROUND_HALF_UP)
    return int(min(Decimal(100), max(Decimal(0), value)))


def recommend(checks: Sequence[OnboardingCheck]) -> Recommendation:
    if blocked(checks):
        return "BLOCK"
    return "AUTO_CLEAR" if all(c.status == "PASS" for c in checks) else "NEEDS_REVIEW"


REQUIRED_DOCS: dict[str, frozenset[str]] = {
    "BUYER": frozenset({"TRADE_LICENSE", "IRC"}),
    "SUPPLIER": frozenset({"BUSINESS_LICENSE", "BANK_PROOF"}),
}


@dataclass(frozen=True, slots=True)
class ProfileFacts:
    """What the multi-step onboarding collected, reduced to what the checks need."""

    role: str  # BUYER | SUPPLIER
    legal_name: str
    contact_name: str
    today: date
    duplicate_of_other_company: bool
    phone_verified: bool
    doc_types: frozenset[str]
    reused_hash: bool
    license_expiry: date | None = None  # buyer
    holder_name: str | None = None  # supplier bank
    swift_country: str | None = None  # ISO-2 from the SWIFT/BIC (supplier)


def _profile_sanctions(
    facts: ProfileFacts, entries: Sequence[SanctionEntry], th: Thresholds
) -> OnboardingCheck:
    names = [("legal_name", facts.legal_name), ("contact_name", facts.contact_name)]
    if facts.holder_name:
        names.append(("holder_name", facts.holder_name))
    hits = screen_sanctions(names, entries, th)
    if hits:
        roles = sorted({h["role"] for h in hits})
        ids = sorted({h["entry_id"] for h in hits})
        return OnboardingCheck(
            "SANCTIONS_SCREEN",
            "FAIL",
            f"match on the sanctions list (mock list): entries {', '.join(ids)}; "
            f"fields {', '.join(roles)}",
        )
    return OnboardingCheck(
        "SANCTIONS_SCREEN", "PASS", "no screened name matches the sanctions list"
    )


def assess_profile(
    facts: ProfileFacts,
    sanctions: Sequence[SanctionEntry],
    allowed_countries: Sequence[str],
    thresholds: Thresholds | None = None,
) -> OnboardingAssessment:
    """Automated checks for a submitted onboarding profile (docs/p30-design.md section 5)."""
    th = thresholds or Thresholds()
    checks: list[OnboardingCheck] = [_profile_sanctions(facts, sanctions, th)]
    checks.append(
        OnboardingCheck(
            "DUPLICATE_COMPANY",
            "FAIL" if facts.duplicate_of_other_company else "PASS",
            "an approved business already uses this licence or registration number; "
            "needs manual review"
            if facts.duplicate_of_other_company
            else "no other business uses this licence or registration number",
        )
    )
    missing = sorted(REQUIRED_DOCS[facts.role] - facts.doc_types)
    checks.append(
        OnboardingCheck(
            "DOC_PRESENT",
            "FAIL" if missing else "PASS",
            f"missing documents: {', '.join(missing)}"
            if missing
            else "required documents uploaded",
        )
    )
    checks.append(
        OnboardingCheck(
            "DOC_HASH_REUSE",
            "FAIL" if facts.reused_hash else "PASS",
            "a document is byte-identical to one uploaded by another account"
            if facts.reused_hash
            else "no document was uploaded by another account",
        )
    )
    checks.append(
        OnboardingCheck(
            "PHONE_VERIFIED",
            "PASS" if facts.phone_verified else "FAIL",
            "mobile number confirmed by code" if facts.phone_verified else "mobile not verified",
        )
    )
    if facts.role == "BUYER" and facts.license_expiry is not None:
        left = (facts.license_expiry - facts.today).days
        if left < 0:
            checks.append(OnboardingCheck("LICENSE_EXPIRY", "FAIL", "trade licence has expired"))
        elif left <= 30:
            checks.append(
                OnboardingCheck("LICENSE_EXPIRY", "WARN", f"trade licence expires in {left} days")
            )
        else:
            checks.append(OnboardingCheck("LICENSE_EXPIRY", "PASS", "trade licence is current"))
    if facts.role == "SUPPLIER" and facts.holder_name:
        status, detail = _name_status(facts.legal_name, facts.holder_name, th)
        # a differing holder is a reviewer's call at onboarding (the Tier 3 name-mismatch rule
        # applies later, per payment), so it warns instead of failing
        checks.append(
            OnboardingCheck(
                "KYB_HOLDER_NAME",
                "PASS" if status == "PASS" else "WARN",
                f"holder vs legal: {detail}",
            )
        )
        corporate = bool(COMPANY_MARKERS.search(facts.holder_name))
        checks.append(
            OnboardingCheck(
                "KYB_ACCOUNT_TYPE",
                "PASS" if corporate else "WARN",
                "bank account holder looks like a company"
                if corporate
                else "bank account holder does not look like a company (personal account?)",
            )
        )
        allowed = {c.upper() for c in allowed_countries}
        country = (facts.swift_country or "").upper()
        in_list = country in allowed or country == "HK"
        checks.append(
            OnboardingCheck(
                "KYB_COUNTRY",
                "PASS" if in_list else "WARN",
                "bank country is supported"
                if in_list
                else "bank country is outside the supported list",
            )
        )
    return OnboardingAssessment(tuple(checks), score_of(checks), recommend(checks))


def risk_summary(checks: Sequence[OnboardingCheck]) -> Status:
    """Worst status across the checks: FAIL > WARN > PASS."""
    if any(c.status == "FAIL" for c in checks):
        return "FAIL"
    return "WARN" if any(c.status == "WARN" for c in checks) else "PASS"
