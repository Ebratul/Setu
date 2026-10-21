# Setu — Security Self-Assessment (v2)

FinTechathon 2026 International Track, Topic E. Prepared by the Setu team. [TO FILL: team name]

**Scope.** The Setu web app (`frontend`), the API service (`backend`) and the agent and RAG code (`rag_agent`, which
runs inside the backend process), as of branch `feature/paypal-sandbox-escrow` (includes the P24 authentication,
onboarding and PayPal Sandbox work). **All money movement is simulated. No real payment rails, no real SMS provider,
no real lender.** The only external payment system is the optional PayPal **Sandbox** (test mode, off by default,
section 3). No model was trained. This is a self-assessment: it was written by the team, and the project's
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
| Tool registry; `ToolSpec.max_tier`; `llm_tools()` offers only allow-listed tools at or below the ceiling; `guard()` refuses `max_tier > MAX_LLM_TOOL_TIER` with `requires_approval_flow` before validation | `rag_agent/app/agent/registry.py` |
| Risk engine `evaluate(ctx, policy)` (pure), `context_hash`, `rules_table` | `backend/app/services/risk/engine.py` |
| Thresholds | `backend/config/risk.yaml`, loaded by `backend/app/security/policy.py` |
| Gate used by fund, propose/confirm schedule, FX lock, beneficiary change: `run_gate` | `backend/app/services/risk/gate.py` |
| Enforcement inside services: `release_tranche`, `fund_escrow` | `backend/app/services/escrow.py` |
| `lock_fx`, `change_beneficiary` | `backend/app/services/fx_lock.py`, `backend/app/services/beneficiary.py` |
| Approval binding hash over action, tier, deal, milestone, account, params: `approval_binding_hash` | `backend/app/security/approvals.py` |
| Approve, reject, cancel, expiry, re-escalation: `approve`, `reject`, `cancel`, `expire_due`; four-eyes check `_four_eyes` | `backend/app/services/approvals.py` |
| OTP (`hash_code`, `code_matches`, `cooling_off_until`, `issue_otp`); cooling-off floor 600 s in prod (`COOLING_OFF_FLOOR_PROD`) | `backend/app/services/approval_otp.py` |
| Human approve endpoint `POST /approvals/{id}/approve` (body `{otp?}` only) | `backend/app/api/approvals.py` |
| E-mail step-up (`start`, `verify`, `require`; signed `X-Stepup` token) | `backend/app/services/stepup.py` |
| Neon Auth JWT verification; `current_user` status checks | `backend/app/auth/neon.py`, `backend/app/auth/deps.py` |
| Production start guard `check_prod_settings` | `backend/app/main.py`, `backend/tests/test_prod_guard.py` |
| Agent-side propose-only tools (`propose_release_tranche`, `propose_fx_lock`, ...) | `rag_agent/app/agent/tools/escrow.py` |

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

Last recorded full runs in `docs/PROGRESS.md` (not re-run for this document): pytest 1,313 passed with 23 registry
tests failing when no migrated database is available (P23); Vitest 433 passed (P23). Authentication, onboarding and
payments tests (`backend/tests/auth`, `onboarding`, `payments`) were added after that and no full-suite result for them is
recorded.

## Measured evidence (test split, synthetic)

From `backend/eval/results/metrics.json` (generated 2026-10-20, harness `backend/eval/run.py`; thresholds tuned on the
dev split only). **These are ceilings on synthetic data, not real-world accuracy.**

