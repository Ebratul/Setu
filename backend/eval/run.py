"""Evaluation harness (P24): runs every measurement on the TEST split and writes eval/results/.

    uv run --directory backend python -m eval.run [--split test] [--only forensics,duplicates,injection,pii,tiers]

Numbers are measured, never assumed. The test split is for reporting only; thresholds are tuned on dev.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.forensics import eval_dev
from app.forensics.names import GROUND_TRUTH_NAMES
from app.forensics.pack_loader import GENERATED, load_pack, manifest
from app.forensics.scoring import score_document
from app.services.risk.engine import Action, RiskContext, evaluate

RESULTS = Path(__file__).resolve().parent / "results"
ALL = ("forensics", "duplicates", "injection", "pii", "tiers")


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def forensics(split: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode, fail_only in (("warn_or_fail", False), ("fail_only", True)):
        r = eval_dev.run(GENERATED, fail_only=fail_only, split=split)
        checks = {}
        for n in GROUND_TRUTH_NAMES:
            tp, fp, fn = r["tp"][n], r["fp"][n], r["fn"][n]
            checks[n] = {"tp": tp, "fp": fp, "fn": fn, "tn": r["tn"][n],
                         "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn)}  # fmt: skip
        TP, FP, FN = (sum(r[k].values()) for k in ("tp", "fp", "fn"))
        types = {t: {"packs": len(h), "detected": sum(h), "recall": _ratio(sum(h), len(h))}
                 for t, h in r["by_type"].items()}  # fmt: skip
        out[mode] = {
            "checks": checks, "by_fraud_type": types,
            "overall": {"precision": _ratio(TP, TP + FP), "recall": _ratio(TP, TP + FN),
                        "f1": _ratio(2 * TP, 2 * TP + FP + FN)},
            "clean_packs": r["clean_total"], "clean_packs_flagged": r["clean_fp"],
            "tampered_packs": r["tampered_total"],
            "tampered_packs_with_unpassed_doc": r["tampered_flagged"],
            "misses": r["misses"], "false_alarms": r["false_alarms"],
        }  # fmt: skip
    return out


def duplicates(split: str) -> dict[str, Any]:
    from app.db.session import batch_session
    from app.forensics import eval_registry

    with batch_session() as db:
        r = eval_registry.run(db, GENERATED, split)
    stats = {k: {"n": len(v), "correct": sum(v), "rate": _ratio(sum(v), len(v))}
             for k, v in r["stats"].items()}  # fmt: skip
    return {"variants": stats, "missed": r["missed"]}


def injection(split: str) -> dict[str, Any]:
    from app.security.injection.suite import run_attack_suite

    return run_attack_suite(split)  # type: ignore[arg-type]


def pii(split: str) -> dict[str, Any]:
    from app.privacy.eval import run_documents

    return run_documents(split)


def tiers(split: str) -> dict[str, Any]:
    """Release of a USD 3,000 milestone against each pack's own forensic result, via the real risk engine."""
    registry = eval_dev.build_registry(GENERATED)
    rows: list[dict[str, Any]] = []
    for entry in manifest(GENERATED):
        if entry["split"] != split:
            continue
        lp = load_pack(entry, GENERATED)
        res = eval_dev.evaluate_pack(lp, registry)
        scores = [score_document(o) for o in res["per_doc"].values()]
        worst = res["worst"]
        dup = registry.hit(lp.sha256.get("COMMERCIAL_INVOICE"), lp.canonical_key, lp.pack_id)
        ctx = RiskContext(
            action=Action.RELEASE_TRANCHE, amount=Decimal("3000"), amount_usd=Decimal("3000"),
            max_document_fraud_score=max((s.score for s in scores), default=0),
            any_document_warning=any(s.status == "WARNING" for s in scores),
            any_document_failed=any(s.status == "FAILED" for s in scores),
            duplicate_hash=dup is not None,
            instruction_from_document=any(
                worst.get(n) in ("FAIL", "WARN") for n in ("HIDDEN_TEXT_SCAN", "INSTRUCTION_SCAN")
            ),
        )  # fmt: skip
        d = evaluate(ctx)
        rows.append({"pack": lp.pack_id, "tampered": bool(lp.fraud_types), "tier": d.tier,
                     "decision": str(d.decision)})  # fmt: skip

    def count(sel: list[dict[str, Any]]) -> dict[str, Any]:
        auto = sum(r["tier"] <= 1 and r["decision"] != "BLOCK" for r in sel)
        blocked = sum("BLOCK" in r["decision"] for r in sel)
        return {"n": len(sel), "auto_tier0_1": auto, "escalated_tier2_3": len(sel) - auto - blocked,
                "blocked": blocked, "auto_share": _ratio(auto, len(sel))}  # fmt: skip

    clean = [r for r in rows if not r["tampered"]]
    bad = [r for r in rows if r["tampered"]]
    return {"all": count(rows), "clean": count(clean), "tampered": count(bad),
            "false_escalation_rate_clean": _ratio(len(clean) - count(clean)["auto_tier0_1"], len(clean)),
            "tampered_auto_released": count(bad)["auto_tier0_1"]}  # fmt: skip


