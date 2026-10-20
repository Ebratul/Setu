# Setu — Security Self-Assessment (v1)

FinTechathon 2026 International Track, Topic E. Prepared by the Setu team. [TO FILL: team name]

**Scope.** The Setu web app (`frontend`) and API/agent service (`backend`), as of the P22 handoff in
`docs/PROGRESS.md`. **All money movement is simulated. No real payment rails, no real SMS provider, no real
lender.** No model was trained. This is a self-assessment: it was written by the team, and the project's
`security-reviewer` agent reviewed most phases (results below). There has been no external penetration test.

Requirement IDs come from `docs/REQUIREMENTS.md` (there is no `docs/SRS.md`).

## 1. Permission tiers: how they are enforced in code

Tiers are decided by code, never by a prompt.

| Tier | Meaning | Trigger examples (from `docs/risk.md`) | Who executes |
|---|---|---|---|
| 0 | Auto. Analysis, read-only checks, and "propose" tools | non-money actions | the agent (LLM-callable) |
| 1 | Auto + notice | release to a verified, unchanged beneficiary with all checks passing and amount not above USD 20,000 | system, raises an INFO alert |
| 2 | One-tap human approval | first deal with a supplier, document WARNING, FX rate not locked, lock FX, confirm/propose milestones, agent origin | a person, via the UI/HTTP endpoint |
| 3 | Human approval + cooling-off + OTP | amount above USD 20,000, advance above limit, beneficiary change or recent change, fraud score above 60, duplicate hash, instruction found in a document, KYB account warning | a person, via the UI/HTTP endpoint |
| BLOCK | refused | sanctions hit, KYB blocked, beneficiary blocked/retired, document FAILED (release) | nobody |

Highest tier wins; BLOCK beats every tier.

### Code references (each path and symbol was checked to exist with grep)

| Function | Where |
|---|---|
| Tier enum and LLM ceiling `MAX_LLM_TOOL_TIER = Tier.T0` | `backend/app/security/tiers.py` |
| Tool registry; `ToolSpec.max_tier`; `llm_tools()` offers only allow-listed tools at or below the ceiling; `guard()` refuses `max_tier > MAX_LLM_TOOL_TIER` with `requires_approval_flow` before validation | `backend/app/agent/registry.py` |
| Risk engine `evaluate(ctx, policy)` (pure), `context_hash`, `rules_table` | `backend/app/services/risk/engine.py` |
| Thresholds | `backend/config/risk.yaml`, loaded by `backend/app/security/policy.py` |
| Gate used by fund, propose/confirm schedule, FX lock, beneficiary change: `run_gate` | `backend/app/services/risk/gate.py` |
| Enforcement inside services: `release_tranche`, `fund_escrow` | `backend/app/services/escrow.py` |
| `lock_fx`, `change_beneficiary` | `backend/app/services/fx_lock.py`, `backend/app/services/beneficiary.py` |
| Approval binding hash over action, tier, deal, milestone, account, params: `approval_binding_hash` | `backend/app/security/approvals.py` |
| Approve, reject, cancel, expiry, re-escalation: `approve` | `backend/app/services/approvals.py` |
| OTP (`hash_code`, `code_matches`, `cooling_off_until`, `issue_otp`) | `backend/app/services/approval_otp.py` |
| Agent-side propose-only tools (`propose_release_tranche`, `propose_fx_lock`, ...) | `backend/app/agent/tools/escrow.py` |

### Tests that prove the boundary

| Claim | Test |
|---|---|
| A Tier 2 tool is refused and never executes; Tier 2 tools are not offered to the model | `tests/agent/test_graph.py::test_tier2_tool_is_refused_and_never_executes`, `::test_tier2_tools_are_not_offered_to_the_model` |
| Every registered tool is Tier 0 and money tools are propose-only | `tests/agent/test_graph.py::test_every_registered_tool_is_tier0_and_money_tools_are_propose_only` |
| The guard refuses any tier above zero, and checks tier before allow-list | `tests/agent/test_router_and_tools.py::test_guard_refuses_any_tier_above_zero`, `::test_tier_check_runs_before_allowlist` |
| Propose arguments cannot carry a tier or an approval | `tests/agent/test_escrow_tools.py::test_propose_arguments_cannot_smuggle_a_tier_or_approval` |
| Engine rules, enforcement at each service | `tests/risk/test_engine.py`, `tests/api/test_risk_enforcement.py`, `tests/api/test_risk_api.py` |
| Approval lifecycle, OTP, cooling-off | `tests/api/test_approvals.py` |
| Escrow release order and idempotency | `tests/api/test_escrow_release.py`, `tests/api/test_escrow_hardening.py` |

