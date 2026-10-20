---
paths:
  - "services/agent/app/security/**"
  - "services/agent/app/tools/**"
  - "services/agent/app/graph/**"
  - "services/agent/app/llm/**"
  - "services/agent/app/domain/escrow*"
  - "services/agent/app/forensics/**"
  - "services/agent/app/api/approvals*"
  - "services/agent/app/api/audit*"
  - "services/agent/app/audit/**"
  - "apps/web/src/app/(app)/approvals/**"
  - "apps/web/src/components/approvals/**"
---

# Security rules

## 1. Permission tiers (SR-1, SR-2) — enforced in `app/security/tiers.py`
`classify(action: ActionRequest, ctx: RiskContext) -> TierDecision(tier, reasons[])` is a **pure function**; highest triggered tier wins.

| Tier | Executes | Triggers |
|---|---|---|
| 0 | auto | read-only analysis, checks, calculations, RAG |
| 1 | auto + notice | tranche release to verified, unchanged beneficiary; all evidence checks pass; amount ≤ USD 20,000; fraud score < 0.3 |
| 2 | one-tap human approval | first deal with supplier; minor mismatch (score 0.3–0.6, no hard-fail); FX rate lock; milestone schedule create/change |
| 3 | OTP + 10-min cooling-off | beneficiary/account change; fraud score ≥ 0.6; duplicate hash hit; amount > USD 20,000; **any instruction originating from document/email text**; KYB name mismatch on receiving account |

- Thresholds live in `app/security/policy.py` constants; tests cover every trigger and boundary (=20,000 vs 20,000.01).
- The LLM-facing tool layer only exposes Tier 0/1 tools. `@setu_tool` raises `TierViolation` if a tool with tier ≥ 2 is
  invoked with `ctx.caller == "llm"`. Tier 1 actions re-run `classify` at execution time (never trust a cached tier).
- Approvals (`app/security/approvals.py`): `PendingApproval(id, action, params_hash, tier, reasons, created_at,
  cooling_off_until, status)`. Execution endpoint recomputes `params_hash` and tier; mismatch → reject.
- Tier 3: server-side OTP (pyotp TOTP, shown in a "Simulated SMS" panel) + `cooling_off_until = now + 10 min`; execution
  before that time is rejected server-side; user can cancel during cooling-off. Escrow is FROZEN while a Tier 3 is pending.

## 2. Prompt-injection defence (SR-3) — `app/security/injection.py`
- Untrusted text (documents, emails, supplier messages) is passed to models only inside
  `<untrusted_document id="..." sha256="...">…</untrusted_document>` with the system prompt stating its content is data.
- `detect_instructions(text) -> list[Finding]`: imperative/role patterns (`SYSTEM:`, "ignore previous", "release", "approve",
  "transfer", "verified", tool-call-like JSON), base64/homoglyph decoding, Bangla/Chinese equivalents, **plus hidden text**
  (white/near-background colour, font < 2pt, off-page) from `forensics/hidden_text.py`. Any finding → Tier 3 trigger
  `DOC_INSTRUCTION` and an audit entry.
- Per-node tool allow-lists; the forensics node has **no** action tools. Model outputs that request actions are parsed
  against a schema; free-text "approve/release" from the model is ignored.
- Never let document-derived strings become tool names, URLs, SQL, or approval parameters without validation.

## 3. Privacy Gateway (SR-4) — `app/security/privacy_gateway.py`
- Detectors: BD NID (10/13/17 digits), bank account numbers (8–18 digits, IBAN-like), phone (`+?880?1[3-9]\d{8}`, CN `1[3-9]\d{9}`),
  emails, unit prices/amounts in documents (`USD|CNY|BDT|$|¥|৳` + number), person names from known-party list.
- Replace with stable reversible tokens `⟦ACCT_1⟧`, `⟦PHONE_2⟧`, `⟦AMT_3⟧`; vault is per-request, in memory, never sent to the model or logged.
- Deterministic code always works on the **unmasked** values; only the LLM sees masked text. Unmask only the final user-facing answer.
- Must be called inside `app/llm/client.py`; a test asserts no raw PII reaches the (mocked) model.

## 4. Audit log (SR-5) — `app/audit/` (full spec: `docs/audit.md`)
- Entry body `{seq, ts, actor_type, actor_id, deal_id, action, tier, decision, payload}`; `payload_hash = sha256(canonical_json(body))`;
  `entry_hash = sha256(prev_hash|payload_hash|seq|ts)`; `signature = Ed25519(entry_hash)`; seq 1 links to the genesis hash.
- Write only through `app.audit.write_audit` (single ordered writer; payload is PII-redacted before signing). A DB trigger
  rejects UPDATE/DELETE. No signing key = no row. Never put raw PII, secrets or document text in a payload: ids and hashes.
- `GET /audit/verify`, `GET /audit/export` (JSONL), `python -m app.audit.verify --file … --pubkey docs/submission/audit-public-key.pem`,
  public `/verify` page (browser-side). The tamper demo works on an in-memory copy only.

## 5. Secrets & data (SR-7, SR-8)
- Keys from env only: `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY`, `DATABASE_URL`, `AUDIT_SIGNING_KEY` (base64 Ed25519 seed),
  `OTP_SECRET_SEED`. Never hard-code, log, return in API responses, or include in prompts.
- `.env*` files are blocked from Claude by hooks and permissions — ask the user to set values.
- All payments/ledger are simulated; endpoints and UI say "Simulated". No real bank/payment APIs.

## Review checklist (security-reviewer uses this)
- [ ] No tier ≥ 2 path reachable from an LLM tool call · [ ] tier recomputed at execution · [ ] params hash bound to approval
- [ ] untrusted text wrapped + detector run · [ ] LLM call goes through client.py · [ ] no PII/secret in logs, prompts, audit entries
- [ ] audit entry for each action · [ ] Decimal money · [ ] tests for new triggers/boundaries