def md(res: dict[str, Any]) -> str:
    f = res.get("forensics", {}).get("warn_or_fail")
    L = [f"# Setu evaluation ({res['split']} split)", "",
         f"Generated {res['generated_at']} · seed data `data/generated` · no LLM extraction used · synthetic data, a ceiling not real-world accuracy.", ""]  # fmt: skip
    if f:
        o = res["forensics"]["fail_only"]["overall"]
        L += ["## Fraud detection (11 checks)", "",
              f"WARN or FAIL counts as flagged: precision {f['overall']['precision']}, recall {f['overall']['recall']}, F1 {f['overall']['f1']}.",
              f"FAIL only: precision {o['precision']}, recall {o['recall']}, F1 {o['f1']}.",
              f"Clean packs flagged: {f['clean_packs_flagged']}/{f['clean_packs']}. Tampered packs with at least one unpassed document: {f['tampered_packs_with_unpassed_doc']}/{f['tampered_packs']}.",
              "", "| fraud type | packs | detected | recall |", "|---|---|---|---|"]  # fmt: skip
        L += [
            f"| {t} | {v['packs']} | {v['detected']} | {v['recall']} |"
            for t, v in f["by_fraud_type"].items()
        ]
        L += ["", "| check | TP | FP | FN | precision | recall |", "|---|---|---|---|---|---|"]
        L += [f"| {n} | {v['tp']} | {v['fp']} | {v['fn']} | {v['precision']} | {v['recall']} |" for n, v in f["checks"].items()]  # fmt: skip
    if "duplicates" in res:
        L += [
            "",
            "## Duplicate-document catch rate",
            "",
            "| variant | n | caught | rate |",
            "|---|---|---|---|",
        ]
        L += [
            f"| {k} | {v['n']} | {v['correct']} | {v['rate']} |"
            for k, v in res["duplicates"]["variants"].items()
        ]
    if "injection" in res:
        L += [
            "",
            "## Prompt injection (attack success rate)",
            "",
            "| defences | attack success | money moved |",
            "|---|---|---|",
        ]
        L += [
            f"| {m} | {s['attack_success_rate']:.0%} | {s['money_moved']} |"
            for m, s in res["injection"]["modes"].items()
        ]
        d = res["injection"]["detection"]
        L += [
            "",
            f"Detection recall {d['recall']:.0%}; false positives {d['false_positives']}/{d['clean_documents']}.",
        ]
    if "pii" in res:
        L += ["", "## PII leakage to the model", "", "```json", json.dumps(res["pii"], indent=2, ensure_ascii=False)[:3000], "```"]  # fmt: skip
    if "tiers" in res:
        t = res["tiers"]
        L += ["", "## Auto vs escalated (USD 3,000 release per pack)", "", "| group | n | auto (T0/1) | escalated (T2/3) | blocked |", "|---|---|---|---|---|"]  # fmt: skip
        L += [f"| {g} | {t[g]['n']} | {t[g]['auto_tier0_1']} | {t[g]['escalated_tier2_3']} | {t[g]['blocked']} |" for g in ("all", "clean", "tampered")]  # fmt: skip
        L += ["", f"False-escalation rate on clean packs: {t['false_escalation_rate_clean']}. Tampered packs auto-released: {t['tampered_auto_released']}."]  # fmt: skip
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--only", default=",".join(ALL))
    args = ap.parse_args(argv)
    want = [x for x in args.only.split(",") if x]
    res: dict[str, Any] = {
        "split": args.split,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    for name in want:
        print(f"running {name} ...", flush=True)
        try:
            res[name] = globals()[name](args.split)
        except Exception as exc:  # report, never fake
            res[name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"  {name} FAILED: {exc}", file=sys.stderr)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS.parent / "results.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False, default=str)
    )
    (RESULTS / "metrics.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False, default=str)
    )
    (RESULTS / "metrics.md").write_text(md(res))
    print(md(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