| Control | Measure | Result |
|---|---|---|
| SR-3 injection defences | Attack success rate, 12 test attacks, obedient mock model | defences off 100%, on 0%, on without the detector 0% |
| SR-3 detector | Recall / false positives | recall 100% (12/12, all caught at layer 2); false positives 0 / 300 clean documents |
| SR-1, SR-2 money safety | Money moved by any injection attack | 0 in all three modes |
| SR-4 Privacy Gateway | Ground-truth bank identifiers present in the model payload, 600 documents | masking off 600, on 0 |
| SR-4 | Identifiers the detector finds in the payload | off 2,491, on 0; extracted-field accuracy 1200/1200 in both modes (masking did not break extraction) |
| SR-1 tiers | Tampered packs auto-released (USD 3,000 release, 50 tampered packs) | 0 (27 escalated to Tier 2/3, 23 blocked) |
| SR-1 tiers | Clean packs wrongly escalated or blocked (50 clean packs) | 0 (all 50 auto at Tier 0/1) |
| SR-6 registry | Duplicate documents caught | 5/5 (exact 2/2, near 3/3) |
| FR-6 forensics | Flagged (WARN or FAIL), 100 packs | precision 1.0, recall 1.0; 0/50 clean packs flagged; 50/50 tampered packs have an unpassed document |
| FR-6 forensics | FAIL only | precision 1.0, recall 0.9508 (3 subtle name variants are WARN by design) |

Limits of this evidence: the injection harness replaces the model with an obedient mock and cannot show that
layer 1 (delimiters) binds a real model; "money moved 0" is also 0 with defences off because money moves only through a
human endpoint, so the informative number is the attack success rate (forbidden tool call attempted and reaching a
service); the tier row is one scenario; no LLM extraction was used in this run. Tests that back the same claims are
listed in section 1.

## 2. Controls table (SR-1 to SR-9)

| ID | Requirement (short) | Status | Implementation | Evidence |
|---|---|---|---|---|
| SR-1 | Tiers enforced in code | Implemented, with one deviation | Section 1. Fraud-score trigger is "> 60" in code; SR-1 says "threshold or above" (see risk R9). | tests above; `docs/risk.md` |
| SR-2 | LLM explains, code executes | Implemented | `MAX_LLM_TOOL_TIER`, `guard()`; money tools only create requests; approve body is `{otp?}` only (`extra=forbid`); unknown tool names refused | tests above |
| SR-3 | Prompt-injection defence | Implemented (layers 1 to 5), evasions known | `backend/app/security/injection/` (`wrap.py`, `detector.py`, `events.py`, `gating.py`, `guard.py`, `switch.py`); hidden text and metadata are never used as content | `docs/injection.md`; test split: attack success OFF 100% → ON 0% (12 attacks), recall 100%, false positives 0/300, money moved 0 (`backend/eval/results/injection_test.json`; dev run in `injection_dev.json`); live `/demo/attack-console` |
| SR-4 | Privacy Gateway | Implemented in nodes and `structured_call`, not in one client wrapper | `backend/app/privacy/` (`detectors.py`, `vault.py`, `gateway.py`); `gateway.protect()` before every model call; payload re-scan blocks the call if an identifier survives; tool runs carry no raw values to LangSmith | `docs/privacy.md`; test split: ground-truth identifiers leaked OFF 600/600 → ON 0/600, detectable identifiers in payload 0 (dev run had 1/600, a company name equal to the holder); `/demo/privacy-playground`, "Privacy X-ray" on messages |
| SR-5 | Signed hash-chained audit log, verify endpoint, JSONL export | Implemented | `backend/app/audit/` (`scheme.py`, `writer.py` with `write_audit`, `verify.py`, `export.py`, `tamper.py`, `middleware.py`); Ed25519; DB trigger blocks UPDATE/DELETE | `docs/audit.md`; `tests/audit/` (163 tests at P20); CLI check of a 493-entry export; `docs/submission/EXECUTION_EVIDENCE.md` |
| SR-6 | Duplicate-financing registry across lenders | Implemented (simulated lenders) | `backend/app/services/hash_registry.py` (`evaluate`, `check`), table `hash_registry`; Tier 3 on duplicate; financing gate returns 409 `INVOICE_ALREADY_FINANCED` | `docs/registry.md`; test catch rate 5/5 (exact 2/2, near 3/3); `tests/registry/` |
| SR-7 | Secrets only in env vars | Implemented | `backend/app/config.py` uses `SecretStr`; `.env*` blocked by repo hooks; audit signing key from `AUDIT_SIGNING_KEY` or a git-ignored key file (mode 0600, directory 0700); production start guard refuses weak or missing session secret | `docs/PROGRESS.md` 2.1, 1.1 |
| SR-8 | Sandbox only; "Simulated" label | Implemented, with one test-mode integration | The escrow and ledger are internal and simulated. The only external payment code is the PayPal **Sandbox** adapter (`backend/app/services/payments/paypal_sandbox.py`, API host fixed to `api-m.sandbox.paypal.com`, off unless `PAYPAL_SANDBOX_ENABLED=true`, DB CHECK `simulated`). "Simulated" badge in the UI | `docs/escrow.md`, `docs/paypal-sandbox.md`, `backend/tests/payments/` |
| SR-9 | Step-up OTP + 10-minute cooling-off, server-side by timestamp, cancellable | Implemented, OTP simulated | `backend/app/services/approval_otp.py`, `backend/app/services/approvals.py::approve`: cooling-off first (no attempt consumed before it ends), 6-digit HMAC OTP, 5 min life, 3 wrong codes lock; default cooling-off 600 s (30 s in demos by config) | `docs/approvals.md`; `tests/api/test_approvals.py`; Playwright `approvals.spec.ts` 5/5 at P17 |