Last recorded full run: pytest 1,240 passed (P20 handoff; needs a local pgvector database). A later run is not
recorded in `docs/PROGRESS.md`.

## 2. Controls table (SR-1 to SR-9)

| ID | Requirement (short) | Status | Implementation | Evidence |
|---|---|---|---|---|
| SR-1 | Tiers enforced in code | Implemented, with one deviation | Section 1. Fraud-score trigger is "> 60" in code; SR-1 says "threshold or above" (see risk R9). | tests above; `docs/risk.md` |
| SR-2 | LLM explains, code executes | Implemented | `MAX_LLM_TOOL_TIER`, `guard()`; money tools only create requests; approve body is `{otp?}` only (`extra=forbid`); unknown tool names refused | tests above |
| SR-3 | Prompt-injection defence | Implemented (layers 1 to 5), evasions known | `app/security/injection/` (`wrap.py`, `detector.py`, `events.py`, `gating.py`, `guard.py`, `switch.py`); hidden text and metadata are never used as content | `docs/injection.md`; dev: attack success OFF 100% → ON 0% (13 attacks), recall 100%, false positives 0/300, money moved 0 (`eval/results/injection_dev.json`); live `/demo/attack-console` |
| SR-4 | Privacy Gateway | Implemented in nodes and `structured_call`, not in one client wrapper | `app/privacy/` (`detectors.py`, `vault.py`, `gateway.py`); `gateway.protect()` before every model call; payload re-scan blocks the call if an identifier survives; tool runs carry no raw values to LangSmith | `docs/privacy.md`; dev: masking ON 0 detectable identifiers in payload, 1/600 ground-truth leaked (company name equal to holder), OFF 600/600; `/demo/privacy-playground`, "Privacy X-ray" on messages |
| SR-5 | Signed hash-chained audit log, verify endpoint, JSONL export | Implemented | `app/audit/` (`scheme.py`, `writer.py` with `write_audit`, `verify.py`, `export.py`, `tamper.py`, `middleware.py`); Ed25519; DB trigger blocks UPDATE/DELETE | `docs/audit.md`; `tests/audit/` (163 tests at P20); CLI check of a 493-entry export; `docs/submission/EXECUTION_EVIDENCE.md` |
| SR-6 | Duplicate-financing registry across lenders | Implemented (simulated lenders) | `app/services/hash_registry.py` (`evaluate`, `check`), table `hash_registry`; Tier 3 on duplicate; financing gate returns 409 `INVOICE_ALREADY_FINANCED` | `docs/registry.md`; dev catch rate exact 3/3, near 2/2; `tests/registry/` |
| SR-7 | Secrets only in env vars | Implemented | `app/config.py` uses `SecretStr`; `.env*` blocked by repo hooks; audit signing key from `AUDIT_SIGNING_KEY` or a git-ignored key file (mode 0600, directory 0700); production start guard refuses weak or missing session secret | `docs/PROGRESS.md` 2.1, 1.1 |
| SR-8 | Sandbox only; "Simulated" label | Implemented | No payment integration exists; `simulated: true` on responses; "Simulated" badge in the UI; ledger entries are internal | UI, `docs/escrow.md` |
| SR-9 | Step-up OTP + 10-minute cooling-off, server-side by timestamp, cancellable | Implemented, OTP simulated | `approval_otp.py`, `approvals.py::approve`: cooling-off first (no attempt consumed before it ends), 6-digit HMAC OTP, 5 min life, 3 wrong codes lock; default cooling-off 600 s (30 s in demos by config) | `docs/approvals.md`; `tests/api/test_approvals.py`; Playwright `approvals.spec.ts` 5/5 at P17 |

## 3. Other defences

- **Document handling.** Magic-byte file typing, 10 MB cap enforced while reading, sanitised names, storage keyed
  by SHA-256, signed short-lived URLs tied to the user, PDF parsing in a resource-limited child process.
- **Beneficiary change.** In-app only. E-mail never changes an account; `POST /inbox/email-check` blocks and logs it
  (`app/security/email_guard.py`, `app/services/supplier_accounts.py`).
