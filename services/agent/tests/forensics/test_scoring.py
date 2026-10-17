"""Score thresholds, forced verdicts and the generated text."""

import pytest

from app.forensics.checks import Outcome
from app.forensics.names import CHECK_CODES, GROUND_TRUTH, GROUND_TRUTH_NAMES, LABELS
from app.forensics.scoring import (
    FAIL_ABOVE,
    FORCES_FAILED,
    WARN_AT,
    WEIGHTS,
    raw_score,
    score_document,
    status_for,
)
from app.security.injection import detect_instructions


def o(code: str, status: str) -> Outcome:
    return Outcome(code, status)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "PASSED"),
        (29, "PASSED"),
        (30, "WARNING"),
        (60, "WARNING"),
        (61, "FAILED"),
        (100, "FAILED"),
    ],
)
def test_thresholds(score: int, expected: str) -> None:
    assert status_for(score) == expected
    assert (WARN_AT, FAIL_ABOVE) == (30, 60)


def test_all_pass_is_zero_and_passed() -> None:
    r = score_document([o(c, "PASS") for c in CHECK_CODES] + [o("PHOTO_MATCH", "SKIPPED")])
    assert (r.status, r.score, r.reason_codes) == ("PASSED", 0, ())
    assert r.explanation_en.startswith("Passed")


def test_one_ordinary_fail_is_a_warning_two_are_failed() -> None:
    one = score_document([o("QUANTITY_MATCH", "FAIL"), o("NAME_MATCH", "PASS")])
    assert (one.status, one.score) == ("WARNING", 35)
    two = score_document([o("QUANTITY_MATCH", "FAIL"), o("PORT_MATCH", "FAIL")])
    assert (two.status, two.score) == ("FAILED", 70)
    assert two.reason_codes == ("QUANTITY_MATCH", "PORT_MATCH")


def test_a_single_warn_is_at_least_a_warning_but_metadata_notes_are_not() -> None:
    w = score_document([o("NAME_MATCH", "WARN")])
    assert (w.status, w.score) == ("WARNING", 30)  # floor: never PASSED with a finding to review
    m = score_document([o("METADATA_ANOMALY", "WARN")])
    assert (m.status, m.score) == ("PASSED", 5)


def test_score_is_capped_at_100() -> None:
    r = score_document([o(c, "FAIL") for c in WEIGHTS])
    assert r.score == 100 and raw_score([o(c, "FAIL") for c in WEIGHTS]) == 100


@pytest.mark.parametrize("code", sorted(FORCES_FAILED))
def test_forced_failed_rules(code: str) -> None:
    r = score_document([o(code, "FAIL")])
    assert r.status == "FAILED" and r.score > FAIL_ABOVE and r.forced_by == (code,)
    assert r.explanation_en.startswith("Failed") and "Hold any payment" in r.explanation_en
    assert code in r.reason_codes
    warn_only = score_document([o(code, "WARN")])
    assert warn_only.status != "FAILED" and warn_only.forced_by == ()


def test_forced_fail_beats_a_low_raw_score() -> None:
    # beneficiary mismatch alone is already forced; a lone FAIL of a small weight is not
    assert raw_score([o("DUPLICATE_HASH", "FAIL")]) == 70
    assert score_document([o("PHOTO_MATCH", "FAIL")]).status == "WARNING"


def test_reason_codes_are_worst_first() -> None:
    r = score_document([o("NAME_MATCH", "WARN"), o("PORT_MATCH", "FAIL"), o("HIDDEN_TEXT", "FAIL")])
    assert r.reason_codes[0] == "HIDDEN_TEXT" and r.reason_codes[-1] == "NAME_MATCH"


def test_every_code_has_a_weight_label_and_mapping() -> None:
    assert set(CHECK_CODES) == set(WEIGHTS) == set(LABELS) == set(GROUND_TRUTH)
    mapped = {v for v in GROUND_TRUTH.values() if v}
    assert mapped == set(GROUND_TRUTH_NAMES) and len(GROUND_TRUTH_NAMES) == 11


def test_generated_text_does_not_trip_the_injection_detector() -> None:
    texts = [t for pair in LABELS.values() for t in pair]
    for combo in (
        [o(c, "FAIL") for c in CHECK_CODES],
        [o(c, "WARN") for c in CHECK_CODES],
        [o(c, "PASS") for c in CHECK_CODES],
    ):
        r = score_document(combo)
        texts += [r.explanation_en, r.explanation_bn]
    for single in CHECK_CODES:
        r = score_document([o(single, "FAIL")])
        texts += [r.explanation_en, r.explanation_bn]
    flagged = {t: [f.code for f in detect_instructions(t)] for t in texts}
    assert {t: c for t, c in flagged.items() if c} == {}
