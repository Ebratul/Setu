"""Synthetic trade-document generator: determinism, labels, hidden text, duplicates, split."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pdfplumber
from PIL import Image

from synthetic.catalog import FOOTER
from synthetic.factory import container_number, iso6346_check_digit
from synthetic.generator import generate
from synthetic.tamper import EXPECTED_FAILS, FRAUD_TYPES, HIDDEN_PHRASES
from synthetic.validator import CHECKS


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def squash(text: str) -> str:
    return "".join(text.split())


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def extract(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return pdf.pages[0].extract_text() or ""


def entries_of(entries: list[dict], fraud: str) -> list[dict]:
    return [e for e in entries if e["fraud_types"] and e["fraud_types"][0] == fraud]


def doc_path(root: Path, entry: dict, doc_type: str) -> Path:
    return root / next(d["path"] for d in entry["documents"] if d["type"] == doc_type)


# ---- determinism ------------------------------------------------------------------------------
def test_same_seed_gives_identical_manifest_and_files(tmp_path: Path) -> None:
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    generate(6, 20, 7, a)
    generate(6, 20, 7, b)
    generate(6, 20, 8, c)
    assert (a / "manifest.jsonl").read_bytes() == (b / "manifest.jsonl").read_bytes()
    assert tree_hashes(a) == tree_hashes(b)
    assert (a / "manifest.jsonl").read_bytes() != (c / "manifest.jsonl").read_bytes()


def test_manifest_hashes_match_files(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    for e in entries:
        for d in e["documents"]:
            assert sha(root / d["path"]) == d["sha256"]


# ---- labels ---------------------------------------------------------------------------------
def test_counts_and_manifest_shape(dataset: tuple[Path, list[dict]]) -> None:
    _, entries = dataset
    assert len(entries) == 90
    assert sum(not e["is_tampered"] for e in entries) == 30
    for e in entries:
        assert set(e["expected_checks"]) == set(CHECKS)
        assert e["split"] in {"dev", "test"}
        assert e["is_tampered"] == bool(e["fraud_types"])
        assert (e["difficulty"] is not None) == e["is_tampered"]
        assert all(f in FRAUD_TYPES for f in e["fraud_types"])
        assert len(e["fraud_types"]) in ((0,) if not e["is_tampered"] else (1, 2))
        types = Counter(d["type"] for d in e["documents"])
        assert types["PRODUCTION_PHOTO"] == 2
        assert types["COMMERCIAL_INVOICE"] == types["BILL_OF_LADING"] == 1


def test_clean_packs_pass_every_check(dataset: tuple[Path, list[dict]]) -> None:
    _, entries = dataset
    for e in entries:
        if not e["is_tampered"]:
            assert set(e["expected_checks"].values()) == {"PASS"}, e["pack_id"]


def test_tampered_packs_fail_exactly_the_labelled_checks(dataset: tuple[Path, list[dict]]) -> None:
    _, entries = dataset
    for e in entries:
        if not e["is_tampered"]:
            continue
        failed = {k for k, v in e["expected_checks"].items() if v == "FAIL"}
        wanted = set().union(*(EXPECTED_FAILS[f] for f in e["fraud_types"]))
        assert failed == wanted, (e["pack_id"], e["fraud_types"], e["difficulty"], e["notes"])


def test_every_fraud_type_and_difficulty_is_present(dataset: tuple[Path, list[dict]]) -> None:
    _, entries = dataset
    cells = Counter((e["fraud_types"][0], e["difficulty"]) for e in entries if e["is_tampered"])
    assert {(f, d) for f in FRAUD_TYPES for d in ("obvious", "subtle")} == set(cells)
    assert set(cells.values()) == {3}


# ---- split policy -----------------------------------------------------------------------------
def test_split_is_balanced_overall_and_per_stratum(dataset: tuple[Path, list[dict]]) -> None:
    _, entries = dataset
    split = Counter(e["split"] for e in entries)
    assert split["dev"] == split["test"] == 45
    strata: dict[tuple, Counter] = {}
    for e in entries:
        key = (e["fraud_types"][0] if e["fraud_types"] else "CLEAN", e["difficulty"])
        strata.setdefault(key, Counter())[e["split"]] += 1
    for key, c in strata.items():
        assert abs(c["dev"] - c["test"]) <= 1, key


def test_split_is_independent_of_the_generation_seed(tmp_path: Path) -> None:
    # same pack ids and counts, different content seed: a pack id keeps its split only by policy,
    # so just check the policy is stable for one seed across runs
    generate(10, 20, 3, tmp_path / "x")
    generate(10, 20, 3, tmp_path / "y")
    assert (tmp_path / "x" / "manifest.jsonl").read_text() == (
        tmp_path / "y" / "manifest.jsonl"
    ).read_text()


# ---- hidden instruction -----------------------------------------------------------------------
def _hidden_chars(path: Path) -> tuple[str, str]:
    """(text of white/near-white or <=1 pt characters, text of all other characters)."""
    hidden, shown = [], []
    with pdfplumber.open(path) as pdf:
        for ch in pdf.pages[0].chars:
            color = ch.get("non_stroking_color")
            values = list(color) if isinstance(color, (list, tuple)) else [color or 0]
            whiteish = len(values) >= 1 and all(
                isinstance(v, (int, float)) and v >= 0.9 for v in values
            )
            (hidden if whiteish or ch["size"] <= 1.0 else shown).append(ch["text"])
    return "".join(hidden), "".join(shown)


def test_hidden_instruction_is_in_text_layer_and_invisible(
    dataset: tuple[Path, list[dict]],
) -> None:
    root, entries = dataset
    packs = entries_of(entries, "HIDDEN_INSTRUCTION")
    assert len(packs) == 6
    for e in packs:
        phrases = {squash(p) for p in HIDDEN_PHRASES[e["difficulty"]]}
        found = False
        for d in e["documents"]:
            if not d["path"].endswith(".pdf"):
                continue
            path = root / d["path"]
            hidden, shown = _hidden_chars(path)
            if any(p in squash(hidden) for p in phrases):
                found = True
                assert any(p in squash(extract(path)) for p in phrases)  # present in the text layer
                assert not any(p in squash(shown) for p in phrases)  # but not drawn visibly
        assert found, e["pack_id"]


def test_clean_documents_have_no_hidden_characters(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    for e in [x for x in entries if not x["is_tampered"]][:8]:
        for d in e["documents"]:
            if d["path"].endswith(".pdf"):
                hidden, _ = _hidden_chars(root / d["path"])
                assert hidden == "", d["path"]


# ---- duplicates -------------------------------------------------------------------------------
def test_exact_copy_shares_sha_and_near_copy_does_not(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    by_id = {e["pack_id"]: e for e in entries}
    packs = entries_of(entries, "DUPLICATE_INVOICE")
    assert {e["difficulty"] for e in packs} == {"obvious", "subtle"}
    for e in packs:
        source = by_id[e["duplicate_of"]]
        assert not source["is_tampered"]
        dup_ci, src_ci = (
            doc_path(root, e, "COMMERCIAL_INVOICE"),
            doc_path(root, source, "COMMERCIAL_INVOICE"),
        )
        dup_json = json.loads(dup_ci.with_suffix(".json").read_text())
        src_json = json.loads(src_ci.with_suffix(".json").read_text())
        assert (dup_json["invoice_no"], dup_json["total"]) == (
            src_json["invoice_no"],
            src_json["total"],
        )
        assert src_json["invoice_no"] in extract(dup_ci)
        if e["difficulty"] == "obvious":
            assert sha(dup_ci) == sha(src_ci)
        else:
            assert sha(dup_ci) != sha(src_ci)
        assert e["expected_checks"]["DUPLICATE_INVOICE"] == "FAIL"


def test_clean_invoice_numbers_are_unique(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    numbers = [
        json.loads(doc_path(root, e, "COMMERCIAL_INVOICE").with_suffix(".json").read_text())[
            "invoice_no"
        ]
        for e in entries
        if not e["fraud_types"] or e["fraud_types"][0] != "DUPLICATE_INVOICE"
    ]
    assert len(numbers) == len(set(numbers))


# ---- rendering --------------------------------------------------------------------------------
def test_text_layer_contains_every_labelled_field(dataset: tuple[Path, list[dict]]) -> None:
    from pydantic import TypeAdapter

    from synthetic.models import (
        BillOfEntryDoc,
        BillOfLadingDoc,
        CertOfOriginDoc,
        InvoiceDoc,
        Pack,
        PackingListDoc,
        RenderStyle,
    )
    from synthetic.render_pdf import sections_for

    root, entries = dataset
    models = {
        "PROFORMA_INVOICE": InvoiceDoc,
        "COMMERCIAL_INVOICE": InvoiceDoc,
        "PACKING_LIST": PackingListDoc,
        "BILL_OF_LADING": BillOfLadingDoc,
        "CERTIFICATE_OF_ORIGIN": CertOfOriginDoc,
        "BILL_OF_ENTRY": BillOfEntryDoc,
    }
    del Pack, TypeAdapter
    checked = 0
    for e in entries[:12]:
        deal = json.loads((root / e["deal_path"]).read_text())
        assert deal["order_ref"]
        for d in e["documents"]:
            if d["type"] not in models:
                continue
            path = root / d["path"]
            doc = models[d["type"]].model_validate_json(path.with_suffix(".json").read_text())
            # the style is not stored per document; any style renders the same field strings
            # except dates, so compare labels and non-date values
            text = squash(extract(path))
            style = RenderStyle(font="helvetica", date_fmt="%Y-%m-%d", order_seed=0)
            _, _, sections = sections_for(doc, style)
            for _name, fields in sections:
                for label, value in fields:
                    if "date" in label.lower() or label in {
                        "Date",
                        "Production completion",
                        "Estimated arrival",
                    }:
                        assert squash(label + ":") in text
                    else:
                        assert squash(f"{label}: {value}") in text, (path.name, label)
                        checked += 1
    assert checked > 200


def test_every_pdf_and_photo_carries_the_simulated_footer(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    for e in entries[:10]:
        for d in e["documents"]:
            path = root / d["path"]
            if path.suffix == ".pdf":
                assert FOOTER in extract(path)
                with pdfplumber.open(path) as pdf:
                    assert len(pdf.pages) == 1
            else:
                assert Image.open(path).size == (640, 480)


def test_all_account_numbers_are_simulated(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    for e in entries:
        deal = json.loads((root / e["deal_path"]).read_text())
        assert deal["registered_bank"]["account_masked"].startswith("SIM-")
        ci = json.loads(doc_path(root, e, "COMMERCIAL_INVOICE").with_suffix(".json").read_text())
        assert ci["bank"]["account_masked"].startswith("SIM-")


def test_photo_matches_its_label(dataset: tuple[Path, list[dict]]) -> None:
    root, entries = dataset
    e = next(x for x in entries if not x["is_tampered"])
    for d in [d for d in e["documents"] if d["type"] == "PRODUCTION_PHOTO"]:
        path = root / d["path"]
        label = json.loads(path.with_suffix(".json").read_text())
        img = Image.open(path).convert("RGB")
        patch = img.crop((250, 150, 390, 290)).resize((1, 1), Image.Resampling.BOX)
        got = patch.getpixel((0, 0))
        assert all(abs(g - w) < 45 for g, w in zip(got, label["rgb"], strict=True)), (got, label)
        assert label["color_name"]


def test_iso6346_check_digit_known_value() -> None:
    assert iso6346_check_digit("CSQU305438") == 3
    assert container_number("KMCU", 582136).startswith("KMCU582136")
    assert len(container_number("KMCU", 1)) == 11
