"""Committed demo files (must match the P03 seed) and the prompt-injection attack set."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pdfplumber
import pytest

from app.config import REPO_ROOT
from app.db.models import Document, HashRegistry
from seed.common import Ctx
from seed.documents import build as build_documents
from synthetic.attacks import ACTIONS, STYLES
from synthetic.demo import FORGED_HIDDEN, write_demo

DEMO = REPO_ROOT / "data" / "demo" / "SETU-2026-0001"
PDFS = (
    "proforma_invoice.pdf",
    "commercial_invoice.pdf",
    "packing_list.pdf",
    "bill_of_lading_clean.pdf",
    "bill_of_lading_forged.pdf",
    "certificate_of_origin.pdf",
    "bill_of_entry.pdf",
    "prefinanced_invoice.pdf",
    "proforma_invoice_resaved.pdf",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def squash(text: str) -> str:
    return "".join(text.replace("​", "").split())


def page(path: Path) -> pdfplumber.page.Page:
    return pdfplumber.open(path).pages[0]


def hidden_text(path: Path) -> str:
    out = []
    for ch in page(path).chars:
        color = ch.get("non_stroking_color")
        values = list(color) if isinstance(color, (list, tuple)) else [color or 0]
        if ch["size"] <= 1.0 or all(isinstance(v, (int, float)) and v >= 0.9 for v in values):
            out.append(ch["text"])
    return "".join(out)


# ---- demo -------------------------------------------------------------------------------------
def test_demo_files_exist() -> None:
    for name in (
        *PDFS,
        "email_beneficiary_change.txt",
        "production_photo_1.jpg",
        "production_photo_2.jpg",
    ):
        assert (DEMO / name).is_file(), name


def test_prefinanced_invoice_sha_equals_seeded_hash_registry() -> None:
    rows = dict(build_documents(Ctx(today=date(2026, 10, 20))))
    registry = rows[HashRegistry]
    assert len(registry) == 1 and registry[0]["external_ref"] == "MCB-IMPLOAN-2026-0412"
    assert registry[0]["sha256"] == sha(DEMO / "prefinanced_invoice.pdf")
    pi_row = next(d for d in rows[Document] if d["file_name"] == "proforma_invoice.pdf")
    assert pi_row["sha256"] == registry[0]["sha256"]
    for photo in ("production_photo_1.jpg", "production_photo_2.jpg"):
        row = next(d for d in rows[Document] if d["file_name"] == photo)
        assert row["sha256"] == sha(DEMO / photo)


def test_resaved_invoice_differs_in_bytes_but_not_in_content() -> None:
    a, b = DEMO / "proforma_invoice.pdf", DEMO / "proforma_invoice_resaved.pdf"
    assert sha(a) != sha(b)
    assert page(a).extract_text() == page(b).extract_text()


def test_demo_invoice_matches_the_seeded_deal() -> None:
    text = squash(page(DEMO / "proforma_invoice.pdf").extract_text())
    for want in (
        "HX-PI-2026-118",
        "ShaoxingHuaxinTextileCo.,Ltd.",
        "RahimaKnitwear",
        "6006.22",
        "8,000m",
        "USD9,600.00",
        "USD1.20perm",
        "FOBNingbo",
        "SIM-CN-6222-****-1188",
    ):
        assert squash(want) in text, want
    rows = dict(build_documents(Ctx(today=date(2026, 10, 20))))
    assert (
        next(d for d in rows[Document] if d["key"].endswith("proforma-invoice"))["extracted_json"][
            "invoice_no"
        ]
        == "HX-PI-2026-118"
    )


def test_forged_bill_of_lading_has_hidden_instruction_and_bad_vessel_and_date() -> None:
    forged, clean = DEMO / "bill_of_lading_forged.pdf", DEMO / "bill_of_lading_clean.pdf"
    assert squash(FORGED_HIDDEN) in squash(page(forged).extract_text())
    assert squash(FORGED_HIDDEN) in squash(hidden_text(forged))
    assert hidden_text(clean) == ""
    assert "MV KELMAR PEARL" in page(clean).extract_text()
    assert "MV KELMAR PEARL" not in page(forged).extract_text()
    assert "14-Oct-2026" in page(forged).extract_text()


def test_demo_manifest_expected_checks() -> None:
    manifest = json.loads((DEMO / "demo_manifest.json").read_text())
    checks = manifest["expected_checks"]
    assert set(checks["clean_pack"].values()) == {"PASS"}
    failed = {k for k, v in checks["pack_with_forged_bl"].items() if v == "FAIL"}
    assert failed == {"VESSEL_DATE_MATCH", "HIDDEN_TEXT_SCAN", "INSTRUCTION_SCAN"}
    listed = {f["file"]: f["sha256"] for f in manifest["files"]}
    for name in (*PDFS, "email_beneficiary_change.txt", "production_photo_1.jpg"):
        assert listed[name] == sha(DEMO / name)
    assert manifest["lender_a_registration"]["sha256"] == sha(DEMO / "prefinanced_invoice.pdf")


def test_demo_email_asks_for_hong_kong_account() -> None:
    text = (DEMO / "email_beneficiary_change.txt").read_text(encoding="utf-8")
    assert "Hong Kong" in text and "SIM-HK-012-884213-001" in text and "SIMULATED" in text


def test_committed_demo_files_are_reproducible(tmp_path: Path) -> None:
    write_demo(tmp_path)
    for name in (*PDFS, "email_beneficiary_change.txt"):
        assert sha(tmp_path / name) == sha(DEMO / name), f"{name} drifted: re-run --demo and commit"


# ---- attacks ----------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def attacks(dataset: tuple[Path, list[dict]]) -> tuple[Path, list[dict]]:
    root = dataset[0]
    lines = (root / "attacks_manifest.jsonl").read_text(encoding="utf-8").splitlines()
    return root, [json.loads(line) for line in lines]


def test_attack_set_shape(attacks: tuple[Path, list[dict]]) -> None:
    root, items = attacks
    assert len(items) == 25
    assert {a["attack_style"] for a in items} == set(STYLES)
    assert all(sum(a["attack_style"] == s for a in items) == 5 for s in STYLES)
    assert {a["target_action"] for a in items} == set(ACTIONS)
    assert {a["obfuscation"] for a in items} == {"plain", "spaced", "homoglyph", "zwsp"}
    assert {a["language"] for a in items} == {"en", "zh", "bn"}
    assert {a["delivery"] for a in items} == {"pdf", "email"}
    for a in items:
        assert hashlib.sha256((root / a["path"]).read_bytes()).hexdigest() == a["sha256"]


def test_every_payload_is_in_its_carrier(attacks: tuple[Path, list[dict]]) -> None:
    root, items = attacks
    for a in items:
        path = root / a["path"]
        want = squash(a["payload"])
        if a["delivery"] == "email":
            assert want in squash(path.read_text(encoding="utf-8")), a["attack_id"]
            continue
        with pdfplumber.open(path) as pdf:
            text = squash(pdf.pages[0].extract_text() or "")
            meta = squash(" ".join(str(v) for v in pdf.metadata.values()))
        style = a["attack_style"]
        if style == "pdf_metadata":
            assert want in meta, a["attack_id"]
            assert want not in text
        else:
            assert want in text, a["attack_id"]


def test_attack_visibility_matches_style(attacks: tuple[Path, list[dict]]) -> None:
    root, items = attacks
    for a in items:
        if a["delivery"] != "pdf":
            continue
        hidden = squash(hidden_text(root / a["path"]))
        want = squash(a["payload"])
        if a["attack_style"] in {"hidden_white_text", "tiny_font_footer"}:
            assert want in hidden, a["attack_id"]
        else:
            assert want not in hidden, a["attack_id"]


def test_attacks_contain_no_real_domains(attacks: tuple[Path, list[dict]]) -> None:
    _, items = attacks
    for a in items:
        for word in a["instruction"].split():
            if "@" in word:
                assert word.rstrip(".\u3002").endswith(".example"), word