- **Access control.** Roles BUYER, SUPPLIER, ADMIN, JUDGE with scoped reads; other users' objects return 404 or 403;
  suppliers receive a projection without buyer-private fields.
- **Judge sandboxes.** One Postgres schema per judge, signed cookie, 4-hour TTL, cap of 40 sandboxes, rate limits,
  live-AI budget of 25 calls (`app/demo/sandbox.py`, `app/db/tenancy.py`).
- **Cost control.** Thread token budget, tool-step cap, replay fixtures for the guided demo.

## 4. Review history

Each phase that touched security code was reviewed by the `security-reviewer` agent. Outcomes recorded in
`docs/PROGRESS.md`: most "pass with fixes, all fixed". P15 (registry) and P21 (guided demo/sandboxes) were
**BLOCK, then fixed**. The review was by the team's own tooling, not by an independent party.

## 5. Known-risk list

Built from the "Not fixed" and "Known gaps" bullets in `docs/PROGRESS.md`. Likelihood/impact are the team's
judgement for a competition demo; they are not measured.

| # | Risk | Source | Likelihood / impact | Mitigation now | Future work |
|---|---|---|---|---|---|
| R1 | No real authentication: demo login by role, HMAC cookie; logout is client-side only (cookie valid up to 12 h) | 2.1 | High (by design) / low in sandbox | Sandbox isolation, scoped reads, production start guard | Real auth, server-side session revocation |
| R2 | OTP is a simulated SMS panel (`DEMO_MODE`); no supplier-side OTP | 5.2 | High (by design) / low | Panel exists only with `DEMO_MODE=true` and not in prod mode | SMS provider, supplier-side step-up |
| R3 | Injection detector evasions not covered: MIME or double base64, HTML entities, leetspeak, polite paraphrase, text past 60k chars | 5.4 | Medium / medium | Layer 3 (capability control) and tool gating do not depend on the detector; gate + guard alone gave 0% attack success on dev | Classifier model, broader normalisation |
| R4 | Streaming sends raw tokens on turns with no untrusted tool; final event carries the guarded text | 5.4 | Low / low | Tokens held back on risky turns | Hold back all tokens |
| R5 | Negation suppresses money-claim detection anywhere in the sentence | 5.4 | Low / low | Money cannot move without a human | Sentence-level negation handling |
| R6 | Blocked-tool event flags only the chat's focus deal | 5.4 | Low / medium | Detection also raises deal flags on document upload | Flag all deals in scope |
| R7 | Injection evaluation is a synthetic ceiling; obedient mock ignores delimiters, so layer 1 is not measured; test split not run | 5.4 | n/a / high for claims | Reported as "dev split, synthetic" | P24 test split, run with a real model |
| R8 | Privacy gaps: masking in nodes and `structured_call`, not one client wrapper; tokens from earlier turns cannot be restored (`[protected X]`); unlabelled long digit strings in chat not masked; company names not masked; regex-based | 5.3 | Medium / medium | Payload re-scan blocks calls with surviving identifiers; LangSmith tool runs carry no raw values | Move masking into `client.py`; classifier-assisted detection |
| R9 | Fraud-score trigger uses "> 60", SR-1 says "0.6 or more" (threshold boundary) | 5.1 | Low / low | Documented in `docs/risk.md` | Align with the SRS once available |
| R10 | Audit table owner can TRUNCATE or `DISABLE TRIGGER` | 5.5 | Medium / high in production | Public-key verification detects edits; demo reset is logged | Non-owner application DB role in production |
| R11 | Tail truncation of an export is undetectable without a live head or a receipt; a deal-filtered export has gaps by construction | 5.5, 1.1 | Medium / medium | `/api/audit/summary` shows the live head; receipts carry seq and hash | Signed chain-head anchor |
| R12 | Credit records and sandbox audit chains share the production signing key (no environment tag) | 6.2 | Medium / medium | Sandboxes are separate schemas | Environment-tagged keys |
| R13 | Rate limits are in-memory per instance; the runner pool is shared (8 workers); a timed-out demo scene keeps running | 6.2 | Medium / low | Per-sandbox and per-IP limits, live-AI budget | Shared limiter (Redis), cancel on timeout |
| R14 | `APP_ENV=prod` requires `DEMO_MODE=false`, which disables the scam simulator and simulated SMS used by the demo | 6.2 | n/a / medium | Judge deployment runs with `APP_ENV=dev/test` and `DEMO_MODE=true` (see `docs/demo.md`) | Separate "judge" mode with safe defaults |
| R15 | Registry: release on COMPLETED lets a finished deal's invoice or B/L be reused (reviewer rated High, accepted by the brief); no repayment flow; no rate limit on the lender-check file endpoint; judge checks write counters/alerts; downgrade drops evidence rows | 4.4 | Medium / medium | Fingerprints remain; entries are kept as RELEASED | Repayment flow, rate limit, retain history |
| R16 | Documents: photo width not checked (colour only); overlay covers page 1; covered/low-contrast detection assumes opaque fills; CID-font render-mode-3 text unreadable; no OCR for scanned PDFs; a rejected document keeps its tranche blocked until an admin acts; S3 storage is a stub | 4.3 | Medium / medium | Hidden-text reported, never used | OCR/vision, admin override endpoint |
| R17 | Any open Tier 3 request from a buyer freezes only that buyer's releases (fixed); agent proposal parks a clean tranche in PENDING_APPROVAL until cancelled | 5.1 | Medium / low | Request can be cancelled | Auto-expire agent proposals |
| R18 | Alert and cash-flow description fields flow into alert text; treat as untrusted before free-text sources exist; concurrent recomputes can collide (500) | 2.3 | Low / low | Alert text uses code labels | `ON CONFLICT`, sanitising |
| R19 | Financing: idempotency check not atomic under concurrency; option currency not compared in `code_rules`; `ACCEPT_FINANCING` approvals not executable through the approvals endpoint | 2.2, 5.2 | Low / medium | Execution-time eligibility re-check, row lock | Partial unique index; route acceptance through approvals |
| R20 | Accepted design: another buyer's deal ref returns 403 (references enumerable); scorecard averages are network-wide; upload of identical bytes on another deal historically revealed existence (now handled by the registry) | 2.1, 4.3 | Low / low | n/a | Return 404; minimum-count floor |
| R21 | Knowledge-base content (Bangladesh Bank figures) is not independently verified; no domain-expert review | 3.2 | Medium / medium | Marked "simplified summary for demo — verify with the official circular" | Expert review |
| R22 | Bangla and Chinese text not reviewed by native speakers | 5.2, 6.3 | High / low | Key parity enforced by `i18n:check` | Native review |
| R23 | Accessibility: no CI axe run, no manual keyboard-only or screen-reader pass; `/app` mobile performance about 77 | 6.3 | Medium / low | Manual axe sweep on main routes: no outstanding serious issue except the one fixed | CI axe, keyboard and screen-reader tests |
| R24 | Not verified in a browser or at run time: audit chain page, tamper panel, drawer, receipt dialog/PNG/print; QR (about 1,000 characters) not scanned; several Playwright specs not run or failing in the P22 run (`approvals`, `chat`, `deals`), possibly backend state | 5.5, 6.3 | Medium / medium | `/verify` and CLI are tested | Re-run all specs against a clean stack |
| R25 | Third-party licences: `@axe-core/playwright` is MPL-2.0 (dev only); `psycopg` is LGPL-3.0 (unmodified dependency); `favicon.ico` licence unverified | 5.5, 6.3 | Low / low | Listed in README | Replace favicon |
| R26 | Single signing key and no key rotation procedure in use; committed public key's fingerprint is from the local dev key, so the host key must match | 5.5 | Medium / high for evidence | `keygen` refuses to overwrite; exits non-zero if the committed PEM does not match | Rotation procedure, key per environment |
| R27 | LLM extraction errors can fill missing document fields; a model-filled required field forces at least WARNING | 4.3 | Low / medium | Deterministic parser first; model output validated field by field | Human confirmation step |
| R28 | Hosted cold starts and serverless limits (Vercel) may slow chat; a turn takes 8 to 15 s with a tool round trip and about 8k to 15k tokens | 3.1b | Medium / low | Replay fixtures for the guided demo | Warm instances |

## 6. What this assessment does not claim

- No claim of real-world fraud-detection accuracy. The numbers are dev-split, synthetic.
- No test-split numbers exist yet.
- No claim of compliance with any regulation. Bangladesh Bank summaries in the knowledge base are unverified.
- No on-chain anchoring and no real lender integration.
