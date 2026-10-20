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
}
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
