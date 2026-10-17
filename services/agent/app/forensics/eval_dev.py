"""Dev-split evaluation of the forensic checks against the synthetic ground truth.

    uv run --directory services/agent python -m app.forensics.eval_dev [--root DIR] [--fail-only]

Only the DEV split is evaluated and printed. Thresholds and patterns are tuned here and nowhere
else; the TEST split is for the final report (P24) and is never scored by this module. Test packs
are read for exactly one purpose: the duplicate registry must be global, so the commercial invoice
of every pack that another pack copies (a "source") is registered first, as a lender would have
had it. `duplicate_of` is used only to decide that history, never to decide a check result.
"""

import argparse
import hashlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.forensics.analyze import analyze_pdf
from app.forensics.checks import Outcome, run_checks
from app.forensics.names import GROUND_TRUTH, GROUND_TRUTH_NAMES
from app.forensics.pack_loader import GENERATED, LoadedPack, canonical_key, load_pack, manifest
from app.forensics.scoring import score_document

# fraud type -> the ground-truth checks it must fail (docs/synthetic-data.md)
FRAUD_CHECKS: dict[str, tuple[str, ...]] = {
    "QUANTITY_MISMATCH": ("QUANTITY_MATCH",),
    "VALUE_MISMATCH": ("VALUE_MATCH",),
    "VESSEL_DATE_MISMATCH": ("VESSEL_DATE_MATCH",),
    "NAME_MISMATCH": ("NAME_MATCH",),
    "DUPLICATE_INVOICE": ("DUPLICATE_INVOICE",),
    "PRICE_OUTLIER": ("PRICE_IN_BAND",),
    "ALTERED_BENEFICIARY": ("BENEFICIARY_MATCH",),
    "HIDDEN_INSTRUCTION": ("HIDDEN_TEXT_SCAN", "INSTRUCTION_SCAN"),
    "WRONG_PORT": ("PORT_MATCH",),
    "HS_CODE_MISMATCH": ("HS_CODE_MATCH",),
}


@dataclass(slots=True)
class Registry:
    """What lenders already hold: CI file hashes and canonical invoice keys -> owning pack."""

    sha: dict[str, str] = field(default_factory=dict)
    canonical: dict[str, str] = field(default_factory=dict)

    def hit(self, sha: str | None, key: str | None, pack_id: str) -> str | None:
        owner = (self.sha.get(sha or "") or self.canonical.get(key or "")) if (sha or key) else None
        return owner if owner and owner != pack_id else None


def build_registry(root: Path) -> Registry:
    entries = list(manifest(root))
    sources = {e["duplicate_of"] for e in entries if e.get("duplicate_of")}
    reg = Registry()
    for e in entries:
        if e["pack_id"] not in sources:
            continue
        doc = next(d for d in e["documents"] if d["type"] == "COMMERCIAL_INVOICE")
        data = (root / doc["path"]).read_bytes()
        reg.sha.setdefault(hashlib.sha256(data).hexdigest(), e["pack_id"])
        key = canonical_key(analyze_pdf(data, "COMMERCIAL_INVOICE").view)
        if key:
            reg.canonical.setdefault(key, e["pack_id"])
    return reg


def evaluate_pack(lp: LoadedPack, registry: Registry) -> dict[str, Any]:
    """{ground-truth name: worst status} plus per-document verdicts for one pack."""
    hit = registry.hit(lp.sha256.get("COMMERCIAL_INVOICE"), lp.canonical_key, lp.pack_id)
    per_doc: dict[str, list[Outcome]] = {}
    for doc_type, view in lp.pack.docs.items():
        reg_status = "DUPLICATE" if hit and doc_type == "COMMERCIAL_INVOICE" else "NEW"
        per_doc[doc_type] = run_checks(view, lp.pack, lp.ctx, registry_status=reg_status)
    for i, photo in enumerate(lp.pack.photos):
        per_doc[f"PRODUCTION_PHOTO:{i}"] = run_checks(photo, lp.pack, lp.ctx)
    worst: dict[str, str] = {}
    rank = {"FAIL": 3, "WARN": 2, "PASS": 1, "SKIPPED": 0}
    for outcomes in per_doc.values():
        for o in outcomes:
            gt = GROUND_TRUTH.get(o.code)
            if gt and rank[o.status] > rank.get(worst.get(gt, "SKIPPED"), 0):
                worst[gt] = o.status
    verdicts = {t: score_document(o).status for t, o in per_doc.items()}
    other = {
        o.code: o.status
        for outs in per_doc.values()
        for o in outs
        if GROUND_TRUTH.get(o.code) is None and o.status in ("WARN", "FAIL")
    }
    return {"worst": worst, "verdicts": verdicts, "other": other, "per_doc": per_doc}


