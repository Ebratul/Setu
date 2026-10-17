"""Weighted fraud score (0-100) from check outcomes, and the document verdict.

score = min(100, round(sum(weight x factor))) with factor FAIL = 1, WARN = 0.5, PASS/SKIPPED = 0.
< 30 PASSED, 30..60 WARNING, > 60 FAILED. Any non-pass finding (other than file-metadata notes)
keeps the verdict at WARNING at least; hidden text, instruction-like text, a beneficiary mismatch
and a duplicate hash force FAILED whatever the score. Explanations are fixed templates built from
check codes (never from document text).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.domain.narrative import bn
from app.forensics.checks import Outcome
from app.forensics.names import LABELS

Verdict = Literal["PASSED", "WARNING", "FAILED"]
WARN_AT = 30
FAIL_ABOVE = 60
ORDINARY = 35  # one ordinary FAIL alone is a WARNING; two are FAILED
WEIGHTS: dict[str, int] = {
    "QUANTITY_MATCH": ORDINARY,
    "VALUE_MATH": ORDINARY,
    "VALUE_MATCH": ORDINARY,
    "NAME_MATCH": ORDINARY,
    "VESSEL_VOYAGE_MATCH": ORDINARY,
    "DATE_LOGIC": ORDINARY,
    "PORT_MATCH": ORDINARY,
    "HS_CODE_MATCH": ORDINARY,
    "PRICE_BAND": ORDINARY,
    "PHOTO_MATCH": ORDINARY,
    "EXTRACTION_COMPLETE": 30,
    "REFERENCE_CHANGED": ORDINARY,
    "METADATA_ANOMALY": 10,
    "BENEFICIARY_MATCH": 70,
    "HIDDEN_TEXT": 70,
    "INSTRUCTION_SCAN": 70,
    "DUPLICATE_HASH": 70,
}
FACTOR = {"FAIL": Decimal(1), "WARN": Decimal("0.5")}
FORCES_FAILED = frozenset(
    {"HIDDEN_TEXT", "INSTRUCTION_SCAN", "BENEFICIARY_MATCH", "DUPLICATE_HASH"}
)
NO_STATUS_FLOOR = frozenset({"METADATA_ANOMALY"})  # informational: weight only


@dataclass(frozen=True, slots=True)
class Score:
    status: Verdict
    score: int
    reason_codes: tuple[str, ...]
    forced_by: tuple[str, ...]
    explanation_en: str
    explanation_bn: str


def status_for(score: int, warn_at: int = WARN_AT, fail_above: int = FAIL_ABOVE) -> Verdict:
    if score > fail_above:
        return "FAILED"
    return "WARNING" if score >= warn_at else "PASSED"


def raw_score(outcomes: Sequence[Outcome]) -> int:
    total = sum(
        (Decimal(WEIGHTS.get(o.code, ORDINARY)) * FACTOR[o.status] for o in outcomes
         if o.status in FACTOR),
        Decimal(0),
    )  # fmt: skip
    return int(min(Decimal(100), total).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def explain(
    status: Verdict, score: int, reasons: Sequence[str], forced: Sequence[str]
) -> tuple[str, str]:
    top = list(reasons)[:3]
    en_labels = "; ".join(LABELS[c][0] for c in top)
    bn_labels = "; ".join(LABELS[c][1] for c in top)
    word = {"PASSED": "Passed", "WARNING": "Needs review", "FAILED": "Failed"}[status]
    word_bn = {"PASSED": "সফল", "WARNING": "পর্যালোচনা দরকার", "FAILED": "ব্যর্থ"}[status]
    if status == "PASSED":
        return (
            f"{word}: all checks passed (score {score}/100).",
            bn(f"{word_bn}: সব পরীক্ষা সফল (স্কোর {score}/১০০)।"),
        )
    tail_en = (
        " Hold any payment until a person has reviewed this document."
        if status == "FAILED"
        else " Review it before any payment is made."
    )
    tail_bn = (
        " এই ডকুমেন্টের ভিত্তিতে অর্থ ছাড় করবেন না।"
        if status == "FAILED"
        else " অর্থ ছাড়ের আগে এটি পর্যালোচনা করুন।"
    )
    return (
        f"{word} (score {score}/100): {en_labels}.{tail_en}",
        bn(f"{word_bn} (স্কোর {score}/১০০): ") + bn_labels + "।" + tail_bn,
    )


def score_document(
    outcomes: Sequence[Outcome], *, warn_at: int = WARN_AT, fail_above: int = FAIL_ABOVE
) -> Score:
    raw = raw_score(outcomes)
    flagged = [o for o in outcomes if o.status in FACTOR]
    forced = tuple(o.code for o in outcomes if o.status == "FAIL" and o.code in FORCES_FAILED)
    status = status_for(raw, warn_at, fail_above)
    score = raw
    if forced:
        status, score = "FAILED", max(raw, fail_above + 1)
    elif status == "PASSED" and any(o.code not in NO_STATUS_FLOOR for o in flagged):
        status, score = "WARNING", max(raw, warn_at)
    order = {"FAIL": 0, "WARN": 1}
    reasons = tuple(
        o.code
        for o in sorted(flagged, key=lambda o: (order[o.status], -WEIGHTS.get(o.code, ORDINARY)))
    )
    en, bn_ = explain(status, score, reasons, forced)
    return Score(status, score, reasons, forced, en, bn_)
