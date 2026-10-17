# Supplier KYB (FR-4)

Deterministic, no LLM. It tells a buyer, before money moves, whether a supplier and its receiving bank
account can be trusted, with reasons in English and Bangla. Pure logic: `services/agent/app/domain/kyb.py`.
Orchestration and persistence: `app/services/kyb.py`. API: `app/api/kyb.py`, `app/api/suppliers.py`.
Agent tool: `verify_party` (Tier 0, read-only). All data is simulated.

## Checks

Each check is `PASS | WARN | FAIL` with `code`, `detail_en`, `detail_bn`, `evidence`.

| Code | Rule | Weight |
|---|---|---|
| `LICENSE_VS_INVOICE_NAME` | licence name vs seller on the proforma invoice (`Document.extracted_json["seller"]`, else the legal name, or an explicit override) | 15 |
| `LICENSE_VS_ACCOUNT_HOLDER` | licence name vs account holder | 25 |
| `ACCOUNT_TYPE` | `PERSONAL` account for a company -> FAIL | 20 |
| `ACCOUNT_AGE` | first seen < 7 days FAIL, < 30 days WARN | 15 |
| `ACCOUNT_COUNTRY` | bank country differs from the registered country, or a BDT account -> WARN | 10 |
| `PENDING_BENEFICIARY_CHANGE` | pending accounts only: always WARN | 5 |
| `REGISTRY_HISTORY` | WARN if >= 2 disputed deals or more than half of the supplier's active/completed deals disputed; evidence carries completed/disputed counts and the last 3 KYB results | 10 |
| `SANCTIONS_SCREEN` | supplier, licence, invoice and holder names vs `data/demo/sanctions_mock.json` (fictional); any hit -> FAIL | critical |
| `RECEIVING_ACCOUNT` | extra: no active account on file -> WARN | 25 |
| `DOC_INSTRUCTION` | extra: instruction-like text in the invoice seller name -> FAIL | 20 |

### Name match
Normalise: NFKC, case-fold, `&` -> `and`, a tiny CJK map (有限公司 -> `ltd`, 公司 -> `co`, 贸易 -> `trading`, ...),
ASCII fold of accents, punctuation removed, whitespace collapsed, suffixes canonical (`Company/Corp/Corporation/Inc` -> `co`,
`Limited/LLC` -> `ltd`, `Trade` -> `trading`). Plurals and `Trading` are kept as tokens, so extra words count.
`score = floor2((token_set_ratio + token_sort_ratio) / 2)`: token_set alone gives 100 to any subset name.
`partial_ratio` is returned as evidence.

Thresholds (settings `KYB_MATCH_THRESHOLD=92`, `KYB_PARTIAL_THRESHOLD=80`): score >= 92 match (PASS),
80 <= score < 92 partial (WARN), < 80 mismatch (FAIL). `KYB_SANCTIONS_PATH` (default
`data/demo/sanctions_mock.json`, relative to the repo root) points at the mock list.

## Score and status
`score = 100 - sum(weight x severity)`, severity FAIL 1, WARN 1/2, rounded half up, floor 0.
A sanctions FAIL forces score 0. The weights of the seven normal checks sum to 100.
Status: `BLOCKED` if the sanctions check fails; else `WARNING` if any check is WARN or FAIL; else `VERIFIED`.
`reason_codes` = non-PASS check codes, FAILs first. `explanation_en/bn` are fixed templates (Bangla digits).

## Design decision: evaluate per account
The supplier-level `status` and `score` come from the supplier's **ACTIVE receiving account** (the deal's beneficiary
account if given, else the newest active one) plus the party-level checks. A `PENDING_CHANGE` account is evaluated
separately and returned in `pending_accounts[]` with its own status, `PENDING_BENEFICIARY_CHANGE` WARN and (for a
foreign bank) `ACCOUNT_COUNTRY` WARN. It does **not** downgrade the supplier's current status; the result carries
`has_pending_change: true`. That is how Huaxin stays VERIFIED (corporate CNY account, 400 days old) while its
unreviewed Hong Kong account shows WARNING (holder name mismatch, 1 day old, new country). Moving money to that account
is still a Tier 3 approval (`BENEFICIARY_CHANGE`); KYB only informs it.

Demo outcomes (DEMO_TODAY 2026-10-20): Huaxin VERIFIED 100 (+ pending HK WARNING), Brightline VERIFIED 100,
Huameng WARNING 40 (holder, type and age all FAIL; TC-01).

