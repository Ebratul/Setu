# Risk-tier engine (SR-1, SR-2, Phase 5.1 / P16)

Decided by code, not by AI. `app/services/risk/engine.py` is pure (no DB, clock, LLM). Thresholds live in
`services/agent/config/risk.yaml`, loaded by `app/security/policy.py`.

## Rules (highest tier wins; BLOCK beats every tier)
| Kind | Rule | Applies to |
|---|---|---|
| BLOCK | SANCTIONS_HIT, KYB_BLOCKED, BENEFICIARY_BLOCKED (BLOCKED/RETIRED), DOCUMENT_FAILED | all money actions (DOCUMENT_FAILED: release) |
| Tier 3 | AMOUNT_OVER_LIMIT (> USD 20,000 strict, unrounded), ADVANCE_OVER_LIMIT, BENEFICIARY_CHANGE, BENEFICIARY_PENDING_CHANGE, BENEFICIARY_CHANGED_RECENTLY (< 30 days), FRAUD_SCORE_HIGH (> 60), DUPLICATE_HASH, DOC_INSTRUCTION, KYB_ACCOUNT_WARNING | release (change-beneficiary: the beneficiary ones) |
| Tier 2 | FIRST_DEAL, DOCUMENT_WARNING, FX_RATE_NOT_LOCKED, NOT_FULLY_VERIFIED (fail closed), LOCK_FX, CONFIRM_MILESTONES, PROPOSE_MILESTONES, AGENT_ORIGIN | per rule |
| Tier 1 | none fired: auto + INFO alert "Released USD X to <supplier>" | release |
| Tier 0 | non-money (`ANALYSIS`) | |

FUND_ESCROW moves the buyer's own cash into escrow, so only BLOCK rules and AGENT_ORIGIN apply (supplier-bound rules apply at release).

## Enforcement points (all inside the service, after loading facts from the DB)
`escrow.release_tranche`, `escrow.fund_escrow`, `deals.propose_milestones`, `deals.confirm_milestones`, `fx_lock.lock_fx`, `beneficiary.change_beneficiary`.
- REQUIRE_APPROVAL -> `ApprovalRequest` (tier, reasons, params + binding hash, OTP + 10-min cooling-off for Tier 3); identical open requests are reused (idempotent, deal row locked). Release also sets the milestone PENDING_APPROVAL.
- BLOCK -> 409 `RELEASE_BLOCKED` / `RISK_BLOCKED`, FRAUD alert, audit.
- Decision design: a person's own click on `inline_tier2_actions` (confirm, propose schedule, lock FX) *is* the one-tap and runs inline, still recorded as a Tier 2 decision. The agent (`origin=AGENT`) only ever gets an ApprovalRequest. Releases, deposits and account changes always go through ApprovalRequest at Tier 2/3.
- `approval_id` (Python-level, for the P17 human endpoint) is refused unless origin is USER_UI; it must be APPROVED, bound to identical params, not stale in tier, past cooling-off.
- Request bodies for release/fund/confirm/propose/fx-lock/beneficiary use `ActionIn` (unknown fields such as `tier`/`approved` are dropped).
- Agent: `propose_release_tranche|milestones|confirm_milestones|fund_escrow|fx_lock|change_beneficiary` (Tier 0, only queue requests).
- Every decision: `risk_events` row (readable, with rule trace + hints) and a signed `RISK_DECISION` audit row.

## Endpoints
`POST /deals/{id}/fx-lock`, `POST /deals/{id}/beneficiary`, `POST /risk/evaluate` (dry run, nothing saved), `GET /risk/policy`, `GET /risk/overview` (admin/judge).
Web: `/demo/risk-playground`, `/app/admin/risk`, `RiskDecisionCard` on the deal release dialog.
Migration `e8b4c1d7a2f6`: `risk_events`, approval actions FUND_ESCROW / CONFIRM_MILESTONES.
