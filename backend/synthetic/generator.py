"""CLI and pipeline: `python -m synthetic.generator --clean 100 --tampered 100 --seed 42`.

Run from backend: `uv run python -m synthetic.generator ...`. Same seed gives identical
manifests and identical file bytes. Outputs go to `data/generated/` (git-ignored) or, with
`--demo`, only to `data/demo/SETU-2026-0001/`.
"""

import argparse
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from synthetic import catalog as cat
from synthetic import tamper
from synthetic.factory import (
    buyer_pool,
    clean_pack,
    rng_for,
    supplier_pool,
)
from synthetic.models import ManifestDoc, ManifestEntry, Pack
from synthetic.render_pdf import render_pack_pdfs
from synthetic.render_photo import render_photo
from synthetic.tamper import DUPLICATE_INVOICE, FRAUD_TYPES, Difficulty
from synthetic.validator import Registry, canonical_key, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "generated"
SPLIT_SEED = 20261020  # fixed, independent of --seed, so the dev/test policy never silently moves
SECONDARY_RATE = 0.2


@dataclass(slots=True)
class Built:
    pack: Pack
    pdfs: dict[str, bytes]
    photos: dict[str, bytes]
    fraud_types: list[str]
    difficulty: Difficulty | None
    notes: str
    expected: dict[str, str]
    split: str = "dev"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_json(obj: object) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def assign_splits(items: list[Built]) -> None:
    """Stratified 50/50 dev/test split: strata are clean and each fraud type x difficulty."""
    strata: dict[tuple[str, str], list[Built]] = {}
    for b in items:
        key = (b.fraud_types[0], b.difficulty or "") if b.fraud_types else ("CLEAN", "")
        strata.setdefault(key, []).append(b)
    rng = rng_for(SPLIT_SEED, "split")
    flip = 0
    for key in sorted(strata):
        group = sorted(strata[key], key=lambda b: b.pack.pack_id)
        rng.shuffle(group)
        for i, b in enumerate(group):
            b.split = "dev" if (i + flip) % 2 == 0 else "test"
        if len(group) % 2:
            flip += 1  # odd strata alternate who gets the extra pack, so totals stay balanced


