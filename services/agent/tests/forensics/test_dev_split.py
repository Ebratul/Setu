"""Dev-split evaluation against the generated packs (skipped when data/generated is absent).
Only the dev split is ever scored here; the test split is reserved for the final report."""

from pathlib import Path

import pytest

from app.forensics import eval_dev, pack_loader
from app.forensics.pack_loader import GENERATED

pytestmark = pytest.mark.skipif(
    not (GENERATED / "manifest.jsonl").is_file(), reason="data/generated not built"
)


@pytest.fixture(scope="module")
def result(request: pytest.FixtureRequest) -> dict:
    mp = pytest.MonkeyPatch()
    scored: list[str] = []
    real = pack_loader.load_pack

    def spy(entry: dict, root: Path = GENERATED):  # type: ignore[no-untyped-def]
        scored.append(entry["split"])
        return real(entry, root)

    mp.setattr(eval_dev, "load_pack", spy)
    out = eval_dev.run(GENERATED)
    mp.undo()
    out["_splits"] = scored
    return out


def test_only_the_dev_split_is_scored(result: dict) -> None:
    assert set(result["_splits"]) == {"dev"}


def test_every_fraud_type_is_detected_on_dev(result: dict) -> None:
    for ftype, hits in result["by_type"].items():
        assert hits and sum(hits) / len(hits) >= 0.9, (ftype, hits)


def test_clean_packs_are_rarely_flagged(result: dict) -> None:
    assert result["clean_total"] >= 20
    assert result["clean_fp"] / result["clean_total"] <= 0.05
    assert result["clean_doc_not_passed"] / result["clean_docs"] <= 0.02


def test_per_check_recall_and_precision(result: dict) -> None:
    for name in eval_dev.GROUND_TRUTH_NAMES:
        tp, fp, fn = result["tp"][name], result["fp"][name], result["fn"][name]
        assert tp + fn > 0, name
        assert tp / (tp + fn) >= 0.9, name
        assert fp == 0 or tp / (tp + fp) >= 0.9, name