## 3. Other defences

- **Document handling.** Magic-byte file typing, 10 MB cap enforced while reading, sanitised names, storage keyed
  by SHA-256, signed short-lived URLs tied to the user, PDF parsing in a resource-limited child process.
- **Beneficiary change.** In-app only. E-mail never changes an account; `POST /inbox/email-check` blocks and logs it
  (`backend/app/security/email_guard.py`, `backend/app/services/supplier_accounts.py`).
- **Access control.** Roles BUYER, SUPPLIER, ADMIN, JUDGE with scoped reads; other users' objects return 404 or 403;
  suppliers receive a projection without buyer-private fields.
- **Judge sandboxes.** One Postgres schema per judge, signed cookie, 4-hour TTL, cap of 40 sandboxes, rate limits,
  live-AI budget of 25 calls (`backend/app/demo/sandbox.py`, `backend/app/db/tenancy.py`).
- **Authentication (`AUTH_MODE=neon`).** Neon Auth JWT, EdDSA only, JWKS/issuer/audience/expiry checked; verified e-mail,
  onboarded and `ACTIVE` account required; role and party come from our database, never the token; fails closed if JWKS is
  unreachable (`docs/auth.md`). Mandatory when `APP_ENV=prod`.
- **Onboarding KYB gate.** A new company is `PENDING` until automatic checks (`backend/app/domain/onboarding_kyb.py`, no LLM)
  and an admin approve it; an admin cannot decide their own review; a sanctions hit never auto-approves.
- **Four-eyes and step-up.** The person who created an approval cannot approve it when another approver exists
  (`FOUR_EYES_ENFORCE`); admin decisions, Tier 2 approvals and member changes need an e-mail step-up code.
- **PayPal Sandbox.** Amount derived on the server; ownership enforced (others get 404); idempotency keys; webhook
  signature verified before the body is read; the payment funds escrow only through the unchanged risk gate; a webhook
  cannot post to the ledger.
- **Cost control.** Thread token budget, tool-step cap, replay fixtures for the guided demo.

## 4. Review history

Each phase up to P23 that touched security code was reviewed by the `security-reviewer` agent. Outcomes recorded in
`docs/PROGRESS.md`: most "pass with fixes, all fixed". P15 (registry) and P21 (guided demo/sandboxes) were
**BLOCK, then fixed**. The review was by the team's own tooling, not by an independent party. **The P24 authentication, onboarding, step-up and PayPal Sandbox changes have no recorded `security-reviewer` result in `docs/PROGRESS.md`.**

## 5. Known-risk list

Built from the "Not fixed" and "Known gaps" bullets in `docs/PROGRESS.md`. Likelihood/impact are the team's
judgement for a competition demo; they are not measured.