## Per-deal invoice name vs shared state
`LICENSE_VS_INVOICE_NAME` depends on a deal's proforma invoice, so it is **per deal**. Two assessments run each time:
the deal result (with the invoice name, stored on that deal's `KybRun`) and a party/account-only result (no invoice
check, no invoice screening). `Party.kyb_status`, `kyb_checks`, `BankAccount.verified` and retirement come only from the
second one (`KybResult.party_status` / `party_score` expose it). A run without a deal therefore cannot undo a
deal-specific problem, and an invoice name cannot flip a supplier.

Invoice-name text is untrusted: it is cleaned, then `detect_instructions` runs on it. A finding means the legal name
is used instead, the result gets a `DOC_INSTRUCTION` FAIL (weight 20), `invoice_flags` lists the finding codes, and a
tier 3 `DOC_INSTRUCTION_DETECTED` audit row is written. Alert text is built from codes and the supplier's own legal
name only, never document text.

Sanctions: names are screened with roles (`legal_name`, `licence_name`, `account_holder`, `invoice_name`). A hit on the
first three is **blocking** (BLOCKED, score 0, account retired). A hit on the invoice name alone is a **hold**: the
deal result is WARNING with score <= 20, `SANCTIONS_SCREEN` FAIL with `evidence.blocking=false`, nothing is retired.
Normalisation folds Cyrillic/Greek lookalikes to Latin and drops zero-width characters (`HOMOGLYPHS` in the domain), so
they cannot dodge the screen. The sanctions file must have a `version` and non-empty `entries` (each with `id` and
`names`); otherwise KYB fails closed with 503.

## Persistence (`POST /kyb/verify`)
- `Party.kyb_status`: VERIFIED / WARNING / FAILED (= BLOCKED), from the party/account-only result.
- `kyb_checks`: one row per (party, account), updated in place. `kyb_runs`: one history row per run with the full result.
- `BankAccount.verified` = the account's own party/account result is VERIFIED. Conservative lifecycle: an account whose
  own result is BLOCKED goes `ACTIVE/PENDING_CHANGE -> RETIRED`; nothing else changes `status`; no automatic re-activation.
- Audit: signed, hash-chained `audit_log` rows via `app.security.audit.write_audit` (advisory lock, seq, prev_hash,
  Ed25519; raises 503 and writes nothing without a key). `KYB_CHECKED` (tier 0) params include `retired_account_ids`
  and `verified_changes`; params are stored as a hash. The agent tool still goes through the registry's `record_event`
  (log only, scheduled for 5.4) and writes no signed row.
- Alerts (`alerts.sync_kyb_alerts`), type `KYB_WARNING`:
  - supplier level, per buyer with open deals (DRAFT, FUNDED, IN_PRODUCTION, SHIPPED), key
    `alert:<buyer code>:kyb:<supplier code>`, from the party/account result. WARNING -> WARNING, BLOCKED -> CRITICAL.
  - deal level, key `alert:<buyer code>:kyb:<supplier code>:<deal reference>`, only from a run with that deal.
  Lookups require type `KYB_WARNING` and `facts.supplier_id`; a foreign row on the key moves us to a hashed key.
  Idempotent. Resolved by the engine when clean; supplier-level alerts are resolved only for buyers in the run's scope
  (a buyer's run: itself; admin/seed: all); a run without a deal never touches a deal-level alert. The pre-P12 seed key
  `...:kyb-huameng` is adopted by re-keying. The seed no longer writes this alert; `seed.cli` runs the sync.

## Visibility
A buyer is only shown runs with no deal or on its own deals, so another buyer's invoice name (and the invoice reason
codes) never appear in `GET /kyb/{id}`, the profile or the history; with none, a live read-only result is returned.
The chat card (what the model sees) uses role labels per reason code and omits account-holder, invoice and
sanctions-hit names; the full text is only in the API.

## Endpoints
| Method / path | Who | Notes |
|---|---|---|
| `POST /kyb/verify/{supplier_id}?deal_id=` | buyer (own suppliers), admin | writer; judge and supplier 403 |
| `GET /kyb/{supplier_id}` | buyer (own), admin, judge | latest stored result (or a live read-only one) + history |
| `GET /suppliers?buyer_id=` | buyer, admin, judge | badge, score, completed deals, on-time %, last checked |
| `GET /suppliers/{id}?buyer_id=` | buyer, admin, judge | company, masked accounts, deals, scorecard trend, KYB |

A buyer only sees suppliers it has deals with; others look missing (404). Account numbers are always masked.
