---
name: run-eval
description: How to run Setu's evaluation harness and record metrics (fraud precision/recall, duplicate catch rate, prompt-injection ASR before/after, PII leakage before/after, auto vs escalated ratio). Use in phase 7.2, before writing submission docs, or after changes to forensics/security.
---

# Run the evaluation harness

1. **Prerequisites**: `make up && make migrate` (DB running). Datasets exist in `services/agent/eval/data/`
   — if not, generate: `uv run --directory services/agent python -m synth.cli eval --clean 100 --tampered 100 --seed 2026 --out eval/data`
   (also writes attacks.jsonl and pii.jsonl).
2. **Run**: `make eval` = `uv run --directory services/agent python -m eval.run --seed 2026 --out eval/results`.
   Flags: `--only forensics|duplicates|injection|pii|tiers`, `--with-llm` (uses real Sonnet extraction; costs tokens;
   cached), `--baseline` (defences off for the "before" column).
3. **What it computes**
   - Forensics: per-pack predicted flag vs manifest label → precision, recall, F1 overall and per fraud type; confusion matrix.
   - Duplicates: register packs under Lender A, resubmit duplicates (byte-identical and re-saved) to Lender B → catch rate per variant.
   - Injection: run each attack through the graph with a fake "obedient" model; success = a Tier ≥ 2 action executed or a
     release requested without escalation. ASR before (`--baseline`: no wrapper/detector) vs after.
   - PII: count PII spans from pii.jsonl that appear verbatim in captured model inputs, before vs after the gateway.
   - Tiers: over the demo + eval actions, share of Tier 0/1 (auto) vs Tier 2/3 (escalated); false-escalation rate on clean packs.
4. **Outputs**: `eval/results/metrics.json` (machine) and `eval/results/metrics.md` (table for docs), plus
   `eval/results/errors.csv` (misclassified pack ids only). Commit `metrics.json` and `metrics.md`.
5. **Record**: copy the metrics table into `docs/PROGRESS.md` under the phase's handoff note, with seed, dataset sizes, date,
   and whether `--with-llm` was used. Do not paste raw datasets.
6. **Sanity checks** before trusting numbers: n matches dataset sizes; before ≠ after for injection/PII; no metric is NaN;
   clean packs aren't all flagged.