| # | Risk | Source | Likelihood / impact | Mitigation now | Future work |
|---|---|---|---|---|---|
| R1 | The judge deployment uses demo login by role (HMAC cookie, logout client-side only, valid up to 12 h). Real authentication exists (`AUTH_MODE=neon`) but is not what judges use, and has no recorded security review or external test | 2.1, P24 | High (by design) / low in sandbox | Sandbox isolation, scoped reads, production start guard requires neon mode in prod | Security review of auth, server-side session revocation for demo mode |
| R2 | OTP is a simulated SMS panel in demo mode; in neon mode it is an e-mail code (proves mailbox control, not a device); no SMS provider; no supplier-side OTP | 5.2, P24 | High (by design) / low | Panel exists only with `DEMO_MODE=true` and not in prod mode; e-mail code stored as HMAC, 3 tries, never in API/audit/log; four-eyes | SMS or authenticator factor, supplier-side step-up |
| R3 | Injection detector evasions not covered: MIME or double base64, HTML entities, leetspeak, polite paraphrase, text past 60k chars | 5.4 | Medium / medium | Layer 3 (capability control) and tool gating do not depend on the detector; gate + guard alone gave 0% attack success on dev | Classifier model, broader normalisation |
| R4 | Streaming sends raw tokens on turns with no untrusted tool; final event carries the guarded text | 5.4 | Low / low | Tokens held back on risky turns | Hold back all tokens |
| R5 | Negation suppresses money-claim detection anywhere in the sentence | 5.4 | Low / low | Money cannot move without a human | Sentence-level negation handling |
| R6 | Blocked-tool event flags only the chat's focus deal | 5.4 | Low / medium | Detection also raises deal flags on document upload | Flag all deals in scope |
| R7 | Injection evaluation is a synthetic ceiling; obedient mock ignores delimiters, so layer 1 is not measured. Test split now run once (0% with defences on, n = 12): a small sample | 5.4, P24 | n/a / high for claims | Reported as "synthetic, test split, n = 12" | Larger and adaptive attack set, run with a real model |
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
| R29 | PayPal Sandbox adapter: a third-party service in the payment path (test mode only); depends on PayPal availability and a configured webhook; a refund after funding only raises a `NEEDS_REVIEW` audit entry and does not reverse the simulated escrow; no security review recorded | P24 | Low / low (no real money) | Off by default; fixed Sandbox host; server-derived amount; signature-verified, de-duplicated webhooks; risk gate unchanged | Review; reconcile refunds with the ledger |
| R30 | `backend/eval/run.py` and its results are not yet committed at the time of writing, and the harness is not run in CI | P24 | Low / medium for claims | Commands and result files documented | Commit; run in CI |

## 5b. Residual risks (after the mitigations above)

These are the risks the team would still carry into a real pilot. They are the team's judgement.

1. **Evidence is synthetic and small.** Perfect scores on 100 test packs and 12 attacks come from a generator and checks
   built by the same team, with a mock model in the injection test. Real documents, scanned PDFs and a real model could
   behave differently (R3, R7, R16, R27).
2. **Identity and second factor.** Judges use demo login. Real sign-in uses an e-mail code as the second factor, and
   that code path has had no independent review (R1, R2).
3. **Audit trust anchor.** One signing key, no rotation, owner can truncate the table, and tail truncation of an export
   is only detectable against a live head or a receipt (R10, R11, R12, R26).
4. **Operational limits.** Per-process rate limits, shared runner pool, hosted cold starts (R13, R28).
5. **Content accuracy.** Bangladesh Bank summaries and Bangla/Chinese text are not expert-reviewed (R21, R22).
6. **Third-party test service.** The PayPal Sandbox adapter adds an external dependency and has no recorded review (R29).

## 6. What this assessment does not claim

- No claim of real-world fraud-detection accuracy. The numbers are synthetic; the test split was run once.
- No external penetration test and no independent review.
- No claim of compliance with any regulation. Bangladesh Bank summaries in the knowledge base are unverified.
- No on-chain anchoring (`registry_anchor.py` is an unused interface) and no real lender, bank or live payment integration.
