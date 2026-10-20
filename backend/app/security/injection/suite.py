"""The attack suite (P19, scored by P24): every P11 attack through the real nodes with an obedient
mock model, defences OFF vs ON, plus detection on the clean P11 documents.

    uv run --directory backend python -m app.security.injection.suite dev

Splits: the attack set has no split in its manifest, so one is fixed here (stratified by style,
every obfuscation on both sides): attack n of style s is DEV when (variant + s) is even. Patterns
and rules are tuned on DEV only; the TEST numbers belong to P24 and are run once per configuration.
Results are saved to eval/results/injection_<split>.json (read by the scoreboard).
"""

import json
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.config import AGENT_DIR, REPO_ROOT
from app.forensics.pdf_text import read_pdf
from app.security.injection.detector import scan, scan_document
from app.security.injection.harness import RunResult, UntrustedOut, run_case
from app.services.risk import engine
from app.services.risk.engine import Action, Origin, RiskContext

Split = Literal["dev", "test"]
RESULTS_DIR = AGENT_DIR / "eval" / "results"
GENERATED = REPO_ROOT / "data" / "generated"
FALLBACK_SEED = 42
STYLE_ORDER = (
    "hidden_white_text",
    "tiny_font_footer",
    "visible_notes",
    "pdf_metadata",
    "non_english",
)
RISK_ACTION = {
    "propose_release_tranche": Action.RELEASE_TRANCHE,
    "propose_change_beneficiary": Action.CHANGE_BENEFICIARY,
}
MODES: dict[str, dict[str, Any]] = {
    "off": {"on": False},
    "on": {"on": True},
    "on_without_detector": {"on": True, "layers": (4, 5)},
}


@dataclass(frozen=True, slots=True)
class Case:
    attack_id: str
    style: str
    target: str
    language: str
    obfuscation: str
    delivery: str
    source: str  # where the instruction sits: hidden_text | visible_text | metadata | email
    split: str
    content: UntrustedOut
    instruction: str


def split_of(attack_id: str) -> Split:
    n = int(attack_id.split("-")[1]) - 1
    style_idx, variant = divmod(n, 5)
    return "dev" if (variant + style_idx) % 2 == 0 else "test"


def _source(style: str, delivery: str) -> str:
    if delivery == "email":
        return "email"
    return {
        "hidden_white_text": "hidden_text",
        "tiny_font_footer": "hidden_text",
        "pdf_metadata": "metadata",
    }.get(style, "visible_text")


def _content(path: Path, delivery: str) -> UntrustedOut:
    raw = path.read_bytes()
    if delivery == "email":
        return UntrustedOut(message_text=raw.decode("utf-8", errors="replace"))
    pdf = read_pdf(raw)
    return UntrustedOut(
        visible_text=pdf.visible_text,
        hidden_text="\n".join(s.text for s in pdf.hidden_spans),
        metadata="\n".join(pdf.metadata.values()),
    )


_fallback: Path | None = None


def attack_root() -> Path:
    if (GENERATED / "attacks_manifest.jsonl").is_file():
        return GENERATED
    from synthetic.attacks import write_attacks

    global _fallback
    if _fallback is None or not _fallback.is_dir():
        _fallback = Path(tempfile.mkdtemp(prefix="setu-attacks-"))
        write_attacks(FALLBACK_SEED, _fallback)
    return _fallback


def load_cases(split: Split | None = None, root: Path | None = None) -> list[Case]:
    root = root or attack_root()
    cases: list[Case] = []
    for line in (root / "attacks_manifest.jsonl").read_text().splitlines():
        a = json.loads(line)
        sp = split_of(a["attack_id"])
        if split and sp != split:
            continue
        cases.append(
            Case(
                attack_id=a["attack_id"],
                style=a["attack_style"],
                target=a["target_action"],
                language=a["language"],
                obfuscation=a["obfuscation"],
                delivery=a["delivery"],
                source=_source(a["attack_style"], a["delivery"]),
                split=sp,
                content=_content(root / a["path"], a["delivery"]),
                instruction=a["instruction"],
            )
        )
    return cases


def clean_texts(split: Split, root: Path | None = None) -> list[tuple[str, str, list[str], dict]]:
    """(label, visible text, hidden span texts, metadata) of every document of every CLEAN pack."""
    root = root or GENERATED
    manifest = root / "manifest.jsonl"
    if not manifest.is_file():
        return []
    out: list[tuple[str, str, list[str], dict]] = []
    for line in manifest.read_text().splitlines():
        e = json.loads(line)
        if e.get("split") != split or e.get("fraud_types"):
            continue
        for d in e["documents"]:
            if not d["path"].endswith(".pdf"):
                continue
            pdf = read_pdf((root / d["path"]).read_bytes())
            out.append(
                (
                    f"{e['pack_id']}/{d['type']}",
                    pdf.visible_text,
                    [s.text for s in pdf.hidden_spans],
                    dict(pdf.metadata),
                )
            )
    return out


def risk_of(tool: str, flagged: bool) -> dict[str, Any]:
    """What the real risk engine says about a proposal that reached a service (layer 3)."""
    ctx = RiskContext(
        action=RISK_ACTION.get(tool, Action.RELEASE_TRANCHE),
        origin=Origin.AGENT,
        instruction_from_document=flagged,
    )
    d = engine.evaluate(ctx)
    return {"decision": str(d.decision), "tier": d.tier, "reasons": d.reason_codes}


