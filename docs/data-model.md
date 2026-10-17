# Setu data model

Single owner: SQLAlchemy 2 models in `services/agent/app/db/models/` + Alembic
(`services/agent/alembic/versions/`). The web app never touches the DB; it uses the generated API types.
All 26 tables were created up front in migration `60340801e54e_initial_schema`. Phase P07 (FR-1) added
`financing_applications` in `70bf00166094`. A phase that needs a schema change is the only phase allowed
to add a migration at that time, and it records that in PROGRESS.md.

## Conventions
- **Money:** `NUMERIC(20,4)` (`Amount`), currency in a separate `CHAR(3)`. FX rates: `NUMERIC(20,8)`.
  Fractions (0.30 = 30%): `NUMERIC(9,6)`. Python side is always `Decimal`. Helpers are in `app/domain/money.py`
  (`Money`, `q2`, `split_by_ratios`).
- **Enums:** `VARCHAR(32)` + CHECK constraint (`app/db/base.py::str_enum`, values in `app/db/enums.py`), not
  native PG enums. A new value needs a migration that replaces the CHECK; there is no `ALTER TYPE`.
- **Ids:** UUID primary keys. Seeded rows use `uuid5(namespace, "<kind>:<stable key>")` (`seed/common.py::sid`),
  so the seed is idempotent. `audit_log` uses `seq` (bigint) and `demo_state` uses `id = 1`.
- **Time:** `DATE` for business dates and `timestamptz` for events. Demo dates are `DEMO_TODAY ± n`.
- **Naming:** constraint names follow `pk_/fk_/uq_/ix_/ck_<table>_…` (see `NAMING_CONVENTION`).
- Sessions: `app/db/session.py`. `get_engine()` is the API engine (2 s statement timeout), and
  `get_batch_engine()` / `batch_session()` are for migrations, seed and scripts.

## Tables

