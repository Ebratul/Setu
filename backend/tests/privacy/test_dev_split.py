"""Masking ON vs OFF on the dev split of the synthetic packs (skipped when data is absent).
Only the dev split is scored; the test split is reserved for P24."""

import pytest

from app.forensics.pack_loader import GENERATED
from app.privacy import eval as peval

pytestmark = pytest.mark.skipif(
    not (GENERATED / "manifest.jsonl").is_file(), reason="data/generated not built"
)


@pytest.fixture(scope="module")
def result() -> dict:
    out = peval.run_documents("dev", limit=30)
    print("\nmasked by type (dev, 30 packs):", out["on"]["masked_by_type"])
    return out


def test_no_detectable_identifier_reaches_the_model(result: dict) -> None:
    assert result["on"]["detected_leaked"] == 0
    assert result["off"]["detected_leaked"] > 100


def test_ground_truth_bank_identifiers_are_masked(result: dict) -> None:
    on = result["on"]
    assert on["ground_truth_identifiers"] > 100
    assert on["ground_truth_leaked"] / on["ground_truth_identifiers"] <= 0.01
    assert result["off"]["ground_truth_leaked"] == result["off"]["ground_truth_identifiers"]
    assert {"ACCT", "SWIFT", "NAME", "AMT"} <= set(on["masked_by_type"])


def test_extracted_fields_still_round_trip(result: dict) -> None:
    assert result["on"]["fields_checked"] > 100
    assert result["on"]["field_accuracy"] == 1.0