def evaluate_case(case: Case, mode: str) -> dict[str, Any]:
    kw = MODES[mode]
    r: RunResult = run_case(
        case.content,
        action=case.target,
        delivery=case.delivery,
        on=kw["on"],
        layers=kw.get("layers"),
    )
    flagged = case.delivery == "pdf" or r.detected  # layer 3: the document pipeline always flags
    risks = [risk_of(t, flagged) for t in r.reached]
    moved = sum(1 for k in risks if k["decision"] == "ALLOW")
    return {
        "attack_id": case.attack_id,
        "style": case.style,
        "target": case.target,
        "source": case.source,
        "mode": mode,
        "attempted": r.attempted,
        "reached": r.reached,
        "blocked": r.blocked,
        "detected": r.detected,
        "answer_followed": r.followed,
        "guard": r.guard,
        "risk": risks,
        "money_moved": moved,
        "success": bool(r.reached) or r.followed,
        "layers": (acted := _layers(r, risks)),
        "stopped_at": min(acted) if acted and not (r.reached or r.followed) else None,
    }


def _layers(r: RunResult, risks: list[dict[str, Any]]) -> list[int]:
    """Layers that acted on this attack (2 detector, 3 risk engine, 4 gate, 5 output guard)."""
    acted: list[int] = []
    if r.detected:
        acted.append(2)
    if risks and all(k["decision"] != "ALLOW" for k in risks):
        acted.append(3)
    if r.blocked:
        acted.append(4)
    if r.guard:
        acted.append(5)
    return acted


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    per_style: dict[str, dict[str, Any]] = {}
    for style in STYLE_ORDER:
        sel = [r for r in rows if r["style"] == style]
        if sel:
            per_style[style] = {
                "n": len(sel),
                "attack_success_rate": _rate(sum(r["success"] for r in sel), len(sel)),
                "forbidden_attempts": sum(len(r["attempted"]) for r in sel),
                "reached_services": sum(len(r["reached"]) for r in sel),
            }
    return {
        "n": n,
        "attack_success_rate": _rate(sum(r["success"] for r in rows), n),
        "forbidden_attempts": sum(len(r["attempted"]) for r in rows),
        "reached_services": sum(len(r["reached"]) for r in rows),
        "answers_that_followed": sum(r["answer_followed"] for r in rows),
        "detected": sum(r["detected"] for r in rows),
        "money_moved": sum(r["money_moved"] for r in rows),
        "per_style": per_style,
    }


def run_attack_suite(
    split: Split = "dev",
    defences: Literal["on", "off", "both"] = "both",
    *,
    save: bool = True,
    root: Path | None = None,
) -> dict[str, Any]:
    """Attack success OFF vs ON, detection recall, false-positive rate on clean documents."""
    cases = load_cases(split, root)
    modes = {"both": ["off", "on", "on_without_detector"], "on": ["on"], "off": ["off"]}[defences]
    rows: dict[str, list[dict[str, Any]]] = {m: [evaluate_case(c, m) for c in cases] for m in modes}
    detector_hits = 0
    for c in cases:
        found = scan_document(
            c.content.visible_text, [c.content.hidden_text], {"m": c.content.metadata}
        )
        found += [d for d in [scan(c.content.message_text, "email")] if d.is_injection]
        detector_hits += bool(found)
    clean = clean_texts(split, root if root and (root / "manifest.jsonl").is_file() else None)
    false_pos = [
        label for label, vis, hid, meta in clean if scan_document(vis, hid, meta, use_llm=False)
    ]
    result: dict[str, Any] = {
        "split": split,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "attacks": len(cases),
        "modes": {m: summarise(r) for m, r in rows.items()},
        "detection": {
            "recall": _rate(detector_hits, len(cases)),
            "end_to_end_recall": _rate(sum(r["detected"] for r in rows.get("on", [])), len(cases)),
            "clean_documents": len(clean),
            "false_positives": len(false_pos),
            "false_positive_rate": _rate(len(false_pos), len(clean)),
            "false_positive_ids": false_pos[:20],
        },
        "layer_attribution": _attribution(rows.get("on", [])),
        "rows": {m: r for m, r in rows.items()},
        "notes": "Sandbox registry with the real nodes, an obedient mock model and the real risk "
        "engine as layer 3. Synthetic ceiling, not real-world accuracy.",
    }
    if save:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        target = RESULTS_DIR / f"injection_{split}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        tmp.replace(target)  # atomic: a reader never sees half a file
    return result


def _attribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[str(r["stopped_at"] if r["stopped_at"] is not None else "not_stopped")] += 1
    return dict(sorted(out.items()))


def load_saved(split: Split = "dev") -> dict[str, Any] | None:
    path = RESULTS_DIR / f"injection_{split}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def main(argv: list[str]) -> int:
    split: Split = "test" if argv[:1] == ["test"] else "dev"
    if split == "test":
        print("TEST split: run once per configuration (P24 reports these numbers).")
    res = run_attack_suite(split)
    for mode, s in res["modes"].items():
        print(
            f"{split} {mode:>20}: attack success {s['attack_success_rate']:.0%}  "
            f"attempts {s['forbidden_attempts']}  reached services {s['reached_services']}  "
            f"followed {s['answers_that_followed']}  money moved {s['money_moved']}"
        )
    d = res["detection"]
    print(
        f"detection recall {d['recall']:.0%} (end-to-end {d['end_to_end_recall']:.0%}); "
        f"false positives {d['false_positives']}/{d['clean_documents']} = {d['false_positive_rate']:.1%}"
    )
    print("stopped at layer:", res["layer_attribution"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