| Table | Purpose | Key columns |
|---|---|---|
| `parties` | Buyers, suppliers, lenders (all fictional) | `code` uq, `kind` BUYER/SUPPLIER/LENDER, `legal_name`, `license_name`, `license_no`, `alias` ("Lender A"), `city`, `country`, `first_seen_on`, `cash_balance`+`cash_currency` (buyers), `kyb_status` |
| `users` | One demo user per role, no passwords | `email` uq, `role` BUYER/SUPPLIER/ADMIN/JUDGE, `language` en/bn/zh, `party_id`, `is_demo` |
| `bank_accounts` | Receiving accounts | `party_id`, `bank_name`, `bank_country`, `account_number` (`SIM-…`), `holder_name`, `account_type` CORPORATE/PERSONAL, `currency`, `status` ACTIVE/PENDING_CHANGE/RETIRED, `opened_on`, `first_seen_on`, `verified`, `change_requested_via/at` |
| `kyb_checks` | KYB result per (party, account) | `status` VERIFIED/WARNING/FAILED/PENDING, `score` (fraction), `reasons` JSONB `[{code, ok, message}]`, `checked_at` |
| `deals` | Import order, reference `SETU-YYYY-NNNN` | `reference` uq, `buyer_id`, `supplier_id`, `beneficiary_account_id`, `title`, `hs_code`, `quantity`, `unit`, `unit_price`, `currency`, `goods_value`, `incoterm`, ports, `expected_sale_value`, `status` DRAFT/PROPOSED/CONFIRMED/FUNDED/IN_PRODUCTION/SHIPPED/ARRIVED/COMPLETED/DISPUTED/CANCELLED, `kyb_run_id` (P13), `opened_on/funded_on/completed_on`, `on_time`, `dispute_count`, `dispute_reason` |
| `deal_costs` | Landed-cost lines | uq(`deal_id`,`kind`), `kind` FREIGHT/INSURANCE/DUTY/BANK_CHARGES/OTHER, `amount`, `currency`, `due_on`, `note` |
| `milestones` | Escrow tranches | uq(`deal_id`,`seq`), `trigger` PRODUCTION_START/SHIPMENT/ARRIVAL, `percent` (fractions of a deal sum to 1), `amount`, `due_on`, `status` PROPOSED/PENDING/READY/PENDING_APPROVAL/RELEASED/FROZEN/REFUNDED/CANCELLED, `required_evidence` JSONB [doc types], `condition_text`, `evidence_status` PENDING/VERIFIED/FLAGGED/REJECTED, `release_idempotency_key`, `released_at` (P13, see `docs/escrow.md`) |
| `escrow_accounts` | Simulated escrow per deal | `deal_id` uq, `funded_total`, `released_total`, `refunded_total`, `balance` (≥ 0; CHECK funded = released + refunded + balance), `partner`, `advance_over_20k`, `status` DRAFT/FUNDED/TRANCHE_RELEASED/COMPLETED/FROZEN/REFUNDED/CANCELLED, `simulated` |
| `ledger_entries` | Simulated double entry | `txn_ref` (each txn balances), `deal_id`, `kind` FUND/RELEASE/REFUND, `milestone_id`, `fx_rate` + `counter_amount`/`counter_currency` (CNY releases), `account` (`buyer:<code>:cash`, `escrow:<ref>`, `supplier:<code>:settlement`), `direction` DEBIT/CREDIT, `amount` > 0, `memo`, `posted_at` |
| `milestone_confirmations` | P13: one row per party that confirmed the current schedule | uq(`deal_id`,`party_role`), `party_role` BUYER/SUPPLIER, `user_id`, `confirmed_at` |
| `credit_records` | FR-8 signed completed-deal record | `deal_id` uq, `payload` JSONB, `payload_hash` = sha256(canonical_json(payload)), `signature` (Ed25519 hex), `key_id` |
| `supplier_scores` | Monthly scorecard | uq(`supplier_id`,`month`), `deals_count`, `on_time_rate`, `defect_rate`, `doc_mismatch_count`, `dispute_count`, `score` 0–100 |
| `cashflow_items` | Dated cash movement per buyer | `key` uq, `party_id`, `on_date`, `kind` SALES/SALARY/RENT/UTILITIES/LOAN_REPAYMENT/LOCAL_PURCHASE/MILESTONE_PAYMENT/DEAL_COST/OTHER, `direction` IN/OUT, `amount` > 0, `is_projected`, optional `deal_id`/`milestone_id`/`deal_cost_id` |
| `fx_rates` | Mock rates, 1 base = rate quote | uq(`base`,`quote`,`as_of`,`kind`), `kind` HISTORY/FORECAST, `source` MOCK |
| `fx_locks` | FR-7 mock rate lock | `deal_id`, `party_id`, pair, `rate`, `amount`, `locked_at`, `expires_at`, `status` |
| `financing_options` | Financing catalogue | `code` uq, `kind`, `provider_party_id`, `annual_rate`, `flat_cost_rate`, `price_uplift_rate`, `fee_rate`, `fee_fixed`, `tenor_days_min/max`, `tenor_rule` (e.g. UNTIL_MILESTONE_3), `min/max_amount`, `collateral`, `conditions`, `eligibility` JSONB, `active` |
| `financing_applications` | FR-1 simulated applications (migration `70bf00166094`) | `reference` uq `FA-YYYY-NNNN`, `party_id`, `deal_id`, `option_id`, `mode` shortfall/order, `amount`, `tenor_days`, `start_on`, `maturity_on`, `total_cost`, `schedule` JSONB, `status` SUBMITTED/APPROVED/REJECTED/CANCELLED, `simulated` |
| `alerts` | Pre-computed alerts | `key` uq, `party_id`, `deal_id`, `milestone_id`, `type` SHORTFALL/DEADLINE/FX_OPPORTUNITY/KYB_WARNING/FRAUD/INFO, `severity`, `status`, `title_en/bn`, `message_en/bn`, `amount`, `due_on`, `facts` JSONB |
| `approval_requests` | Pending human approval (Tier 2/3) | `key` uq, `deal_id`, `milestone_id`, `bank_account_id`, `action`, `tier`, `params` JSONB, `params_hash` = sha256(canonical_json(params)), `reasons` JSONB, `status`, `requested_by`, `otp_required`, `cooling_off_until`, `decided_at/by` |
| `documents` | Trade-document metadata | `key` uq, `deal_id`, `milestone_id`, `doc_type`, `file_name`, `storage_path`, `sha256` uq (file bytes), `canonical_hash` (key fields), `status` UPLOADED/PLACEHOLDER/REJECTED, `check_status`, `variant` CLEAN/FORGED, `extracted_json` |
| `forensic_findings` | Per-document check result | uq(`document_id`,`check_code`), `status`, `severity`, `detail` JSONB |
| `hash_registry` | Cross-lender financed-document registry | uq(`canonical_hash`,`lender_party_id`), `sha256` (indexed), `deal_id`, `doc_type`, `external_ref`, `registered_at` |
| `audit_log` | Append-only signed chain | `seq` PK, `ts`, `actor` user/llm/system, `action`, `tier`, `params_hash`, `result` (≤ 64 chars), `deal_id` (P13, unsigned listing metadata), `prev_hash`, `entry_hash` uq, `signature`, `key_id` |
| `chat_threads` / `chat_messages` | Chat history | thread: `user_id`, `title`, `language`. Message: uq(`thread_id`,`seq`), `role` user/assistant, `content` |
| `demo_state` | Singleton demo pointer | `id`=1, `step`, `anchor_date` |
| `llm_cache` | LLM result cache | `key` (sha256) PK, `model`, `prompt_id`, `response` JSONB |
| `kb_chunks` | RAG chunks | `source`, `title`, `heading_path`, `text`, `embedding vector(384)` |

## Formulas the data relies on
- Audit: `entry_hash = sha256(canonical_json({seq, ts(UTC ISO), actor, action, tier, params_hash, result,
  prev_hash}) + prev_hash)`, `signature = Ed25519(bytes.fromhex(entry_hash))` (`app/security/audit.py`).
  The genesis `prev_hash` is 64 zeros.
- Landed cost = `goods_value` + Σ `deal_costs.amount`.
- Projected balance and shortfall: see `services/agent/seed/cashflow.py` and `data/demo/README.md`.