def flagged(status: str | None, fail_only: bool) -> bool:
    return status == "FAIL" if fail_only else status in ("FAIL", "WARN")


def run(root: Path = GENERATED, *, fail_only: bool = False) -> dict[str, Any]:
    registry = build_registry(root)
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)
    tn: dict[str, int] = defaultdict(int)
    by_type: dict[str, list[bool]] = defaultdict(list)
    by_type_diff: dict[tuple[str, str], list[bool]] = defaultdict(list)
    clean_total = clean_fp = clean_doc_not_passed = clean_docs = 0
    tampered_docs_failed = tampered_total = 0
    misses: list[str] = []
    false_alarms: list[str] = []
    for entry in manifest(root):
        if entry["split"] != "dev":
            continue
        lp = load_pack(entry, root)
        res = evaluate_pack(lp, registry)
        worst = res["worst"]
        any_flag = False
        for name in GROUND_TRUTH_NAMES:
            positive = lp.expected[name] == "FAIL"
            pred = flagged(worst.get(name), fail_only)
            any_flag |= pred
            if positive and pred:
                tp[name] += 1
            elif positive:
                fn[name] += 1
                misses.append(f"{lp.pack_id} {name} ({'/'.join(lp.fraud_types)}, {lp.difficulty})")
            elif pred:
                fp[name] += 1
                false_alarms.append(f"{lp.pack_id} {name} ({worst.get(name)})")
            else:
                tn[name] += 1
        if not lp.fraud_types:
            clean_total += 1
            clean_fp += any_flag
            clean_docs += len(res["verdicts"])
            clean_doc_not_passed += sum(v != "PASSED" for v in res["verdicts"].values())
        else:
            tampered_total += 1
            tampered_docs_failed += any(v != "PASSED" for v in res["verdicts"].values())
            for ftype in lp.fraud_types:
                ok = all(flagged(worst.get(n), fail_only) for n in FRAUD_CHECKS[ftype])
                by_type[ftype].append(ok)
                by_type_diff[(ftype, lp.difficulty or "")].append(ok)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, "by_type": by_type, "by_type_diff": by_type_diff,
        "clean_total": clean_total, "clean_fp": clean_fp, "clean_docs": clean_docs,
        "clean_doc_not_passed": clean_doc_not_passed, "tampered_total": tampered_total,
        "tampered_flagged": tampered_docs_failed, "misses": misses, "false_alarms": false_alarms,
    }  # fmt: skip


def ratio(num: int, den: int) -> str:
    return f"{num / den:.2f}" if den else "n/a"


def render(r: dict[str, Any], fail_only: bool) -> str:
    out = [
        f"DEV split only ({'FAIL' if fail_only else 'WARN+FAIL'} counts as flagged)",
        "",
        "| check | TP | FP | FN | TN | precision | recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for n in GROUND_TRUTH_NAMES:
        t, f, m, c = r["tp"][n], r["fp"][n], r["fn"][n], r["tn"][n]
        out.append(f"| {n} | {t} | {f} | {m} | {c} | {ratio(t, t + f)} | {ratio(t, t + m)} |")
    out += [
        "",
        "| fraud type | packs | detected | recall (obvious / subtle) |",
        "|---|---|---|---|",
    ]
    for ftype in FRAUD_CHECKS:
        hits = r["by_type"][ftype]
        ob, su = r["by_type_diff"][(ftype, "obvious")], r["by_type_diff"][(ftype, "subtle")]
        out.append(
            f"| {ftype} | {len(hits)} | {sum(hits)} | {ratio(sum(hits), len(hits))} "
            f"({sum(ob)}/{len(ob)} / {sum(su)}/{len(su)}) |"
        )
    out += [
        "",
        f"clean packs flagged on any of the 11 checks: {r['clean_fp']}/{r['clean_total']} "
        f"(false-positive rate {ratio(r['clean_fp'], r['clean_total'])})",
        f"clean documents not PASSED: {r['clean_doc_not_passed']}/{r['clean_docs']}",
        f"tampered packs with at least one document not PASSED: "
        f"{r['tampered_flagged']}/{r['tampered_total']}",
    ]
    if r["misses"]:
        out += ["", "missed:", *[f"  {m}" for m in r["misses"][:30]]]
    if r["false_alarms"]:
        out += ["", "false alarms:", *[f"  {m}" for m in r["false_alarms"][:30]]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=GENERATED)
    ap.add_argument("--fail-only", action="store_true", help="count only FAIL as flagged")
    args = ap.parse_args(argv)
    if not (args.root / "manifest.jsonl").is_file():
        print(f"no generated data at {args.root}; run `python -m synthetic.generator` first")
        return 1
    print(render(run(args.root, fail_only=args.fail_only), args.fail_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