def _tamper_plan(j: int) -> tuple[str, Difficulty]:
    fraud = FRAUD_TYPES[j % len(FRAUD_TYPES)]
    diff: Difficulty = "obvious" if (j // len(FRAUD_TYPES)) % 2 == 0 else "subtle"
    return fraud, diff


def build_dataset(clean: int, tampered: int, seed: int) -> list[Built]:
    if clean + tampered >= 8000:
        raise ValueError("at most 7,999 packs")
    if tampered and not clean:
        raise ValueError("duplicate-invoice packs need at least one clean pack")
    suppliers, buyers = supplier_pool(seed), buyer_pool(seed)
    total = clean + tampered
    ids = rng_for(seed, "ids").sample(range(1, total + 1), total)
    registry = Registry()
    built: list[Built] = []

    def finish(pack: Pack, fraud_types: list[str], diff: Difficulty | None, notes: str) -> Built:
        pdfs = render_pack_pdfs(pack)
        photos = {p.file_name: render_photo(p) for p in pack.photos}
        ci_sha = sha256_hex(pdfs["commercial_invoice"])
        expected = validate(pack, ci_sha, registry)
        registry.register(ci_sha, canonical_key(pack.invoice), pack.pack_id)
        return Built(pack, pdfs, photos, fraud_types, diff, notes, dict(expected))

    for k in range(clean):
        pack = clean_pack(seed, k, suppliers, buyers)
        pack.pack_id = f"PACK-{ids[k]:04d}"
        built.append(finish(pack, [], None, "clean: all documents agree"))
    clean_packs = [b.pack for b in built]

    for j in range(tampered):
        slot = clean + j
        primary, diff = _tamper_plan(j)
        rng = rng_for(seed, f"tamper:{j}")
        pack_id = f"PACK-{ids[slot]:04d}"
        if primary == DUPLICATE_INVOICE:
            source = rng.choice(clean_packs)
            pack, note = tamper.duplicate_invoice(source, pack_id, diff)
            built.append(finish(pack, [primary], diff, note))
            continue
        pack = clean_pack(seed, slot, suppliers, buyers)
        pack.pack_id = pack_id
        notes = [tamper.apply(primary, pack, rng, diff)]
        fraud_types = [primary]
        if rng.random() < SECONDARY_RATE:
            options = [
                f
                for f in FRAUD_TYPES
                if f != primary
                and f != DUPLICATE_INVOICE
                and frozenset({primary, f}) not in tamper.INCOMPATIBLE
            ]
            secondary = rng.choice(options)
            sec_diff: Difficulty = rng.choice(("obvious", "subtle"))
            notes.append(
                f"secondary {secondary} ({sec_diff}): "
                + tamper.apply(secondary, pack, rng, sec_diff)
            )
            fraud_types.append(secondary)
        built.append(finish(pack, fraud_types, diff, "; ".join(notes)))

    built.sort(key=lambda b: b.pack.pack_id)
    assign_splits(built)
    return built


def write_dataset(items: list[Built], out: Path) -> list[ManifestEntry]:
    packs_dir = out / "packs"
    if packs_dir.exists():
        shutil.rmtree(packs_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries: list[ManifestEntry] = []
    for b in items:
        pdir = packs_dir / b.pack.pack_id
        pdir.mkdir(parents=True)
        docs: list[ManifestDoc] = []
        for stem, doc in b.pack.pdf_docs():
            data = b.pdfs[stem]
            (pdir / f"{stem}.pdf").write_bytes(data)
            (pdir / f"{stem}.json").write_bytes(dump_json(doc.model_dump(mode="json")))
            docs.append(
                ManifestDoc(
                    type=doc.doc_type,
                    path=f"packs/{b.pack.pack_id}/{stem}.pdf",
                    sha256=sha256_hex(data),
                )
            )
        for photo in b.pack.photos:
            data = b.photos[photo.file_name]
            stem = photo.file_name.removesuffix(".jpg")
            (pdir / photo.file_name).write_bytes(data)
            (pdir / f"{stem}.json").write_bytes(dump_json(photo.model_dump(mode="json")))
            docs.append(
                ManifestDoc(
                    type=photo.doc_type,
                    path=f"packs/{b.pack.pack_id}/{photo.file_name}",
                    sha256=sha256_hex(data),
                )
            )
        (pdir / "deal.json").write_bytes(dump_json(b.pack.deal.model_dump(mode="json")))
        entries.append(
            ManifestEntry(
                pack_id=b.pack.pack_id,
                split=b.split,  # type: ignore[arg-type]
                is_tampered=bool(b.fraud_types),
                fraud_types=b.fraud_types,
                difficulty=b.difficulty,
                documents=docs,
                deal_path=f"packs/{b.pack.pack_id}/deal.json",
                expected_checks=b.expected,  # type: ignore[arg-type]
                duplicate_of=b.pack.duplicate_of,
                seed=b.pack.seed,
                notes=b.notes,
            )
        )
    lines = [
        json.dumps(e.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) for e in entries
    ]
    (out / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bands = {
        g.hs: {
            "name": g.name,
            "unit": g.unit,
            "min": str(g.band[0]),
            "max": str(g.band[1]),
            "currency": "USD",
        }
        for g in cat.GOODS
    }
    (out / "price_bands.json").write_bytes(dump_json(bands))
    return entries


def summary_table(entries: list[ManifestEntry]) -> str:
    cells: Counter[tuple[str, str, str]] = Counter()
    for e in entries:
        cells[(e.fraud_types[0] if e.fraud_types else "CLEAN", e.difficulty or "-", e.split)] += 1
    secondary = sum(1 for e in entries if len(e.fraud_types) > 1)
    rows = sorted({(k[0], k[1]) for k in cells})
    head = f"{'fraud type':<22}{'difficulty':<11}{'dev':>5}{'test':>6}{'total':>7}"
    lines = [head, "-" * len(head)]
    for fraud, diff in rows:
        dev, test = cells[(fraud, diff, "dev")], cells[(fraud, diff, "test")]
        lines.append(f"{fraud:<22}{diff:<11}{dev:>5}{test:>6}{dev + test:>7}")
    n_dev = sum(1 for e in entries if e.split == "dev")
    lines += [
        "-" * len(head),
        f"{'ALL':<22}{'':<11}{n_dev:>5}{len(entries) - n_dev:>6}{len(entries):>7}",
        f"clean={sum(1 for e in entries if not e.is_tampered)} "
        f"tampered={sum(1 for e in entries if e.is_tampered)} (with a secondary type: {secondary})",
    ]
    return "\n".join(lines)


def generate(
    clean: int, tampered: int, seed: int, out: Path, attacks: bool = True
) -> list[ManifestEntry]:
    items = build_dataset(clean, tampered, seed)
    entries = write_dataset(items, out)
    if attacks:
        from synthetic.attacks import write_attacks

        write_attacks(seed, out)
    return entries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m synthetic.generator", description=__doc__)
    ap.add_argument("--clean", type=int, default=100)
    ap.add_argument("--tampered", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="default: data/generated (demo: data/demo/SETU-2026-0001)",
    )
    ap.add_argument(
        "--no-attacks", action="store_true", help="skip the prompt-injection attack set"
    )
    ap.add_argument(
        "--demo", action="store_true", help="regenerate only data/demo/ (fixed content)"
    )
    args = ap.parse_args(argv)
    if args.demo:
        from synthetic.demo import write_demo

        written = write_demo(args.out)
        print(f"wrote {len(written)} demo files")
        return 0
    entries = generate(
        args.clean, args.tampered, args.seed, args.out or DEFAULT_OUT, attacks=not args.no_attacks
    )
    print(summary_table(entries))
    print(f"\nwrote {len(entries)} packs and manifest.jsonl to {args.out or DEFAULT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
