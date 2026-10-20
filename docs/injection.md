# Prompt-injection defence (P19)

Text from documents, e-mails, KB passages or tool results can never make Setu move money, change an
account or change its own behaviour. Code: `backend/app/security/injection/`.

| Layer | Module | What it does | Switchable |
|---|---|---|---|
| 1 Structural separation | `wrap.py` | every untrusted text is wrapped as `<untrusted src=".." id="rand">…</untrusted id="rand">` AFTER Privacy Gateway masking; fixed rule in the system prompt; forged tags neutralised | no |
| 2 Detection | `detector.py` | NFKC, look-alike folding, zero-width removal, spaced letters, base64/URL decoding (scan only); EN/BN/ZH rules; score 0-100, `is_injection` >= 50; optional fast-model second opinion (`INJECTION_LLM_CHECK`, can only raise a borderline score) | yes |
| 3 Capability control | `events.py`, risk engine | agent tools only PROPOSE; a detection linked to a deal writes `injection_events.flags_deal` -> `instruction_from_document` -> Tier 3 for the deal's next money action (release, fund, FX lock, schedule); FRAUD alert; signed audit row | **never** |
| 4 Tool gating | `gating.py` | a money tool needs the router intent to allow it, the user's own words to ask for it once untrusted content was read, and no detection in the turn; dropped calls are logged `INJECTION_BLOCKED_TOOL` | yes |
| 5 Output guard | `guard.py` | removes claims that a payment/account change happened, system-prompt leaks and echoed instructions; adds "This document contains a hidden instruction. Setu ignored it and flagged the deal for extra verification." | yes |
| 6 Toggle | `switch.py` | `INJECTION_DEFENCES=on|off` (or a per-run override) switches layers 2, 4, 5 only; `layer_on(3)` raises | - |

Sources recorded: `hidden_text | visible_text | metadata | email | kb | tool_result`. Document uploads record an
event per placement (pipeline); chat tool results record events through `Nodes.tools`.

## Evaluation (`suite.py`, `harness.py`)
`run_attack_suite(split, defences="both")` runs every P11 attack through the REAL graph nodes with an obedient mock
model and a sandbox registry (propose stubs under the production names; the real risk engine decides what a
proposal that reached a service would have caused). Modes: `off`, `on`, `on_without_detector` (gate + guard only).
Saved to `backend/eval/results/injection_<split>.json`. CLI: `python -m app.security.injection.suite dev`.
The attack set has no split in its manifest: attack n of style s is DEV when `(variant + s)` is even (13 dev / 12 test).
**The test split is for P24; run it once per configuration.**

## Judge-facing
- `/demo/attack-console` (admin/judge): gallery + custom text, Defences ON/OFF, step view privacy -> wrap -> detector ->
  gating -> risk -> answer, highlighted matches, result card, scoreboard. API: `GET /security/injection/gallery`,
  `POST /security/injection/run`, `GET /security/injection/scoreboard`, `POST .../scoreboard/rerun` (dev split only).
- `/app/admin/security`: scoreboard + events (filter by style/source; `audit_seq` per row; admin can resolve).
- Document viewer reveal: `GET /documents/{id}/hidden-text` now returns `injection` (rules, highlights).
- Chat: `ChatResponse.security` (also `meta.security` in history) -> "Security check" chip.

## Gaps
- Layer 1 cannot be shown to bind a real model; the obedient mock ignores delimiters by construction. Numbers are a
  synthetic ceiling.
- The harness uses stubs for the propose tools (no DB); DB-backed layer 3 is covered by `tests/injection/test_integration.py`.
- Console runs record events with origin `console` and never touch a deal.
- An admin resolving an event releases only that event's flag; the forensic INSTRUCTION_SCAN flag on the document stays.
- Streaming: when a turn read untrusted tools or was flagged, tokens are held back (`nostream`) so the guard sees the whole answer; otherwise tokens stream raw and the final event carries the guarded text.
