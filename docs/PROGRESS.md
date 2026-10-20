# Setu — Progress log

Updated at the end of every phase by the `phase-handoff` skill. Newest entries at the bottom.
Times are Dhaka (UTC+6). Deadline: 20 Oct 2026 21:59 Dhaka. Must-have cut line: 19 Oct 23:59.

## Phase checklist
- [x] 0.1 · [x] 1.1 · [x] 1.2 · [x] 1.3
- [x] 2.1 · [x] 2.2 · [x] 2.3 (FR-2; FR-7 route compare open) · [~] 2.4 (i18n, fonts, shell, client only) · [x] 2.5 · [x] 2.6
- [~] 3.1 (LLM client, tracing, tier-gated registry, FR tools; no LLM cache) · [x] 3.2 (P10 RAG + citations) · [x] 3.3 (agent, FR tools, citations) · [x] 3.4 (P09 chat UI)
- [x] 4.1 · [x] 4.2 · [x] 4.3 · [ ] 4.4 · [ ] 4.5
- [x] 5.1 · [ ] 5.2 · [ ] 5.3 · [ ] 5.4 · [ ] 5.5
- [ ] 6.1 · [x] 6.2 (P21) · [~] 6.3 (P22: landing, design system, polish; see gaps)
- [ ] 7.1 · [ ] 7.2
- [~] 8.1 (P23: repo side only; not deployed)
- [ ] 9.1 · [ ] 9.2 · [ ] 9.3

## Log

| Phase | Date (Dhaka) | Status | What was done | Test result | Handoff note |
|---|---|---|---|---|---|
| setup | 2026-10-17 | done | Planning session: CLAUDE.md, rules, agents, skills, hooks, PLAN/REQUIREMENTS/PROGRESS docs. No app code. | hook pipe-tests pass | Start Phase 0.1 in a fresh session. |
| 0.1 | 2026-10-17 02:39 | done | Monorepo scaffold: pnpm workspace, Next.js 16 web + status card, FastAPI agent /health, pgvector compose, Makefile, env examples, README. | pytest 4 passed · vitest 2 passed · lint/tsc/ruff clean · build ok | Copy .env.example → .env; `pnpm run db:up`, `pnpm run dev`. Next: Phase 1.1 schema. |
| 1.1+1.2 | 2026-10-17 03:35 | done | All 26 tables + initial Alembic migration; Money helpers; audit-chain primitives; deterministic P03 demo seed (Rahima/SETU-2026-0001), reset-demo, verify_seed. | pytest 45 passed (incl. 7 db) · vitest 2 · ruff clean · verify_seed 18/18 · security review: pass with fixes (highs fixed) | Read data/demo/README.md + docs/data-model.md. Read endpoints deferred to next phase. |
| 2.1+2.6a (P05) | 2026-10-17 04:07 | done | FR-3 domain lib + 5 analysis endpoints, demo-login stub, /app shell, EN/BN i18n, order analysis, calculator, monthly summary, supplier scorecard pages. | pytest 105 passed · vitest 13 passed · Playwright smoke 1 passed · lint/tsc/ruff clean · next build ok · security review: pass with fixes (fixed) | Financing UI (2.6) + FR-1 engine (2.2) next. Margin is 18.01, not 18.00. |
| 2.3+2.5 (P06) | 2026-10-17 04:44 | done | FR-2 90-day forecaster, what-if scenarios, idempotent alert engine (shortfall/deadline/FX), alert + dashboard endpoints; Dashboard, Cash Flow, financing/approvals placeholders. | pytest 159 passed · vitest 25 passed · Playwright 2 passed · lint/tsc/ruff clean · build ok · verify_seed 17/17 · security review: pass with fixes (fixed) | Next P07 financing (FR-1) replaces /app/financing placeholder. |
| 2.2+2.6b (P07) | 2026-10-17 05:21 | done | FR-1 gap (shortfall/order), option matching with eligibility + ranking, schedule, cash-flow impact, simulated applications (+ migration); /app/financing comparison UI. | pytest 189 passed · vitest 33 passed · Playwright 3 passed (serial, E2E_RESET_DEMO) · lint/tsc/ruff clean · build ok · verify_seed 17/17 · security review: pass with fixes (fixed) | TC-09 holds via two product rules; approvals must move behind ACCEPT_FINANCING tiers in 5.x. |
| 3.3 (P08) | 2026-10-17 05:40 | done (real-model check open) | LangGraph agent: router → agent ⇄ tier-guarded tools → respond; 3 Tier 0 tools; Postgres checkpointer; chat threads; /chat + SSE; LangSmith; offline mock model. | pytest 233 passed (incl. db) · ruff clean · web tsc ok · security review: pass with fixes (1 medium + 6 low fixed; 1 medium privacy gap open → P18) | Real Claude run blocked: ANTHROPIC_API_KEY in .env is empty. P09 adds finance tools + chat UI. |
| 3.4 (P09) | 2026-10-17 07:24 | done (real-model check open) | 10 Tier 0 finance tools returning cards (landed cost, cash flow, alerts, financing, FX route, monthly, scorecard), FR-7 FX route, Why-line guarantee; /app/chat + drawer with rich cards, threads, feedback. | pytest 322 passed (incl. db) · vitest 80 passed · Playwright 4 passed · lint/tsc/ruff clean · build ok · security review backend + UI: pass with fixes (fixed) | ANTHROPIC_API_KEY still empty: real-model run open. Next P10 RAG + citations. |
| 3.2 (P10) | 2026-10-17 10:25 | done (real-model check open) | Cited knowledge base: 7 KB sources (own summaries + generated financing catalogue), heading chunker, local multilingual embeddings, hybrid pgvector + FTS retrieval (RRF), search_knowledge tool, [S1] citations in answers/API/UI. | pytest 355 passed (incl. db, real-model retrieval table) · vitest 90 passed · Playwright 5 passed · lint/tsc/ruff clean · build ok · security review: pass with fixes (2 medium + 6 low fixed) | Merged P08–P10 to main. ANTHROPIC_API_KEY still empty. |
| 3.1b (OpenRouter) | 2026-10-17 10:39 | done | Real-model path via OpenRouter (Anthropic-compatible endpoint); provider auto-selection; first real Claude run of the P08–P10 chat. | pytest 362 passed · ruff clean · 12 live EN/BN questions OK | LangSmith traces verified. |
| 1.3 (P11) | 2026-10-17 11:03 | done | Synthetic trade-document generator: 100 clean + 100 tampered packs (10 fraud types, obvious/subtle), 25-item injection attack set, committed demo files matching the seed. | pytest tests/synthetic 29 passed · full suite 275 passed · ruff clean · verify_seed 18/18 | Hash registry now matches prefinanced_invoice.pdf. P14 tunes on dev only, P24 reports on test. |
| 4.2 (P12) | 2026-10-17 11:33 | done | Deterministic supplier KYB engine (8 checks, EN/BN reasons, per-account + per-deal results), signed audit append, KYB alerts, verify_party tool, Suppliers pages, deal KYB panel, chat card. | pytest 465 passed (incl. db) · vitest 99 passed · Playwright suppliers 2 passed · lint/tsc/ruff clean · next build ok · verify_seed 19/19 · security review: pass with fixes (1 high + 4 medium + 4 low fixed) | Next P13 escrow + Deals UI; reuse KybBadge, write_audit, KybResult. |
| 4.1 (P13) | 2026-10-17 12:16 | done | Simulated milestone escrow: state machines, double-entry ledger, evidence-gated idempotent release behind a risk hook, refunds, Deals list/new/detail UI, supplier portal (EN + 中文). | pytest 639 passed (incl. db) · vitest 128 passed · Playwright 8/9 (chat citation test unrelated) · lint/tsc/ruff clean · next build ok · verify_seed 19/19 · security review: pass with fixes (1 high + 4 medium + 6 low fixed) | Next P14 forensics sets evidence_status via set_evidence_status; Phase 5.1 replaces risk_hook.default_evaluate. |
| 4.3 (P14) | 2026-10-17 13:51 | done | Document forensics: safe upload, text/hidden-span extraction, parser + guarded LLM fallback, 11 cross-checks, fraud score, evidence automation, viewer with hidden-text reveal, supplier upload, check_documents tool. | pytest 831 passed (incl. db) · vitest 163 passed · Playwright documents spec passed · lint/tsc/ruff clean · next build ok · verify_seed 19/19 · dev split P/R 1.00 on all checks · security review: pass with fixes (2 high + 8 medium + 8 low fixed) | Next P15 hash registry via hash_registry.set_checker; P24 reports on the TEST split only. |
| 5.1 (P16) | 2026-10-19 | done (OTP/approval endpoints are P17) | Deterministic risk-tier engine (rules in config/risk.yaml) enforced inside release, fund, propose/confirm schedule, FX lock, beneficiary change; agent propose-only tools; rule trace, hints, dry-run playground, policy + admin views. | pytest 878 passed, 27 registry tests deselected (they need a DB on :5435 and fail the same without this change) · ruff clean · vitest 194 passed | P17 builds the human approval endpoints (OTP, cooling-off, cancel/expiry) on `gate.verify_approval`. |
| 6.3 (P22) | 2026-10-20 | partial | Design system (tokens, dark mode, 20 UI components), landing page, app shell (sidebar, Ctrl/⌘K palette, onboarding, 404/500), BN/ZH coverage check, SEO, /accessibility. | vitest 420 passed · tsc, eslint, i18n:check clean · Playwright p22 5/5 · Lighthouse mobile `/` 93/100/100/100, `/app` perf ~77, `/demo` perf 85 | Lighthouse perf on `/app` is below 85; Bangla/Chinese not native-reviewed; real figures for 2 problem cards still needed. |
| 8.1 (P23) | 2026-10-20 | partial (repo side done; nothing deployed) | Prod hardening (rate limits, headers, body caps, rich /health), Dockerfiles + compose `full` profile + Caddy, /judges page, status/version chips, smoke scripts, README v1, submission package drafts. | vitest 433 passed · eslint/tsc/ruff clean · pytest 1313 passed, 23 registry tests fail (DB-dependent, same without these changes) · smoke_prod 10/10 on a local container | User must create Neon/Vercel resources and enter secrets; then run smoke twice and export the prod operation log. |

## Handoff notes

### setup
- `docs/SRS.md` was not provided; `docs/REQUIREMENTS.md` is the stand-in spec. If the SRS is added, Phase 0.1 reconciles it.
- Decisions: Python/Alembic owns the DB schema; web talks only to FastAPI; Vercel for both apps (Vercel Services, fallback two projects); Neon + pgvector in prod, docker pgvector locally; fastembed embeddings.
- `gh` CLI not installed; Docker, jq, psql, uv, pnpm, Node 24, Python 3.13, Vercel CLI available.

### 0.1
- **Run:** `cp .env.example .env` → `pnpm install && uv sync --directory services/agent` → `pnpm run db:up` →
  `pnpm run dev` (or `dev:agent` :8000 / `dev:web` :3000). `pnpm run lint|format|test|types`; `npm run …` and
  `make up down dev test lint format types migrate seed eval` wrap the same scripts.
- **Files:** root `package.json` + `pnpm-workspace.yaml` (workspace = `apps/web`), `Makefile`, `docker-compose.yml`
  (service `db`, volume `setu-pgdata`), `infra/db/init.sql`, `scripts/gen-types.sh`, `.env.example` (root, all keys from
  security.md §5), `apps/web/.env.example`, `services/agent/.env.example`, `README.md` (Local setup).
- **Agent:** `app/main.py` (`create_app()`, CORS from `ALLOWED_ORIGINS` comma list), `app/config.py` (pydantic-settings;
  reads env → root `.env` → `services/agent/.env`; secrets are `SecretStr`), `app/db/session.py` (`get_engine()`, `ping()`;
  normalises `postgresql://` → `postgresql+psycopg://`, 2 s connect/statement timeout), `app/api/health.py`
  (`GET /health` → `HealthResponse{status,service,db,version}`; DB down → `db:"unavailable"`, never 5xx).
- **Web:** `src/lib/api/client.ts` (`apiGet`, `getHealth`, `ApiError`; base `NEXT_PUBLIC_API_BASE`, default `/api`),
  `next.config.ts` rewrites `/api/:path*` → `AGENT_URL` (default http://localhost:8000), `components/status/{AgentStatusCard,StatusRow}.tsx`
  (polls /health every 10 s), placeholder `@theme` tokens per frontend.md in `globals.css`, Inter font only.
  `typecheck` = `next typegen && tsc --noEmit` (route types like `LayoutProps` need typegen on a clean checkout).
- **Versions:** Node 24.15.0, pnpm 11.24.0, Next 16.4.1 (Turbopack, `cacheComponents: true` from create-next-app),
  React 19.3.0, Tailwind 4.3.3, TS 5.9.3, ESLint 9.39.5 + eslint-config-prettier, Prettier 3.9.10 + tailwind plugin 0.8.1,
  Vitest 5.0.5, openapi-typescript 7.13.0 · Python 3.13.12, uv 0.11.28, FastAPI 0.143.3, SQLAlchemy 2.1.4,
  pydantic-settings 2.16.0, LangChain 1.4.6, LangGraph 1.2.15 · `pgvector/pgvector:pg16`, `vector` 0.8.7.
- **Deviations from PLAN 0.1:** none in deps (full list installed). Added a root `package.json`/pnpm workspace with
  cross-platform scripts alongside the Makefile; `make migrate|seed|eval` print a "added in Phase X" notice until those
  phases exist. `e2e` script is a placeholder until Playwright lands (6.2). No `docs/SRS.md`, so step 7 skipped.
- **Next phase reads:** `app/config.py` and `app/db/session.py` (extend, don't replace); Alembic is not initialised yet (1.1 does `alembic init`).

### 1.1 + 1.2 (one session, from the user's "P03 seed" prompt)
- **Scope:** Phase 1.1 (schema) had not been done, so this session built it too (user's choice). The P03 demo world
  **replaces** PLAN's Rahman Textiles / ORD-1042 / ORD-1043. PLAN "Standard demo data" is rewritten, and later ORD-1042
  references now read SETU-2026-0001. There is no ORD-1043; the USD 20,000 rule needs a test deal.
- **Run:** `pnpm run db:up` → `pnpm run db:migrate` → `pnpm run db:seed` → `./scripts/verify_seed` (18 checks, re-seeds
  twice). `pnpm run db:reset-demo` wipes everything except `kb_chunks`/`llm_cache` and reseeds. `make migrate|seed|reset-demo|verify-seed` wrap them.
- **Schema:** `app/db/{base,enums,session}.py`, `app/db/models/{identity,deals,finance,trust,app_state}.py`, migration
  `alembic/versions/20261017_60340801e54e_initial_schema.py` (hand-reviewed: removed duplicate enum CHECKs, added
  `CREATE EXTENSION vector`; `alembic check` reports no drift). Enums are VARCHAR + CHECK. Table list: `docs/data-model.md`.
- **Money:** `app/domain/money.py` (`Money`, `D`, `q2`, `split_by_ratios`, `money_sum`; floats rejected).
- **Audit primitives:** `app/security/audit.py` (`canonical_json`, `params_hash`, `compute_entry_hash`, `build_chain`,
  `verify_chain`, `load_signing_key`). `ts` is hashed in UTC. Key = `AUDIT_SIGNING_KEY` (hex or base64 32-byte seed),
  else a dev key auto-created at seed time in git-ignored `keys/audit_dev_ed25519.key`. Phase 5.4 builds the append
  service, /audit/verify and export on these.
- **Seed:** `services/agent/seed/` has one pure `build(ctx)` per domain plus `cli.py` (the only DB writer: upsert on PK)
  and `verify.py`. Ids are uuid5 of stable keys, and all dates are `DEMO_TODAY ± n` (setting `demo_today`, env `DEMO_TODAY`,
  default 2026-10-20). After an anchor change, `db:seed` refuses and asks for `db:reset-demo`. It produces 610 rows.
  `audit_log` and `approval_requests` are insert-only on re-seed; `reset-demo` refuses a non-local DB without `--allow-remote`.
- **Key numbers:** landed cost 11,200.00; milestones 2,880/5,760/960; margin 18.01% (sale 13,660); Rahima balance on the
  M2 date (2026-11-07) 4,200.00 → shortfall 1,560.00; good CNY day T+2 (CNY/BDT −1.84% vs the 30-day mean); 5 financing
  options; FX 91 days of history + 7 forecast days per pair; 1 pending Tier 2 + 1 pending Tier 3; Lender A holds the
  PI hash; audit chain of 35 entries is valid.
- **Decisions:** (1) Tier 2 reason for the M1 release is `FX_RATE_LOCK` (USD→CNY to Huaxin's CNY account), not
  "first deal": the spec also seeds 2 completed Rahima–Huaxin deals (user's choice). (2) Escrow is funded tranche by
  tranche, so the main deal is FUNDED with M1 only and M2 is a future cash outflow. (3) The seeded Tier 3 beneficiary
  change is PENDING while the deal stays FUNDED (per spec). 5.1 decides whether a pending Tier 3 freezes escrow.
  (4) No passwords are stored; the demo "login as" switch arrives with auth. (5) Document sha256 hashes the real file in
  `data/demo/SETU-2026-0001/` when present, otherwise a deterministic placeholder; the hash registry follows.
- **Tests:** `tests/domain/test_money.py` (golden + Hypothesis), `tests/security/test_audit.py` (tamper, unlink,
  wrong key, TZ invariance), `tests/seed/test_seed_build.py` (pure: numbers for 3 anchors, determinism, no floats,
  unique ids), `tests/seed/test_seed_db.py` (`@pytest.mark.db`: migration, seed twice → identical, reset). DB tests use
  `TEST_DATABASE_URL` or `<db>_test` on the same server, **only if DATABASE_URL is localhost**; otherwise they skip.
- **Security review (security-reviewer): PASS WITH FIXES.** Fixed: both highs (the test-DB guard now requires a local
  host, a `_test` name and a database other than DATABASE_URL; re-seeding no longer rewrites audit or approvals, and
  there is no implicit wipe). Also fixed: `params_hash` = `app/security/approvals.py::approval_binding_hash` over action,
  tier, deal, milestone, account and params; DB CHECKs `tier IN (2,3)` and `tier3 ⇒ otp_required AND
  cooling_off_until`; `DOC_INSTRUCTION` reason on the email-originated change; audit rejects naive `ts`, catches seq
  gaps, key dir 0700 and key file must be 0600. **Open, for 5.1/5.4:** (a) security.md says escrow is FROZEN while a
  Tier 3 is pending, but the spec seeds the deal FUNDED. 5.1 must block releases while a Tier 3 is pending on the same
  deal or supplier, or freeze it. (b) The seeded cooling-off uses DEMO_TODAY 09:45, so 5.1 restarts the window when the
  OTP flow begins. (c) `canonical_json` does not reject floats. (d) No signed chain-head anchor (tail truncation of the
  last entries is undetectable). (e) Seeding a hosted DB without AUDIT_SIGNING_KEY signs with a local dev key; set the
  env var in prod.
- **Not done (deferred):** read endpoints (`GET /suppliers`, `/deals`, `/fx/rates`, `/financing/options`), `make types`,
  `hs_duty.json`, `POST /demo/reset`.
- **Next phase reads:** `docs/data-model.md`, `data/demo/README.md`, `seed/financing.py` docstring (eligibility facts),
  `seed/cashflow.py` docstring (balance rule).

### 2.1 + 2.6 analysis half (from the user's "P05 FR-3 analysis" prompt)
- **Scope:** "P04" (the finance library) had not been built, so this session built the FR-3 subset as well.
  It lives in `app/domain/` (per CLAUDE.md), not `app/finance/`; prompts that say `app/finance` mean this.
  Files: `fx.py` (`FxQuote`, `FxTable.rate/convert/path`), `landed_cost.py`, `margin.py`
  (`gross_margin`, `break_even_price`, `price_for_margin`, `margin_band`), `summary.py`, `scorecard.py`,
  `narrative.py` (deterministic EN/BN sentences with stable codes). Formulas: `docs/finance-formulas.md`.
  There is no HS-code duty table yet (`seed/hs_duty.json` is still open).
- **Endpoints** (FastAPI paths; the web app calls `/api/...`). Models are in `app/schemas/analysis.py`, the
  service in `app/services/analysis.py` (read-only), and errors are RFC 7807 via `app/errors.py`:
  - `GET /analysis/orders`: the caller's deals.
  - `GET /analysis/orders/{ref|uuid}?target_margin_pct=`: breakdown + shares, KPIs, break-even, target
    price, `fx[]` with `as_of`, `explanations[{code,en,bn}]`, `facts`.
  - `POST /analysis/landed-cost`: what-if. Money must be strings; floats get 422. Saves nothing.
  - `GET /analysis/monthly?party_id=&month=YYYY-MM`.
  - `GET /analysis/suppliers?party_id=`.
  - Every amount is `Amounts{USD,BDT,CNY}`, converted server-side, so the UI never computes. Percents
    are 2-dp strings. Per-unit values have 2–4 dp.
- **Numbers for UI checks** (SETU-2026-0001):
  - landed `11200.00` (BDT `1373008.00`, CNY `79508.80`), per unit `1.40`.
  - **margin `18.01`** (the P05 prompt said 18.00; 2,460/13,660 = 18.009%), markup `21.96`, 20% target
    price `1.75`, duty share `7.14`.
  - Rahima Oct 2026: 1 deal, 9,600 / 11,200, top driver DUTY 50%.
  - Karim Sep 2026: 2 deals, 11,700 / 14,595, avg margin 12.60.
  - Scorecard: Huaxin 96.25, Brightline 89.14, Huameng 57.79 (weak: KYB_NOT_VERIFIED, LOW_SCORE,
    HIGH_DISPUTE_RATE, LOW_ON_TIME).
- **Auth stub:**
  - `app/auth/demo.py` maps the HMAC-signed cookie `setu_demo_session` (12 h) to a user id.
  - `app/auth/deps.py` (`CurrentUser`, `current_user`, `require_analysis_reader`, `can_read_party`) is
    the swap point for real auth. Endpoints are `/auth/demo-users|demo-login|me|logout`.
  - Access: BUYER reads own data only (another buyer's deal gives 403); ADMIN/JUDGE read all (monthly
    needs `party_id`); SUPPLIER gets 403.
  - New settings: `APP_ENV` (dev|test|prod), `DEMO_SESSION_SECRET`, `DEMO_COOKIE_SECURE`. In prod,
    `create_app` refuses to start without a 32+ char secret and a secure cookie, or with `*` in
    `ALLOWED_ORIGINS`. **Not added to `.env.example`**, because that file has uncommitted local edits
    with real-looking values. Add the placeholders after cleaning it.
- **Web:**
  - Routes: `/login` ("Login as"); `/app` shell (header with Simulated badge, EN/বাংলা toggle, user
    menu; nav Analysis + Orders); `/app/orders`; `/app/orders/[id]` (minimal deal detail that links to
    the analysis; 4.5 replaces it); `/app/orders/[id]/analysis`; `/app/analysis?tab=calculator|monthly|suppliers`.
  - The routes use the `/app` URL prefix the prompt asked for (folder `src/app/app/`), not the
    `(app)` route group from frontend.md.
  - i18n: `src/i18n/{index.tsx,en.json,bn.json}`. `useT()` gives `t("a.b", vars)`. Also `useLang()`,
    `pickLang()` for API `{en,bn}` text, and the cookie `setu_lang`. A test asserts en/bn key parity.
  - Fonts: Inter + Noto Sans Bengali (next/font).
  - Charts: Recharts (MIT; README "Third-party licences").
  - Helpers: `src/lib/format.ts` (`formatMoney(str, ccy, lang)` gives ৳/$/¥, string-fed Intl),
    `src/lib/useApi.ts` (`useApi`, `useDebounced`).
  - Shared: `QueryError` (401 → `/login?next=`), `AnalysisResults`, `KpiCard band`.
  - e2e: `apps/web/playwright.config.ts` + `e2e/analysis.spec.ts` (`pnpm --dir apps/web e2e`, base
    `E2E_BASE_URL`). Chromium is installed in `~/.cache/ms-playwright`.
- **Verified in a browser** (prod build on :3100 → agent on :8001 against the local DB):
  - Order page numbers match; currency toggle USD/BDT/CNY works; target 20% gives $1.75.
  - The Bangla toggle switches labels, sentences and `<html lang>`.
  - The calculator updates live; monthly shows 18.01%; the scorecard shows 3 suppliers with Huameng
    highlighted.
  - No horizontal scroll at 360 px (en and bn).
- **Security review: PASS WITH FIXES, all fixed.**
  - Fixed: non-ASCII cookies 500'd (now 401); the calculator was open to SUPPLIER (now reader-only);
    `current_user` now requires `is_demo`; prod startup guard; catch-all problem-JSON 500;
    authorization helpers moved out of the demo module.
  - Accepted, by design:
    - Another buyer's deal gives 403 (the prompt asked for 403), not 404, so deal references are
      enumerable.
    - Scorecard `price_index`/`completed_deals_count` aggregate network-wide deals. Revisit with a
      minimum-count floor if real data arrives.
    - Logout is client-side only (cookie stays valid ≤ 12 h).
- **Known gaps:**
  - FR-1/FR-2 engines (2.2/2.3), the financing UI, and the dashboard/cash-flow pages are not built.
  - No zh dictionary.
  - The Why panel's `facts` stay English.
  - The admin/judge buyer picker on the monthly tab is not covered by tests.
  - Rahima's 6-month chart has one non-zero month (seed data).
  - `.env` still points at the hosted DB, so `pnpm dev` shows db unavailable. Use
    `DATABASE_URL=postgresql://setu:setu@localhost:5435/setu` locally.
- **Next phase reads:** this block, `docs/finance-formulas.md`, `app/schemas/analysis.py` (the `Amounts`
  pattern), `app/auth/deps.py`.

### 2.3 + 2.5 (from the user's "P06 FR-2 cash flow + dashboard" prompt)
- **Forecaster:**
  - Domain: `app/domain/cashflow.py` (`Flow`, `forecast`, `running_balance`, `apply_scenario`) and
    `app/domain/alerts.py` (rules + policy constants).
  - Services: `app/services/{cashflow,alerts,scenario,dashboard,scope}.py`; models in `app/schemas/cashflow.py`.
  - Sources: unlinked `cashflow_items` plus tranches and deal costs derived live from deals, milestones,
    escrow and `deal_costs`. The seed's linked copies are skipped, so nothing counts twice.
  - Financing-application repayments are **not modelled** (no table yet). P07 must add them to
    `load_book`.
- **Endpoints** (FastAPI paths; the web app uses `/api/...`):
  - `GET /cashflow/forecast?party_id=&days=&min_buffer=`
  - `POST /cashflow/scenario` (moves, removes, loans; validated to the window; saves nothing)
  - `GET /alerts?party_id=&status=`
  - `POST /alerts/recompute?party_id=`
  - `POST /alerts/{id}/acknowledge` and `POST /alerts/{id}/resolve`
  - `GET /dashboard?party_id=`
- **Alert rules + thresholds:** see `docs/finance-formulas.md`.
  - SHORTFALL: first day closing < `min_buffer` (default 0); CRITICAL if ≤ 7 days away, else WARNING.
  - DEADLINE: milestone 14/30 days, duty 7/60, bill of entry (arrival + 1 day) 7/60, loan instalment
    7/7. Each pair is action window / notice window: INFO inside the notice window, WARNING inside the
    action window, CRITICAL at T-1. The notice windows were added so the duty (T+45) and bill-of-entry
    (T+41) alerts your tests require exist at all. A milestone deadline is dropped when the shortfall
    alert covers that payment.
  - FX_OPPORTUNITY: next tranche per deal paid into a foreign-currency account; best day more than 1%
    below the 30-day mean.
  - Keys `alert:<party>:<type>:<ref>:<date>` (hashed if > 80 chars), id = uuid5(key).
  - Auto-resolve, reopen and resolve: an engine alert whose condition goes away is auto-resolved and
    reopens if it returns. A user-resolved or acknowledged alert reopens only if its severity rises or
    its amount grows.
  - Buyers may resolve engine types only. KYB/FRAUD alerts close via admin or when their check clears.
- **Seed change:** the seed writes only the KYB alert. `db:seed` and `db:reset-demo` run the engine for
  every buyer (`seed.cli.recompute_alerts`).
  - Run `pnpm run db:reset-demo` on older local DBs to drop the old hand-seeded alerts.
  - Rahima now has 6 open alerts: loan instalment WARNING; SHORTFALL **1,560.00** on 2026-11-07,
    WARNING (18 days away, per your ≤ 7-days-critical rule; P03 called it critical); FX on 2026-10-22
    (≈ BDT 13,014.68); bill of entry 2026-11-30; duty 800.00 on 2026-12-04.
  - Karim has no shortfall: deadlines, FX and KYB only.
- **Demo numbers:** Rahima's lowest balance is −3,835.00 on 2027-01-02, so `cover_amount` is 3,835.00.
  A 1,560.00 loan on 2026-11-05 clears the 2026-11-07 shortfall; the next one is freight on 11-08.
- **Auth:** `require_writer` (BUYER own + ADMIN); JUDGE is read-only. Another buyer's alert id returns
  404 (no existence oracle). All reads are buyer-scoped through `app/services/scope.py`.
- **Web:**
  - `/app` is now the Dashboard: KPIs, AlertPanel, pending approvals, mini chart, active deals, month.
    Login lands here.
  - `/app/cashflow`: chart, week calendar, day details, alert filters with acknowledge/resolve,
    what-if panel with Reset.
  - `/app/financing` is a placeholder that reads `amount`, `currency`, `date` and `deal` from the query.
  - `/app/approvals` is a placeholder.
  - Nav: Dashboard / Deals / Cash Flow / Financing / Analysis.
  - Reusable pieces: `components/cashflow/{AlertPanel,CashflowChart,CashflowCalendar,WhatIfPanel,BuyerScopeGate}`,
    `lib/api/cashflow.ts`, `whatIf.ts::buildScenarioRequest`.
- **Verified in a browser** (prod build → agent on the local DB):
  - Dashboard: $6,000 cash, $2,880 in escrow, the shortfall alert with $1,560, and the duty +
    bill-of-entry alerts. The shortfall action opens `/app/financing` with the prefill.
  - Cash Flow: the chart dips below 0 on 7 Nov; a what-if loan removes the red days and Reset restores
    them; acknowledge works.
  - Bangla toggle works; no horizontal scroll at 360 px; no console errors.
  - Next 16 keeps the previous route mounted but hidden (Cache Components), so a second hidden `<main>`
    can be in the DOM after client navigation.
- **Security review: PASS WITH FIXES, fixed.**
  - Fixed: KYB/FRAUD resolve permission; reopen on escalation; 404 instead of 403 for others' alerts;
    loan/move window validation; error text no longer echoes refs; long keys hashed.
  - **Open:**
    - (a) No audit-log entries for recompute, acknowledge and resolve; Phase 5.4 must append
      ALERT_* entries.
    - (b) Concurrent recomputes can collide on insert (500); use ON CONFLICT if it matters.
    - (c) `cashflow_items.description` and `deal_costs.note` flow into alert text and labels. Treat
      them as untrusted before free-text sources (uploads, email) exist.
- **Not done:** FR-7 USD-vs-CNY route comparison and rate lock (PLAN 2.3 task 3), financing repayments
  in the forecast, the approvals inbox (P17), alert recompute triggers on deal/milestone changes (no
  such endpoints yet).
- **Next phase reads:** this block, `docs/finance-formulas.md` (FR-2 section),
  `app/services/cashflow.py::load_book`, `components/cashflow/AlertPanel.tsx`.

### 2.2 + 2.6 financing half (from the user's "P07 FR-1 financing-option matching" prompt)
- **Domain:** `app/domain/financing.py`
  - Gap: `shortfall_gap`, `order_gap`.
  - Costing: `Terms`, `option_tenor`, `option_cost`.
  - Eligibility: `evaluate_rules`, `code_rules`.
  - Ranking and output: `rank`, `schedule`, `why_codes`, `pick_sentences`, `risk_notes`.
  - Formulas and tables are in `docs/finance-formulas.md` (FR-1 section).
- **Service:** `app/services/financing.py`. Models are in `app/schemas/financing.py` and the router in
  `app/api/financing.py`.
- **Migration** `70bf00166094` (the only one this phase) adds `financing_applications`. It is applied to
  the local and test DBs. **Run `pnpm run db:migrate` on the hosted DB** before pointing the dev agent at
  it. `reset-demo` wipes the table.
- **Endpoints:**
  - `GET /financing/gap?mode=shortfall|order&deal_id=`
  - `POST /financing/match`
  - `GET /financing/options/{code|id}/schedule?amount=&start=&deal_id=`
  - `POST /financing/impact`
  - `POST /financing/applications`: SUBMITTED. Idempotent per deal + option + mode while active, 409 if
    the amount differs; eligible options only.
  - `POST /financing/applications/{id}/simulate-approval`: re-checks eligibility, terms and dates at
    execution, otherwise REJECTED and 409. On success: APPROVED, `cashflow_items` `fin:<ref>:in` and
    `fin:<ref>:repay`, and an alert recompute.
  - `GET /financing/applications`
- **Ranking rules:** eligible first → total cost → shorter tenor → fewer conditions → code.
- **Eligibility:** the JSON rule tree (facts from `seed/financing.py`) plus `MIN_AMOUNT`, `MAX_AMOUNT`,
  `TENOR_FITS` and `NOT_WITH_FUNDED_ESCROW`.
- **Product rules chosen with the user to keep TC-09:**
  - (1) Insured open-account terms are not offered once a deal's escrow is funded.
  - (2) Ranged-tenor lines are priced at their maximum tenor (NBFI 120 days).
  - Also: `UNTIL_MILESTONE_3` = start → arrival + 5 days clearance (45 days from today for SETU-2026-0001).
- **TC-09:** `docs/SRS.md` does not exist, so TC-08/TC-09 are recorded in `docs/REQUIREMENTS.md` (new
  "Test cases" section).
  - **Order mode:** 5,200.00. Escrow-backed loan 97.70 (45 d), supplier credit 104.00, bank import loan
    173.45, NBFI line 239.34; insured terms are ineligible (escrow funded). The old 3,600 figure is
    replaced.
  - **Shortfall mode:** 1,560.00 needed by 2026-11-07, recovering 2026-11-19 (12 d), peak 2,160.00.
    Supplier credit 31.20, escrow loan 50.39, NBFI line 71.80; bank and insured are ineligible (minimum
    amount, plus escrow for insured).
- **Demo story caveat:**
  - Applying the 1,560 pick resolves the 2026-11-07 SHORTFALL alert, as the e2e test checks.
  - Rahima's 90-day forecast stays structurally negative (outflows 23.7k vs inflows 16.4k; the seed has
    no sale proceeds for the imported fabric). So a later, smaller shortfall alert (e.g. 600 on 11-08
    from freight) appears.
  - Adding projected sale receipts for SETU-2026-0001 to the seed would fix the story. Not done here;
    it changes the P03/P06 numbers.
- **Web:**
  - `/app/financing` (`components/financing/*`): mode switch, deal picker, gap card, ranked option cards
    with recommended highlight and why-not, schedule and impact dialogs, apply dialog that auto-approves
    after 1.5 s (simulated), applications list.
  - Shared `components/ui/Modal.tsx` (focus trap, Esc, focus return). Deal detail links to
    `?deal=&mode=order`.
  - The option name, collateral and conditions come from the catalogue and stay English in bn.
- **e2e:** specs now run serially (`workers: 1`). `e2e/global-setup.ts` runs `seed.cli reset-demo` when
  `E2E_RESET_DEMO=1`, with `DATABASE_URL` pointing at the local DB (reset refuses non-local DBs).
  Command: `DATABASE_URL=postgresql://setu:setu@localhost:5435/setu E2E_RESET_DEMO=1
  E2E_BASE_URL=http://localhost:3100 pnpm --dir apps/web e2e`, against a build whose
  `AGENT_URL` points at an agent using the local DB.
- **Security review: PASS WITH FIXES, fixed.**
  - Fixed: execution-time re-check and REJECTED, 409 for non-active apps, row lock on approval, 409 on
    re-POST with a different amount, 400 for zero amounts, references from max+1, EAR capped at 999,900%.
  - **Open, for 5.x:**
    - (a) simulate-approval / acceptance must go through `PendingApproval(ACCEPT_FINANCING)`: Tier 2 by
      default; Tier 3 above USD 20,000 or for ESCROW_BACKED_LOAN (it assigns escrow tranches), with a
      `params_hash` over app, option, amount, tenor, dates and schedule. It must never be an LLM tool.
    - (b) No audit entries for apply/approve (5.4).
    - (c) `code_rules` compares amount vs min/max in the buyer currency without checking the option
      currency (latent; all USD).
    - (d) The idempotency check is not atomic under concurrency (no partial unique index).
    - (e) Another buyer's deal gives 403 vs 404 for a missing one (kept consistent with P05).
- **Next phase reads:** this block, `docs/finance-formulas.md` (FR-1), `app/services/financing.py`
  (`quote_all`, `simulate_approval`), `components/financing/OptionCard.tsx`.

### 3.3 (from the user's "P08 LangGraph agent skeleton" prompt)
- **Branch / worktree:** `phase/3.3-agent-skeleton`, built in the worktree `/data/setu-3.3`, because another
  session was editing phase 2.2 (financing) in `/data/Setu` at the same time. **Merge order:** both branches add
  an Alembic revision on top of `60340801e54e` (mine: `b7c1a9e4d2f0`; 2.2's financing migration: `70bf00166094`).
  Whichever merges second must set its `down_revision` to the other one (or add a merge revision).
  **Done in P09:** 2.2 reached `main` first, so `b7c1a9e4d2f0` now revises `70bf00166094`.
- **Layout (from the prompt; it overrides PLAN's `app/graph`/`app/tools` names):** `app/agent/{state,intents,
  prompts,registry,mock_llm,models,nodes,graph,persistence,runner}.py`, `app/agent/tools/readonly.py`. The router
  is `app/api/chat.py` (the existing `app/api` convention, not `app/routers`). Models: `app/llm/client.py` is
  still the **only** module that imports `langchain_anthropic` (a test enforces it). `models.py` picks the real or
  the mock model. Tracing: `app/llm/tracing.py`.
  Security seams: `app/security/tiers.py` (`Tier`, `MAX_LLM_TOOL_TIER = T0`), `injection.py`
  (`detect_instructions`, EN/BN/ZH patterns), `privacy_gateway.py` (identity stub, `TODO(P18)`),
  `audit.py::record_event` (structlog + in-memory `RECENT_EVENTS`, `TODO(5.4)`: signed chain append).
- **Graph:**
  ```mermaid
  flowchart LR
    S((start)) --> L[load_context] --> P[privacy_gateway<br/>stub, TODO P18] --> R[router<br/>fast model, json_schema<br/>keyword fallback]
    R -- greeting / out_of_scope / budget --> X[respond]
    R -- other intents --> A[agent<br/>fast or smart model + allow-listed tools]
    A -- tool_calls --> T[tools<br/>registry.guard]
    T -- more steps --> A
    T -- injection flag / 6-step cap --> X
    A -- READY / budget / model error --> X
    X --> E((END))
  ```
  - The agent node only gathers facts. It replies `READY`, and its text is never shown. `respond` writes the
    answer from the `<tool_result untrusted="true">` blocks, in the turn language. `<` inside a payload is
    escaped, so data cannot close the tag.
  - Code then appends to the answer: the simulated-data note (when tools returned data), the injection warning,
    the tool-cap note, and a "no money moved" line if the model claims a release or payment.
  - `documents` intent (or `needs_smart_model`) uses MODEL_SMART for agent and respond.
- **Tier guard (`registry.guard`):**
  - Refuses any tool with `max_tier > 0` with `{"code":"requires_approval_flow","tier":N}` before validation or
    execution. Also refuses unknown or non-allow-listed tools (`INTENT_TOOLS`).
  - Validates args and output with pydantic `extra=forbid`. Runs each tool as a LangSmith tool run
    (tags `setu, tool, <tier>`). Scans string values for instructions. Writes `record_event` for every call or
    refusal.
  - An injection finding sets `stop_reason="injection"`, so no further tool calls happen in that turn (enforced
    in code, not by the prompt). It also records an `INJECTION_DETECTED` Tier 3 event.
- **Tools (Tier 0):**
  - `get_dashboard_snapshot(party_id?)` wraps `services.dashboard` and returns home-currency strings.
  - `get_deal_summary(deal_id)` takes a ref or UUID matching `^[A-Za-z0-9-]+$`. Another buyer's deal gives
    `not_found` (no oracle).
  - `explain_how_setu_works()` returns static text.
- **Persistence:**
  - Migration `b7c1a9e4d2f0` adds: `chat_messages.role` `tool`, `chat_messages.meta` JSONB (intent, model,
    tool, ok, args summary, usage, run id), `chat_threads.deal_id`, `tokens_used` and `updated_at`.
  - It also creates the LangGraph checkpoint tables with the exact langgraph-checkpoint-postgres 3.2.0 DDL and
    fills `checkpoint_migrations` (0–9), so `PostgresSaver.setup()` is never needed. Alembic stays the schema
    owner (`alembic/env.py` ignores those 4 tables; `alembic check` clean).
  - A test fails if the library's `MIGRATIONS` count changes. **Bumping langgraph-checkpoint-postgres needs a
    new migration.**
  - Checkpointer: `PostgresSaver` on a psycopg pool (`prepare_threshold=0` for pgbouncer/Neon), keyed by
    `thread_id` = `chat_threads.id`. Without DATABASE_URL it falls back to `InMemorySaver`.
  - Tool results are stored through `mask_for_storage` (identity until P18).
- **API** (FastAPI paths; the web app uses `/api/...`; `make types` regenerated `schema.gen.ts`):
  - `POST /chat` `{thread_id?, message (≤4000), language? en|bn|zh, deal_id?}` →
    `{thread_id, answer, intent, model_used, language, tool_calls[{name,args_summary,ok}],
    usage{input,output,total,thread_total,thread_budget}, stopped, trace_url, simulated}`.
  - `POST /chat/stream` (SSE): `meta {thread_id,intent,model,language}` → `tool_start {name,id}` /
    `tool_end {name,id,ok,args_summary,error_code}` → `token {text}`… → `final <ChatResponse>`, or `error
    {code,message}`. The tokens joined equal `final.answer`. A static answer comes as a single token. Headers
    are `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. It uses FastAPI's built-in
    `fastapi.sse.format_sse_event` with `StreamingResponse`, so there is no sse-starlette dependency.
  - `GET /chat/threads?user_id=` (only your own id; anything else gives 403) and
    `GET /chat/threads/{id}/messages`. Another user's thread gives 403 on read, post and stream.
  - All endpoints need the demo session (401 otherwise).
  - `trace_url` is returned to ADMIN and JUDGE only, when tracing is on.
- **Language:** the request `language`, else the message script (Bangla → bn, Chinese → zh, Latin → en),
  else the thread's language. (Rahima's profile is `bn`, but an English message gets an English answer.)
- **Env vars** (in `.env.example`): `AGENT_MOCK_MODE`, `MODEL_FAST`, `MODEL_SMART` (`SETU_MODEL_FAST` and
  `SETU_MODEL_REASONING` are still accepted as aliases), `LLM_MAX_TOKENS` 2048, `LLM_TIMEOUT_SECONDS` 30,
  `LLM_MAX_RETRIES` 2 (SDK exponential backoff), `THREAD_TOKEN_BUDGET` 60000, `AGENT_MAX_TOOL_STEPS` 6,
  `LANGSMITH_*`. I also added `APP_ENV`, `DEMO_SESSION_SECRET` and `DEMO_COOKIE_SECURE`, which P05 left out.
  - **Mock mode** is on when `AGENT_MOCK_MODE=true` **or the key is missing or blank**. `MockChatModel` is
    deterministic: keyword router, keyword tool choice, answers composed from tool JSON in EN/BN/ZH, word
    streaming, estimated token usage.
- **Models:** `claude-haiku-5-5` (fast: router, agent, respond) and `claude-sonnet-5-5` (smart: documents).
  The router uses `with_structured_output(method="json_schema")` because Sonnet 5.5 rejects forced
  `tool_choice`.
- **Pinned versions (uv.lock):** langgraph 1.2.15, langgraph-checkpoint 4.3.0, langgraph-checkpoint-postgres
  3.2.0, langchain-core 1.6.12, langchain-anthropic 1.7.6, anthropic 1.15.0, langsmith 0.14.11, psycopg 3.3.6,
  psycopg-pool 3.3.3, FastAPI 0.143.3. `langchain-core`, `langgraph-checkpoint` and `psycopg-pool` are now
  direct dependencies.
- **Verified:**
  - Mock mode: curl `POST /chat "hello"` works offline. Rahima's "What's on my dashboard?" gives USD 6,000.00
    cash, 2,880.00 in escrow and a **1,560.00 shortfall on 2026-11-07**, in English and Bangla. `curl -N` on
    `/chat/stream` shows tokens arriving one by one.
  - LangSmith (real key, mock model): the root run `setu-chat` is in project `setu` with tags `[setu, phase-P08,
    intent:…, model:…]` and metadata `{user_role, thread_id}`. Tool child runs are tagged. The judge got the run
    URL.
  - **Not verified with a real Claude model:** `ANTHROPIC_API_KEY` in the local `.env` is empty, so the service
    fell back to mock mode. Set the key and rerun the two dashboard questions as Rahima (EN + BN).
- **Security review (security-reviewer): PASS WITH FIXES, no critical or high findings.** Fixed:
  - (M1) Token budget bypass by disconnecting mid-stream. `abort_turn` now charges the checkpointed usage
    plus the streamed text, on error, `GeneratorExit` or GC, and writes an `aborted` assistant marker.
    `add_tokens` is an atomic `UPDATE … RETURNING`, and `append_message` locks the thread row for `seq`.
  - (L3) Tool names from the model are checked against `^[A-Za-z0-9_]{1,64}$` (else `invalid_tool_name`).
  - (L4) Conversation and user text in the respond prompt are escaped, so `<tool_result>` cannot be forged.
  - (L5) The detector applies NFKC and strips zero-width characters, and adds the `MONEY_TO_ACCOUNT` and
    `APPROVAL_COMMAND` rules (no hits on the seeded alert texts).
  - (L6) The model is only offered tools at or below the tier ceiling, and the tier check runs before the
    allow-list.
  - (L7) The dashboard tool returns the same `not_found` for any foreign, unknown or invalid `party_id`.
  - (L8) Each tool call runs in a DB savepoint, so a DB error becomes `tool_failed` and the turn still saves.
  - **Open (M2, for P18):** the Privacy Gateway node masks only the latest user message. The system prompt
    (names, deal refs), tool results and history reach the model, and LangSmith, unmasked. P18 must mask
    every model input inside `app/llm/client.py` (security.md §3) and extend the "no raw PII reaches the
    model" test to system and tool content.
  - Accepted: two turns in parallel on one thread can each start under the budget (overshoot ≤ 1 turn).
- **Tests:** `tests/agent/` has 58 tests (no DB, no network). They cover node order, the privacy gateway
  running before the first model call, the tool loop, Tier 1/2/3 refusal, injection, Bangla, out of scope,
  documents → smart, router fallback, the budget (at start and mid-turn), model failure, the 6-step cap,
  checkpoint resume, the detector, and the import boundary. They also cover hostile tool names, forged
  results in user text, and tier-filtered tool offers. `tests/api/test_chat_api.py` has 16 db tests: offline,
  dashboard numbers, BN, deal isolation, SSE order, persistence + resume, 403s, budget, 401/422, SSE
  disconnect still charging tokens, the atomic token counter, `trace_url` by role with tracing on, the party
  oracle, and a tool DB error.
  DB tests ran on `TEST_DATABASE_URL=…/setu_p08_test`, not `setu_test`, to stay clear of the parallel session.
- **Known gaps:**
  - No LLM cache (PLAN 3.1).
  - Privacy masking is a stub covering only the user message (see M2 above), and LangSmith traces contain
    raw prompts and tool outputs until P18. Don't enable tracing with real PII.
  - The audit seam does not append to the signed chain yet (5.4).
  - No RAG/citations (`citations` stays empty; P10).
  - The mock router equals the keyword fallback.
  - `GET /chat/threads` has no pagination.
  - Thread titles are the raw first message (≤ 80 chars).
  - Chat history is not shown to ADMIN/JUDGE (by design: own threads only).
- **Next phase reads:** this block, `app/agent/registry.py` (how to add a tool: `@REGISTRY.tool(...)` + an
  `INTENT_TOOLS` entry), `app/agent/nodes.py` (respond input format), `app/schemas/chat.py` (SSE payloads).

### 3.4 (from the user's "P09 Core finance tools + Chat UI" prompt)
- **Branch:** `phase/3.4-chat-tools` (worktree `/data/setu-3.3`), branched from `phase/3.3-agent-skeleton` with
  `main` (2.2 financing) merged in. That merge re-parented `b7c1a9e4d2f0` onto `70bf00166094` (one Alembic head).
  **P08 and P09 reach `main` together when this branch merges.** `docs/SRS.md` still does not exist, so the
  prompt's SRS 5.2 / FR-9 references map to `docs/REQUIREMENTS.md`.
- **Tools** (`app/agent/tools/finance.py`, all `max_tier=0`, registered on the P08 registry; 13 tools in
  total, and a test asserts every one is Tier 0 and allow-listed). Each returns a card
  `{card_type, data, explanation_codes, explanation_en, explanation_bn, simulated}` (`app/schemas/cards.py`):
  | tool | card | service |
  |---|---|---|
  | `analyze_order(deal_id?)` | landed_cost | `analysis.order_analysis` |
  | `landed_cost_what_if(goods_value, quantity, unit, currency, cost_lines, selling_price?)` | landed_cost | `analysis.what_if` |
  | `forecast_cashflow(days=90)` | cashflow (series, first shortfall, lowest, 5 biggest payments in 30 d) | `cashflow.get_forecast` |
  | `simulate_cashflow_scenario(moves, removes, loans, days)` | cashflow before/after | `scenario.run` |
  | `get_alerts(status=OPEN)` | alerts (severity-sorted, safe routes) | `alerts.list_alerts` |
  | `match_financing(deal_id?, mode)` | financing_comparison (ranked, recommended + reasons, why_not, apply_route) | `financing.match` |
  | `financing_impact(option_id, amount, deal_id?, mode)` | cashflow before/after | `financing.impact` |
  | `compare_fx_route(amount?, from_currency=BDT, to_currency?, deal_id?)` | fx_compare | `services/fx_route.compare` → `domain/fx_route.py` |
  | `get_monthly_summary(month?)` | monthly_summary | `analysis.monthly` |
  | `get_supplier_scorecard()` | scorecard | `analysis.suppliers` |
  - **Deal resolution:** the explicit `deal_id`, else the chat's "About deal" scope (`ToolContext.deal_ref`),
    else the most recent in-flight deal, with drafts last (`defaulted_deal=true`, and the answer says which).
    Shortfall-mode financing without a deal leaves the choice to the service, which takes the deal behind
    the first shortfall.
  - **Isolation:** another buyer's deal gives `not_found` (explicit, scoped or impact). Admin and judge get a
    clean `bad_request` from buyer-scoped tools. A test shows the 10 tools write nothing (row counts are
    unchanged).
  - **No action tools:** `apply_financing` and rate lock are not tools. A model call to them is refused
    (`unknown_tool`). The Apply button only links to `/app/financing`.
- **FR-7 (new):** `domain/fx_route.compare_routes` covers the USD route (bank USD spread, supplier-side
  USD→CNY spread, SWIFT and correspondent fees) and the direct CNY route (CNY spread, flat fee). Mid rates come
  from `fx_rates`. The spreads and fees are **MOCK** constants and are labelled `MOCK:` in `assumptions`.
  Golden example: USD 5,760 → USD route BDT 718,223.24 vs CNY route 712,766.14, saving 5,457.10 (0.76 %). The
  rate lock is still not built (Tier 2, Phase 5).
- **Agent behaviour:**
  - The agent prompt maps question types to tools and covers the default-deal and clarifying-question rules
    (`agent@2`).
  - The respond prompt asks for 2–5 sentences plus a "Why:" line from the explanation fields, and natural
    Bangla that keeps common English finance terms (`respond@2`).
  - Code guarantees the Why line: the model's text is kept verbatim, and a missing line is appended from
    the card explanation, in the turn language. It is **never** taken from a flagged result (then a generic
    fallback is used).
  - The model sees cards without `series`/`history` (`ToolOutcome.model_payload`), but the UI gets the full
    card. Earlier answers are escaped in the agent's history.
  - Keyword router and mock: analysis before deal status; FX, alert, Bangla financing and summary keywords.
    The mock picks all the new tools and writes card summaries in EN and BN.
- **API changes** (`make types` was run):
  - `ChatResponse` gains `message_id`, `why`, `notes`, `cards[]`. The SSE `tool_end` event carries `card`.
  - `MessageOut` gains `id` and `card` (for tool rows).
  - New endpoints: `GET /chat/threads?q=` (ILIKE, escaped), `PATCH /chat/threads/{id}` `{title}`,
    `DELETE /chat/threads/{id}` (checkpoints first, then the thread and its messages), and
    `POST /chat/messages/{id}/feedback` `{rating: up|down, comment?}`. Feedback is stored in `meta.feedback`;
    missing, someone else's and non-assistant messages all give 404.
- **Web** (`apps/web`, built by the frontend-builder agent):
  - `/app/chat` has a thread list (new, rename, delete, search) and a message stream. Streaming uses
    `src/lib/sse.ts` with `src/lib/api/chat.ts`, with typing indicator, tool chips, stop and retry.
  - Messages have a body (markdown-lite, no raw HTML), the Why line, notes, a Simulated tag, copy, and 👍/👎.
  - Suggested EN/BN chips, the existing language toggle, an "About deal" selector, and the footer disclaimer.
  - `ChatDrawer` is on every `/app` page except the chat. It is scoped to the deal on `/app/orders/[id]` and
    on `/app/financing?deal=`, and has an "Open full chat" link.
  - Cards are in `components/chat/cards/`: LandedCost, Cashflow (Recharts, shortfall zone, before/after),
    Alerts, FinancingComparison, FxCompare, MonthlySummary, Scorecard.
  - Links render only for internal `/app` routes (`safeAppHref`), and the Apply link only for `/app/financing`.
  - The nav has a Chat item, and the `chat.*` i18n strings keep en/bn parity.
- **Verified (mock mode):**
  - All four suggested questions (EN and BN) route to the right tool and card with a Why line:
    - cash-flow card: shortfall 1,560.00 on 2026-11-07;
    - landed cost: 11,200.00, margin 18.01 %;
    - cheapest financing: supplier credit 31.20 for the shortfall; for the order, the escrow loan 97.70 →
      supplier credit 104.00 → bank loan 173.45;
    - FX: CNY is cheaper for M1 of SETU-2026-0001.
  - Playwright `chat.spec.ts` asks in Bangla, sees the CashflowCard with 1,560, and opens the drawer from the
    dashboard. There is no horizontal scroll at 360 px (en and bn).
  - **Not verified:** a real Claude run and LangSmith tool-call traces for these questions.
    `ANTHROPIC_API_KEY` in `.env` is still empty, so the agent runs in mock mode. Set it, then ask the four
    questions in EN and BN.
- **Security reviews (security-reviewer):**
  - **Backend: PASS WITH FIXES, fixed.**
    - (H) The narrowed `MONEY_TO_ACCOUNT` missed fake-supplier payment requests. It now has three branches:
      a request or sentence-start verb plus an amount, verb → to/into/via a destination, and verb plus an
      account number (spaces and dashes allowed). Seven attack phrases are caught, and our own card text and
      the seeded text are not flagged.
    - (M) Flagged results never feed the Why line, and prior answers are escaped in the agent history.
    - (L) Feedback 404s are uniform, checkpoints are deleted first, and the FX assumptions say MOCK.
    - Open: privacy masking (P18). Tool runs and cards now carry supplier names and amounts to LangSmith
      and the model.
  - **UI: PASS WITH FIXES, fixed.** Fixes: the Apply route is restricted to `/app/financing`, thread ids are
    UUID-checked and encoded, the SSE event parser and card shapes are hardened, the SSE buffer and answer
    length are capped, and the drawer's percent-decoding is safe.
- **Known gaps:**
  - The chat threads in the seed have `meta: null`, so they show no separate Why or notes.
  - At 360 px the scorecard table's last column scrolls inside the card.
  - The `useChatSession` hook has no direct unit test; the stream path is covered by the parser tests and e2e.
  - No LLM cache.
  - FX route spreads and fees are mock constants.
  - The forecast stays structurally negative (lowest −3,835.00), as noted in P07.
  - Financing option names and conditions stay English in Bangla answers (catalogue text).
- **Next phase reads:** this block, `app/schemas/cards.py` (add a card type: the model, the `Card` union,
  `CARD_TYPES`, the UI dispatcher `components/chat/cards/ChatCard.tsx`), `app/agent/registry.py`
  (`INTENT_TOOLS`), `app/agent/nodes.py` (`_respond_input`, `_finalize`), `app/agent/state.py`
  (`citations`).

### 3.2 (from the user's "P10 RAG knowledge base with citations" prompt)
- **Branch:** `phase/3.2-rag` (worktree `/data/setu-3.3`), on top of `phase/3.4-chat-tools`. It was merged to
  `main` with P08 and P09 (`--no-ff`).
- **KB sources** (`services/agent/kb/sources/`, our own summaries, about 3,900 words plus the generated
  catalogue):
  - `bb-advance-payment` (regulation_summary)
  - `incoterms-basics`, `trade-document-fields`, `financing-glossary` (glossary)
  - `setu-how-it-works`, `faq-bn` (product_doc, Bangla)
  - `generated/financing-catalogue` (catalogue, from `financing_options` by `npm run kb:sync`)

  Each file has YAML front-matter: `id`, `title`, `source_type`, `original_reference`, `language`,
  `last_reviewed`, `disclaimer`. The Bangladesh Bank figures are as given in the prompt (USD 20,000;
  raised from USD 10,000 in Sept 2025; FEPD circular of 13 Aug 2026). They are **not independently
  verified**, are marked "simplified summary for demo — verify with the official circular", and no circular
  number is invented. A native speaker should review the Bangla FAQ.
- **Embeddings:** fastembed has no `multilingual-e5-small`, so the KB uses
  **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (384-d, which fits the existing
  `Vector(384)`; Apache-2.0, 50+ languages including Bengali). It runs locally through fastembed with no paid
  API and is cached in `~/.cache/setu-fastembed` (`KB_MODEL_CACHE_DIR`, about 240 MB). It needs no e5
  prefixes. `KB_EMBEDDER=hash` gives a deterministic offline stub (all tests default to it). The licence is
  in the README.
- **Schema:**
  - Migration `c4d2e8f1a9b3` (revises `b7c1a9e4d2f0`) rebuilds the empty `kb_chunks` table: `source_id`,
    `seq`, `title`, `heading_path`, `content`, `language`, `content_hash`, `embedding vector(384)`,
    `metadata` JSONB, and `tsv` (a generated `to_tsvector('simple', title‖heading‖content)`).
  - Indexes: HNSW (`vector_cosine_ops`) and GIN on `tsv`. `alembic check` is clean.
  - Alembic stays the schema owner; the prompt's "Prisma migration" does not apply here.
- **Indexing** (`app/rag/chunker.py`, `ingest.py`, `cli.py`; `npm run kb:index` / `make kb-index`):
  - Sections are split by `##`/`###`, about 300–450 tokens (estimated as words × 1.3), with a 40-token
    overlap when a section is split. Tiny sections and intros fold into the next one.
  - Every chunk keeps "Title > Section > Sub".
  - Idempotent by `content_hash` (model id + heading path + text): an edit re-embeds only the changed
    chunks, and a deleted source removes its chunks. The current KB is 7 sources and 59 chunks.
- **Retrieval** (`app/rag/retrieve.py`):
  - Vector top 20 (cosine ≥ 0.30) plus full-text top 20 (`to_tsquery('simple')`, OR of the prefix terms,
    with stop words dropped in EN and BN). The two lists are merged with RRF (k = 60) and return the top 4.
  - Passages in the requested language score × 1.25.
  - If the model is missing, retrieval falls back to full-text only.
  - Every candidate goes through the injection detector. A flagged passage is **withheld**, and its codes
    are reported in `security_flags`, which the registry turns into the turn's injection flags.
  - A test asserts that all our own KB chunks pass the detector, so a bad edit fails CI. Two passages were
    reworded for this.
  - The retrieval table is top-1 correct with the real model for: the advance payment limit, FOB, bill of
    lading fields, escrow, and the Bangla advance-limit question.
- **Agent:**
  - Tool `search_knowledge(query, language?)` is Tier 0 and allow-listed for every agent intent. It
    returns a `citations` card.
  - The model sees `<retrieved_document cite_id="S1" source_id="…">` blocks (escaped) inside the
    untrusted `<tool_result>`.
  - Cite ids are unique per turn across several searches (S1…S4, then S5…).
  - The respond prompt (`respond@3`, `CITE_RULE`) says to cite `[S#]` and only from retrieved passages.
    `state.citations` keeps only ids that were actually retrieved and not flagged.
  - `ChatResponse.citations[]` holds `{cite_id, source_id, title, heading_path, source_type,
    original_reference, last_reviewed, disclaimer}`, also stored in `meta.citations`.
  - Answers that come only from the KB get no "simulated figures" note.
  - The mock model picks `search_knowledge` for rule and definition questions and answers from the top
    passage with `[S1]`.
- **UI:** citation chips `[S1]` in the answer, a Sources / উৎস list under the message, a withheld-passage
  notice, and KB suggestion chips.
- **Verified (mock mode, real embeddings):**
  - The four example questions and the Bangla FAQ questions answer with `[S1]` from the right source.
  - `kb:index` re-run gives `+0 embedded, 59 unchanged`.
- **Security review (security-reviewer): PASS WITH FIXES, all fixed.**
  - (M1) The user's own query was echoed in the card and scanned as untrusted data, so "release the
    tranche?" flagged the turn. The card no longer carries the query.
  - (M2) A missing model triggered a download or a failure on every request. Now the request path never
    downloads (`get_embedder()` returns None and search runs full-text only, with the failure cached);
    only `kb:index` may download.
  - (L) The vector query runs in a savepoint, so a failure falls back to full-text.
  - (L) Detection covers title, heading, content and meta; withheld entries are id + codes only.
  - (L) `<retrieved_document>` attributes are escaped.
  - (L) The indexer refuses symlinks, non-mapping front-matter, unknown languages, duplicate ids and
    instruction-like sources.
  - (L) Catalogue values are collapsed to one line.
- **Known gaps:**
  - A real Claude run is untested (the key is empty).
  - The hash stub is plumbing-only (ranking quality is tested with the real model).
  - The KB content is unreviewed by a domain expert.
  - No `docs/SRS.md`, so the 1.4 / 6.3 references were not checked.
  - The first `kb:index` downloads the model (needs network once).
- **Next phase reads:** this block, `app/rag/retrieve.py` (tuning constants), `app/agent/tools/knowledge.py`,
  `kb/sources/*` front-matter format.

### 3.1b OpenRouter provider (from the user's switch of ANTHROPIC_API_KEY to OPENROUTER_API_KEY)
- **What changed:** `app/llm/client.py` (still the only place models are built) now supports two providers
  for the same Claude models. `Settings.active_llm_provider`: `LLM_PROVIDER=auto` picks Anthropic when
  `ANTHROPIC_API_KEY` is set, else OpenRouter when `OPENROUTER_API_KEY` is set, else mock mode. OpenRouter
  uses `ChatAnthropic` against its Anthropic-compatible endpoint (`OPENROUTER_BASE_URL`, default
  `https://openrouter.ai/api`) with a bearer header; model ids are mapped
  (`claude-haiku-5-5` → `anthropic/claude-haiku-5.5`, `claude-sonnet-5-5` → `anthropic/claude-sonnet-5.5`).
  `model_used` in responses shows the id actually called.
- **Verified live (real Haiku 5.5 via OpenRouter, local DB):** plain text, structured router output
  (`json_schema`), tool calls, and 12 EN/BN questions through `/chat`:
  - dashboard and cash flow: shortfall USD 1,560.00 on 2026-11-07, lowest balance quoted from the forecast;
  - landed cost: USD 11,200.00, margin 18.01 %;
  - financing: supplier credit 31.20 cheapest for the shortfall, default deal stated;
  - FX: CNY route saves BDT 4,373.88 (1.21 %) on milestone 1;
  - KB: advance limit USD 20,000 with `[S2]`/`[S3]`, FOB in Bangla with `[S1]`/`[S2]`.
  Each answer used the right tool and card, and ended with a "Why:" line in the user's language. LangSmith
  traces appear in project `setu` (URL returned to admin/judge only).
- **Observations:** a turn costs about 8k–15k tokens (system prompt + 14 tool definitions), so the default
  `THREAD_TOKEN_BUDGET=60000` allows only about 4–6 turns per thread; raise it for demos. Latency is 8–15 s
  per turn with a tool round trip.
- **Tests:** a developer's real key no longer reaches tests (autouse mock mode); provider selection and
  model-id mapping are tested.

### 1.3 (from the user's "P11 Synthetic trade-document generator" prompt)
- **Branch:** `phase/1.3-synthetic-docs`. `docs/SRS.md` still does not exist, so FR-6 / metrics come from `docs/REQUIREMENTS.md`
  (NFR-4). The prompt's `services/agent/synthetic/` and `data/` layout override the skill's older `synth/` sketch
  (the skill file now points at the new layout). Full reference: **`docs/synthetic-data.md`**.
- **Run (repo root):** `uv run --directory services/agent python -m synthetic.generator --clean 100 --tampered 100 --seed 42`
  (about 7 s, 35 MB, prints the count table); `--demo` rewrites only `data/demo/SETU-2026-0001/`; `--no-attacks`, `--out DIR`.
  Same seed gives identical manifest and bytes. Tests: `uv run --directory services/agent pytest -q tests/synthetic`.
- **Files** (`services/agent/synthetic/`): `generator.py` (CLI, pipeline, split, summary), `models.py` (pydantic docs, `Pack`,
  `DealTerms`, manifest), `render_pdf.py` (reportlab, extractable text, per-pack font/date-format/field-order variation),
  `render_photo.py` (Pillow + numpy swatches with a tape-measure width), `tamper.py` (one mutator per fraud type),
  `attacks.py`, `demo.py`, plus `catalog.py` (fictional master data, price bands), `factory.py` (plans to packs), and
  `validator.py` (the ground truth). New direct deps: `pillow`, `numpy` (reportlab and pdfplumber were already there).
- **Output** (`data/generated/`, now fully git-ignored): `manifest.jsonl`, `price_bands.json`, `packs/PACK-xxxx/` (6 PDFs + JSON,
  2 JPEGs, `deal.json`), `attacks/` + `attacks_manifest.jsonl`. Pack ids are shuffled, so the id does not leak the label.
- **Counts (seed 42):** 100 clean + 100 tampered = 200 packs; 100 dev / 100 test. Each of the 10 fraud types has 5 obvious +
  5 subtle, split 3/2 or 2/3 (stratified, `SPLIT_SEED = 20261020`); 20 tampered packs carry a secondary type. Attacks: 25 =
  5 styles × 5 variants (plain, plain, spaced, homoglyph, zero-width; en/zh/bn; 4 actions per style cover all 5 target actions).
- **Checks** in every manifest line (11): QUANTITY_MATCH, VALUE_MATCH, VESSEL_DATE_MATCH, NAME_MATCH, DUPLICATE_INVOICE,
  PRICE_IN_BAND, BENEFICIARY_MATCH, HIDDEN_TEXT_SCAN, INSTRUCTION_SCAN, PORT_MATCH, HS_CODE_MATCH. `HIDDEN_INSTRUCTION` fails
  both HIDDEN_TEXT_SCAN and INSTRUCTION_SCAN (same names as the seed's checks). A pack's checks come from `validator.validate`;
  a test cross-checks them with `tamper.EXPECTED_FAILS`.
- **Split policy:** P14 may tune only on `dev`; P24 reports on `test`. Stratified by clean and fraud type × difficulty.
- **Demo files** (`data/demo/SETU-2026-0001/`, committed, 13 files): see `data/demo/README.md`. `prefinanced_invoice.pdf` is a
  byte copy of `proforma_invoice.pdf`, so its sha256 equals the seeded registry value: `c912b855…3026`.
  Verified by a test and by re-running `db:seed` + `verify_seed` (18/18) on the local DB. `proforma_invoice_resaved.pdf` is the
  near-duplicate; `bill_of_lading_forged.pdf` has the wrong vessel, on-board 14 Oct and hidden white text.
- **Decisions:**
  - (1) Demo file names follow the seed (`bill_of_lading_clean|forged.pdf`, `production_photo_N.jpg`), not the prompt's
    `forged_bill_of_lading.pdf`.
  - (2) `prefinanced_invoice.pdf` is the registered PI itself, so the seed needed no change.
  - (3) The PI carries the booked vessel/voyage, production-completion date, ETA and shipment date, so P14 can check the B/L
    from documents alone.
  - (4) Bangla attacks are emails (no portable Bangla font in the repo); Chinese ones use reportlab's built-in `STSong-Light`.
  - (5) Hidden text sits at the page bottom so it extracts on its own line.
  - (6) A duplicate is a clone of a clean pack, so only DUPLICATE_INVOICE fails.
  - (7) Photos use "-" not "–" in the footer text (PIL's default font lacks the en dash).
- **Visual check:** 4 pages rendered with `pdftoppm` (a clean packing list, a tampered invoice, the demo invoice and the forged
  B/L). They look like real documents. The white text is invisible on screen but present in `pdftotext` output.
- **Security review:** not run: the diff touches no `app/security`, `tools`, `graph`, `llm`, escrow or approvals code.
- **Local DB:** the dev docker DB was one migration behind, so I ran `alembic upgrade head` on `localhost:5435` before re-seeding.
- **Known gaps:**
  - (a) Demo dates are fixed for `DEMO_TODAY = 2026-10-20`.
  - (b) PII corpus (skill step 6) is not built: Phase 5.2/7.1 need it.
  - (c) Photo-vs-spec mismatches (cut-if-late) are not a fraud type; photos always match.
  - (d) Duty rates, price bands and HS codes are illustrative.
  - (e) PDFs are single page and text-based; there are no scanned or image-only variants for OCR.
  - (f) `tests/api/test_chat_api.py::test_tool_db_error…` fails without a reachable Postgres (it passes with the local DB): unrelated to this phase.
- **Next phase reads:** this block, `docs/synthetic-data.md`, `data/demo/README.md`, `synthetic/models.py` (field names the
  extractor must recover), `synthetic/validator.py` (check semantics), `seed/documents.py` (checks the seed expects).

### 4.2 (from the user's "P12 Supplier KYB" prompt)
- **Branch:** `phase/4.2-kyb` (from `main` after P11 merged). `docs/SRS.md` still missing: FR-4 is in `docs/REQUIREMENTS.md`; TC-01 is
  covered by tests. Full reference: **`docs/kyb.md`** (checks, thresholds, score, endpoints, design decisions).
- **Engine:** `app/domain/kyb.py` (pure: name normalisation incl. suffix canon, 有限公司, Cyrillic/Greek/zero-width folding;
  rapidfuzz score = floor2((token_set + token_sort)/2); checks; aggregation), `app/services/kyb.py`, `app/services/suppliers.py`,
  `app/schemas/kyb.py`, `app/api/{kyb,suppliers}.py`, tool `app/agent/tools/kyb.py`. Thresholds in settings:
  `kyb_match_threshold` 92 (PASS), `kyb_partial_threshold` 80 (WARN), below FAIL; account age <7 d FAIL, <30 d WARN.
- **Checks:** LICENSE_VS_INVOICE_NAME, LICENSE_VS_ACCOUNT_HOLDER, ACCOUNT_TYPE, ACCOUNT_AGE, ACCOUNT_COUNTRY,
  PENDING_BENEFICIARY_CHANGE, REGISTRY_HISTORY, SANCTIONS_SCREEN (+ DOC_INSTRUCTION FAIL when an invoice name looks like an
  instruction). Score = 100 − Σ weight × severity (FAIL 1, WARN 0.5); weights holder 25, type 20, invoice name 15, age 15,
  country 10, history 10, pending change 5. Sanctions hit forces 0 + BLOCKED. Status: BLOCKED / WARNING (any FAIL or WARN) / VERIFIED.
- **Design decision:** evaluated per bank account. Supplier status comes from the ACTIVE account plus party checks; a
  PENDING_CHANGE account is returned in `pending_accounts[]` (its own status) and does not downgrade the supplier.
  Results: Huaxin VERIFIED 100 (pending HK account WARNING), Brightline VERIFIED 100, Huameng WARNING 40
  (holder, type, age FAIL). Invoice-name results are per deal (`KybRun.deal`); party/account state never depends on them.
- **Endpoints:** `POST /kyb/verify/{id}?deal_id=` (buyer/admin; judge and supplier 403), `GET /kyb/{id}`,
  `GET /suppliers?buyer_id=`, `GET /suppliers/{id}`. Foreign supplier/deal gives 404 (no oracle). `DealSummary` gained `supplier_id`.
- **Persistence:** migration `26ef10614ad3` adds `kyb_runs` (history, full result JSON); `kyb_checks` updated in place. There is no
  `Party.kyb_reasons` column: reasons live in `kyb_checks.reasons` and `kyb_runs`. BLOCKED on a legal/licence/holder sanctions hit
  sets accounts RETIRED (no automatic way back; needs an admin path); an invoice-name-only hit is a hold, nothing retired.
- **Audit:** real signed append `app/security/audit.py::write_audit(db, ...)` (advisory lock, seq/prev_hash, Ed25519, raises 503 and
  writes nothing without a key). One `KYB_CHECKED` row per run (params list retired ids and verified changes) and a tier 3
  `DOC_INSTRUCTION_DETECTED` row. Phase 5.4 builds on it. The tool-call `record_event` is still structlog only (5.4).
- **Alerts:** engine owns KYB alerts: supplier-level `alert:<buyer>:kyb:<supplier code>` and deal-level
  `...:<deal ref>`; idempotent, auto-resolve, reopen. The seed no longer writes the Huameng alert (`seed.cli` syncs it; the old key is adopted).
  Alert text uses reason-code labels and the legal name only.
- **Tool:** `verify_party(supplier_id?, deal_id?)` Tier 0, compute-only, `kyb` card (status, score, top 3 reasons, link). The card sent
  to the model has role labels instead of holder/sanctions names. Registry now has 15 tools; agent prompt `agent@4`, router `router@2`.
  Generated text avoids injection-detector trigger phrases (a test scans it).
- **Sanctions mock:** `data/demo/sanctions_mock.json` (fictional; needs `version` + non-empty `entries`, fail closed 503).
- **Web:** `/app/suppliers` (card grid, status filter, search, pending marker), `/app/suppliers/[id]` (checks with evidence, pending
  section, accounts, deals, score trend, past checks, Re-run KYB for buyer/admin), KYB panel on `/app/orders/[id]` (red banner when
  BLOCKED), chat `KybCard`, `KybBadge` (icon + text), nav item, EN/BN keys. The deal route stays `/app/orders/[id]` (P13 may move it).
- **Verified:** Playwright `e2e/suppliers.spec.ts` (Karim sees Huameng Warning with ≥2 failing checks; Rahima does not see it).
- **Security review: PASS WITH FIXES, all fixed:** (H) invoice-name state shared across buyers; (M) retire on document text, cross-buyer
  invoice-name leak, document text in alerts, holder PII in the model card; (L) alert key collision, homoglyph sanctions evasion, empty
  sanctions file. 19 tests added.
- **Known gaps:** supplier-level alerts for buyers outside a buyer's run scope are raised but only resolved on an admin run or reseed;
  `GET /analysis/suppliers` and the scorecard tool still list every supplier network-wide (since P05); privacy masking is still P18;
  the 360 px layout and the Huaxin pending section were not checked by eye; `docs/SRS.md` TC-06 is for later phases.
- **Next phase reads:** this block, `docs/kyb.md`, `app/services/kyb.py` (`evaluate`, `verify`), `app/security/audit.py::write_audit`,
  `components/kyb/KybBadge.tsx`.

### 4.1 (from the user's "P13 Escrow, milestones, Deals UI and Supplier portal" prompt)
- **Branch:** `phase/4.1-escrow-deals`. No `docs/SRS.md` and no `app/finance`: rules live in `app/domain/{escrow,money,fx}.py`. Full
  reference: **`docs/escrow.md`** (state machines, check order, hook contract, endpoints, invariants, roles).
- **Files:** `app/domain/escrow.py`, `app/services/{escrow,deals}.py`, `app/schemas/deals.py`, `app/api/deals.py`,
  `app/security/{risk_hook,policy}.py`, `app/agent/tools/escrow.py`; migration `4822f40a71c9` (backfills seeded rows; adds
  milestone_confirmations, deals.kyb_run_id, milestone condition_text/evidence_status/release_idempotency_key, escrow refunded_total/
  partner/advance_over_20k + CHECK funded = released + refunded + balance, ledger kind/milestone_id/fx fields, audit_log.deal_id).
- **States:** Deal DRAFT → PROPOSED → CONFIRMED → FUNDED → IN_PRODUCTION → SHIPPED → ARRIVED → COMPLETED (+ DISPUTED, CANCELLED).
  Milestone PENDING (the prompt's LOCKED) → PROPOSED/READY → PENDING_APPROVAL → RELEASED | REFUNDED (+ FROZEN). Release advances
  the deal: first tranche IN_PRODUCTION, shipment SHIPPED, arrival ARRIVED, and COMPLETED when nothing is left unsettled.
- **Release check order:** READY + evidence VERIFIED (`EVIDENCE_NOT_VERIFIED`) → balance (`INSUFFICIENT_ESCROW`) → beneficiary ACTIVE
  and KYB-clean (`BENEFICIARY_NOT_ACTIVE`) → frozen escrow / open Tier 3 (`ESCROW_FROZEN`, `TIER3_APPROVAL_PENDING`) and open
  PENDING/APPROVED approvals → `risk_hook` → one transaction with row locks (ledger RELEASE with FX for CNY, balance, milestone,
  next milestone READY, deal status, cash-flow, alert recompute, signed `write_audit`). Same idempotency key replays; a new key on a
  RELEASED milestone is refused. `release_tranche(..., approval_id=)` is the 5.5 execution path (re-checks binding hash, tier, params, cooling-off).
- **risk_hook contract for 5.1:** `evaluate(action="RELEASE_TRANCHE", context) -> {decision ALLOW|REQUIRE_APPROVAL|BLOCK, tier, reasons}`.
  The shipped `default_evaluate` is an interim FAIL-CLOSED policy, not the full engine: Tier 3 when USD amount > 20,000 (unrounded),
  advance over 20,000 or receiving account < 30 days old; Tier 2 for a first deal with the supplier or a different settlement currency
  (FX lock); otherwise ALLOW at tier 1 with a notice. REQUIRE_APPROVAL creates an ApprovalRequest bound by `approval_binding_hash` and sets
  PENDING_APPROVAL (HTTP 202). The Python-level `hook=` argument of `release_tranche` (tests only) must be removed or locked in 5.1.
- **Demo caveat:** the seeded deal pays Huaxin's CNY account, so every tranche is Tier 2 `FX_RATE_LOCK`; the seeded Tier 3
  `CHANGE_BENEFICIARY` approval freezes all Huaxin releases until decided. The demo script (6.2) must decide it first.
- **Endpoints:** POST /deals; GET /deals?status=; GET /deals/{id}; POST /deals/{id}/milestones/propose|confirm; POST /deals/{id}/escrow/fund
  (amount optional: funds the next uncovered tranche, up to goods value; funding spends buyer cash, 409 `INSUFFICIENT_CASH`);
  POST /milestones/{id}/release (200 RELEASED, 202 PENDING_APPROVAL), /refund (admin); GET /deals/{id}/ledger|activity; dev-only
  POST /milestones/{id}/evidence (needs `ENABLE_DEV_EVIDENCE=true` and APP_ENV != prod; default off; UI control also needs `NEXT_PUBLIC_DEV_TOOLS=1`).
  Responses carry `can_*` {allowed, reason} flags; errors are problem JSON with a stable `code`. Suppliers get a projection with buyer-private
  fields nulled (expected sale value, costs, KYB score/reasons, approval reasons, refund reasons).
- **Tools:** `propose_milestones` (Tier 2) and `release_tranche` (Tier 3) are registered but in no allow-list; `llm_tools()` hides them
  and the guard returns `requires_approval_flow`. 17 tools in total.
- **Web:** `/app/deals` (list), `/app/deals/new` (4 steps, exact string-math totals, landed-cost preview, warning dialog),
  `/app/deals/[id]` (stepper, escrow bar, ledger, tabs, Propose/Confirm/Fund/Release dialogs, KYB panel); `/app/orders/[id]` redirects to
  it (`/app/orders/[id]/analysis` stays); `/supplier` + `/supplier/[id]` portal (EN + 中文, `src/i18n/zh.json`, Noto Sans SC), suppliers are
  redirected there from `/app`; new `Toast` and `ConfirmDialog`; ~30 error codes mapped to EN/BN.
- **Decisions:** propose has no PendingApproval yet (both-party confirmation stands in; audit row at tier 2); re-seeding resets seeded
  deals (use `db:reset-demo` after releasing the demo deal through the API); activity feed `deal_id` is unsigned grouping metadata.
- **Security review: PASS WITH FIXES, all fixed.** (H) placeholder hook allowed everything at Tier 0; (M) APPROVED-unexecuted approval
  bypass, frozen/Tier 3 holds, buyer cash race, supplier saw buyer-private data, dev endpoint default-on; (L) unrounded amount, approval key
  collision and supersede, refund cancels approvals, 403 and resync audit, goods cap. 18 hardening tests added.
- **Known gaps:** FR-8 credit record on COMPLETED not built; Documents tab shows evidence counts only (P14); refund has no UI; the new-deal
  supplier picker lists only existing counterparties (no supplier-onboarding endpoint); `can_*` reasons are English only; admin Confirm hidden;
  Playwright `chat.spec` citation test fails without the LLM/RAG backend (not investigated).
- **Next phase reads:** this block, `docs/escrow.md`, `app/services/escrow.py::set_evidence_status` and `release_tranche`,
  `app/security/risk_hook.py`, `components/deals/`.

### 4.3 (from the user's "P14 Document forensics" prompt)
- **Branch:** `phase/4.3-forensics`. Full reference: **`docs/forensics.md`** (pipeline, checks and weights, ground-truth mapping, dev-split table, endpoints, security notes). No `docs/SRS.md`.
- **Pipeline:** pure logic in `app/forensics/` (pdf_text, parse_fields, checks, scoring, analyze, eval_dev, sandbox/pdf_worker) and orchestration in `app/services/documents/` (upload, storage, signing, extract_text, extract_fields, checks, scoring, evidence, pipeline, read); `app/services/hash_registry.py` is a stub returning NEW (P15 plugs in with `hash_registry.set_checker`); API `app/api/documents.py`; tool `check_documents` (Tier 0, read-only, `document_check` card, agent@5/respond@4); 18 tools.
- **Upload:** magic bytes at offset 0, 10 MB (413 via ASGI body limit before spooling), file-name sanitising, storage keyed by sha256 outside public folders (S3 is a stub), HMAC signed URLs bound to document and user. Same bytes on the same deal reuse the document; on another deal 409 `DUPLICATE_DOCUMENT` (accepted cross-tenant oracle). Parsing runs in a sandboxed child process (RLIMIT_AS 1 GB, CPU limit, 20 s). Uploading a file matching a seeded PLACEHOLDER row activates it.
- **Extraction:** deterministic label parser handles the 4 date formats, swapped blocks, wrapped values; LLM fallback only for missing fields (`structured_call`, masked, `<untrusted_document>` NFKC-escaped, skipped when instruction codes exist; an LLM-filled required field forces at least WARNING); cached by (sha256, extractor version). Hidden spans and PDF metadata are reported, never used as content.
- **Hidden-text detection:** white or near-white, size <= 2 pt, off-page, render mode 3 (hard), covered by a later opaque rect/image and dark-on-dark (WARN only), up to 100 pages scanned; truncation is an EXTRACTION_COMPLETE WARN.
- **Checks (finding codes):** QUANTITY_MATCH, VALUE_MATH/VALUE_MATCH, NAME_MATCH (exact only = PASS; near matches WARN), BENEFICIARY_MATCH, VESSEL_VOYAGE_MATCH, DATE_LOGIC, PORT_MATCH, HS_CODE_MATCH, PRICE_BAND, HIDDEN_TEXT, INSTRUCTION_SCAN, METADATA_ANOMALY, DUPLICATE_HASH, PHOTO_MATCH (colour only; width needs OCR/vision flag, off), EXTRACTION_COMPLETE, REFERENCE_CHANGED. Mapped to the 11 ground-truth names in one table.
- **Scoring:** sum of weight x factor (FAIL 1, WARN 0.5), cap 100; ordinary checks 35, BENEFICIARY_MATCH/HIDDEN_TEXT/INSTRUCTION_SCAN/DUPLICATE_HASH 70 (each forces FAILED, floor 61), EXTRACTION_COMPLETE 30, METADATA_ANOMALY 10. < 30 PASSED, 30-60 WARNING, > 60 FAILED.
- **Evidence automation:** all required types PASSED -> VERIFIED; WARNING -> FLAGGED (buyer review); FAILED -> REJECTED + FRAUD alert; worst verdict wins, computed under the per-deal advisory lock; an unchecked upload demotes to PENDING and release is refused with `DOCUMENTS_PENDING`. Document instruction/duplicate flags reach `ReleaseContext` (force Tier 3 and freeze). Booking/dates come from the first PASSED or buyer-accepted PI (pinned); later changes give `REFERENCE_CHANGED` (buyer can `POST /documents/{id}/accept-reference`); FRAUD alerts are resolved only by an admin re-check.
- **Endpoints:** POST /deals/{id}/documents (?wait= buyer/admin only), GET /deals/{id}/documents, GET /documents/{id} (adds `file_url`, `file_inline_url`, `viewer_role`, findings with neutral labels + issue text, `top_reason` on list rows), POST /documents/{id}/recheck, POST /documents/{id}/accept-reference, GET /documents/{id}/hidden-text, GET /documents/{id}/file?token=[&inline=1]. Suppliers see `UPLOADED`/`IN_REVIEW` only and `file_url` only for their own uploads; hidden-text 403. Migration `26b582a72d5c` adds `documents.uploaded_by_user_id`.
- **Dev-split results (50 clean + 50 tampered packs, dev only):** precision and recall 1.00 on all 11 checks and all 10 fraud types (obvious and subtle); 0/50 clean packs flagged, 0/400 clean documents not PASSED. Treat this as a ceiling on synthetic data, not real-world accuracy; with fail-only counting NAME_MATCH recall is 0.57 (subtle name variants are WARN by design). **No test-split metrics were computed; P24 reports those.** All 20 attack PDFs are flagged.
- **Demo cases:** TC-02 clean pack -> M2 VERIFIED; TC-03 forged B/L -> FAILED, M2 REJECTED, FRAUD alert, tier-3 audit row; TC-04 chat answer states the hidden instruction was ignored (EN and BN).
- **Web:** Documents tab (dropzone, per-file status with polling, evidence checklist, list with top reason), `/app/documents/[id]` (preview via `file_inline_url`, fields table with mismatch highlighting, check list, verdict, Re-check, Accept as reference, reveal-hidden-text overlay + accurate span list), supplier upload on `/supplier/[id]` (status words only), chat `document_check` card, EN/BN/zh keys.
- **Security review: PASS WITH FIXES, all fixed.** (H) `structured_call` skipped the Privacy Gateway; PI baseline could be replaced to launder a forged B/L. (M) evidence race, upload not demoting evidence, document flags not reaching the risk hook, hidden-text gaps, truncation, OTHER docs unscanned, LLM-filled fields deciding checks, parser DoS. (L) metadata keys, image pixel cap, polyglot, wrapper escaping, supplier verdict/file leaks, KYB seller source, download audit.
- **Known gaps:** privacy masking is still the identity stub (P18); the overlay covers page 1 only; covered/low-contrast detection assumes opaque fills; render-mode-3 text in CID fonts has no readable content; photo width is not checked; a rejected document keeps its tranche blocked until an admin acts (no override endpoint); S3Storage is a stub; Firefox inline PDF preview untested; accept-reference not exercised end to end (mocked vitest only); the demo script must also decide the seeded Tier 3 approval.
- **Next phase reads:** this block, `docs/forensics.md`, `app/services/hash_registry.py`, `app/services/documents/pipeline.py`, `app/security/risk_hook.py`.

### 4.4 (from the user's "P15 Document hash registry and duplicate-financing detection" prompt)
- **Branch:** `phase/4.4-registry`. Full reference: **`docs/registry.md`** (fingerprints, verdict rules, integrations, lender-check contract, privacy, gaps). No `docs/SRS.md`.
- **Fingerprints:** exact sha256 + semantic (invoice seller/no./total/currency = `documents.canonical_hash`; B/L shipper/B/L no./vessel). Date left out on purpose. PI and CI match as one family. Migration `d5a3f0c8b7e1` (Alembic, not Prisma): `hash_registry` gets purpose, status, context_key, seen_count, hit counters, nullable lender; `documents` unique per `(deal_id, sha256)`; backfills evidence rows.
- **Verdicts:** NEW / SAME_CONTEXT / EXACT_DUPLICATE / NEAR_DUPLICATE over ACTIVE entries; another deal, or same deal at another lender, conflicts; same deal other purpose does not; conflicts win.
- **Integrations:** pipeline registers non-FAILED docs as ESCROW_EVIDENCE and fails duplicates (DUPLICATE_HASH FAIL, FRAUD alert, Tier 3 flag via release facts); the 409 DUPLICATE_DOCUMENT and `platform_duplicate` are removed. Financing: BANK_IMPORT_LOAN and ESCROW_BACKED_LOAN gate on the deal's invoices (match shows `registry_block`; apply 409 `INVOICE_ALREADY_FINANCED` + FRAUD alert; no invoice -> 400 `INVOICE_REQUIRED`; approval re-checks; collateral registered at submit). Deal COMPLETED/CANCELLED releases entries. Audit: REGISTRY_REGISTERED / RELEASED / LENDER_CHECK (T0), REGISTRY_DUPLICATE_HIT (T3). Tool `registry_status` (T0, `registry` card, 19 tools; agent@6); `check_documents` carries registry state.
- **Lender-check contract:** `POST /registry/lender-check {lender_id, sha256 | document_id | fields}` (+ `/file` multipart) -> `{simulated, result, already_registered_for, registered_on, held_by}`; admin/judge any input, buyers own `document_id` only. Other endpoints: `GET /registry`, `/registry/stats` (admin/judge), `GET /documents/{id}/registry`.
- **Mock lenders:** kept the seed: Lender A = Meghna Commercial Bank (holds the main deal's PI), Lender B = Setu Partner Finance, NBFI Shitalakshya. The brief named Meghna "Lender B".
- **Decision with demo impact:** on SETU-2026-0001 the escrow-backed Lender B loan is now blocked, so the P07 top pick became supplier credit (TC-09 and 3 financing tests updated). Alternative: gate the bank import loan only.
- **Catch rate (dev split, `python -m app.forensics.eval_registry`):** byte-identical 3/3 EXACT, re-saved 2/2 NEAR, 5/5 caught. Synthetic ceiling; test split is P24's.
- **On-chain:** not built; `app/services/registry_anchor.py` has the Merkle root and `Anchorer` protocol only; wait for the organiser's answer on Topic E.
- **Web:** Registry box in the document viewer, judge/admin demo button "Try to finance this invoice at Lender B" on the deal page, `/app/admin/registry`, blocked financing option, chat `registry` card, EN/BN. Playwright `e2e/registry.spec.ts` compiles but was NOT run (no stack).
- **Security review: BLOCK -> fixed:** (H) financing race (registry lock across gate + register), apply before any invoice, approval did not re-check; (M) failed doc released its entry (now fail closed), PI/CI relabel bypass, lender-check open to every buyer and misses unaudited, no backfill. **Not fixed, by the brief:** release on COMPLETED lets a finished deal's invoice/B/L be reused (reviewer High); no repayment flow, no rate limit on the file endpoint, JUDGE checks write counters/alerts, downgrade drops evidence rows.
- **Verified:** pytest 858 passed, ruff clean, web lint clean, vitest 182 passed.
- **Next phase reads:** this block, `docs/registry.md`, `app/security/risk_hook.py` (duplicate_hash -> Tier 3), `app/services/hash_registry.py`.

### 5.1 (from the user's "P16 Deterministic risk-tier engine" prompt)
- **Branch:** `phase/5.1-risk-engine`. Reference: **`docs/risk.md`** (rules table, enforcement points, endpoints). No `docs/SRS.md`.
- **Engine:** `app/services/risk/engine.py` (pure), thresholds `services/agent/config/risk.yaml` via `app/security/policy.py`. Output has reason codes, EN/BN text, `context_hash`, rule `trace`, `decided_by`, `hints` (counterfactuals). Release uses it through `risk/adapter.py` (the `risk_hook` contract kept; injected test hooks still work, `default_evaluate` removed).
- **Enforcement:** `risk/gate.py::run_gate` for fund, propose/confirm schedule, `fx_lock.lock_fx` (new, creates `FxLock`), `beneficiary.change_beneficiary` (new, always Tier 3); release keeps its own path. `origin` (USER_UI/AGENT/SYSTEM) is a Python argument; `approval_id` is refused unless USER_UI. Bodies use `ActionIn` (unknown fields such as tier/approved are dropped).
- **Decision to review:** a person's own click on confirm / propose schedule / lock FX (`inline_tier2_actions`) is the Tier 2 one-tap and runs inline (recorded as a decision); the agent only gets an ApprovalRequest. Release, deposit and account change always use an ApprovalRequest at Tier 2/3. FUND_ESCROW only applies BLOCK + agent rules.
- **Storage:** migration `e8b4c1d7a2f6`: `risk_events` (readable decision + trace) and approval actions FUND_ESCROW / CONFIRM_MILESTONES; each decision also writes a signed `RISK_DECISION` audit row. INFO alert on Tier 1 release, FRAUD alert on BLOCK.
- **Agent:** six Tier 0 `propose_*` tools (deal_status intent), prompts agent@7 / respond@5. Registry has 23 tools.
- **API/web:** `POST /deals/{id}/fx-lock`, `POST /deals/{id}/beneficiary`, `POST /risk/evaluate` (dry run), `GET /risk/policy`, `GET /risk/overview` (admin/judge); `/demo/risk-playground`, `/app/admin/risk`, `RiskDecisionCard` in the release dialog, landing security section.
- **Security review: PASS WITH FIXES.** Fixed: beneficiary change no longer retires the supplier's other accounts; FX lock must match quote currency and cover the tranche amount. **Open / for P17:** (H) any buyer's open Tier 3 account request freezes every release to that supplier (P13 design; needs cancel + expiry, or scope to the buyer); (M) approval execution does not yet check OTP verified / `decided_by_user_id` (add `otp_verified_at`); (M) an agent proposal parks a clean tranche in PENDING_APPROVAL until cancelled; (M) FAILED/WARNING/score look at documents of the tranche only (milestone-less FAILED docs are caught only through instruction/duplicate flags); (M) fraud score uses `> 60` as specified in the prompt (SR-1 says 0.6 or more); (L) `origin` defaults to USER_UI, FX lock is not consumed at settlement, inline one-tap has no dedicated audit marker.
- **Web gaps:** a blocked release returns HTTP 409 (problem JSON), so the blocked card is not shown from that path yet; landing page thresholds are static text; not browser-checked.
- **Tests:** tests/risk (engine), tests/api/test_risk_enforcement.py, test_risk_api.py; DB tests need `TEST_DATABASE_URL` (a throwaway pgvector container was used).
- **Next phase reads:** this block, `docs/risk.md`, `app/services/risk/gate.py`, `app/db/models/trust.py::ApprovalRequest`.

### 5.2 (from the user's "P17 Approval inbox, OTP, cooling-off, in-app beneficiary change" prompt)
- **Branch:** `phase/5.1-risk-engine` (work not yet committed). Reference: **`docs/approvals.md`** (lifecycle, OTP, endpoints, storage, decisions). No `docs/SRS.md`.
- **Backend:** `app/services/approvals.py` (approve / reject / cancel / resend, expiry, evidence snapshot, notifications, timeline), `approval_otp.py` (HMAC OTP, demo phone, events), `supplier_accounts.py`, `inbox.py`, `simulator.py`, `app/security/email_guard.py`, routers `api/approvals.py` + `api/inbox.py`, migration `f1c7a3b9d204`. Request creators (gate, release) now set context hash, expiry, OTP and a feed event.
- **Rules held:** approve body = `{otp?}` only; the creating service re-runs the risk engine and executes the stored params; higher tier at execution -> old request cancelled and a stricter one opened (`RE_ESCALATED`); Tier 3 = cooling-off first, then 6-digit code (5 min, 3 wrong = LOCKED); only buyer/admin decide (403 otherwise); OTP only in the demo-phone table when `DEMO_MODE=true` (404 otherwise).
- **Beneficiary:** supplier portal request -> PENDING_CHANGE -> KYB re-run -> Tier 3 for the buyer. E-mail never changes anything: `POST /inbox/email-check` BLOCKS (alert + signed audit, no account touched); accounts with `change_requested_via='email'` cannot be proposed or approved (the seeded HK request can only be rejected, which retires the account).
- **Fixed from the P16 review:** an open Tier 3 request now freezes only the same buyer's releases (was every buyer).
- **Config:** `DEMO_MODE`, `COOLING_OFF_SECONDS` (600; demo 30), `APPROVAL_EXPIRY_MINUTES` 1440, `OTP_TTL_SECONDS` 300, `OTP_MAX_ATTEMPTS` 3, `OTP_SECRET_SEED`.
- **Web:** `/app/approvals` (tabs, evidence snapshot, Tier 2 / Tier 3 dialogs, OTP boxes, cooling-off ring), Demo phone panel, notification bell, `/app/inbox/email-check`, `/demo/scam-simulator`, supplier "Change payout account" + 4-step tracker (EN/中文), deal "Approval trail".
- **Verified:** pytest 940 passed (needs a local pgvector DB; `tests/registry` also needs `DATABASE_URL` pointing at a migrated, seeded DB); web lint + tsc clean, vitest 210 passed; Playwright `e2e/approvals.spec.ts` 5/5 (reset DB first, agent with `DEMO_MODE=true COOLING_OFF_SECONDS=30`, Next started separately).
- **Known gaps:** Bengali/Chinese strings not reviewed by a native speaker; 360 px and keyboard-only not hand-checked; demo phone is outside the Tier 3 modal's focus trap; seeded approval reasons have no Bengali text; large-advance simulator is a dry run; `ACCEPT_FINANCING` approvals are not executable here.
- **Next phase reads:** this block, `docs/approvals.md`, `app/services/approvals.py`.

### 5.3 (from the user's "P18 Privacy Gateway + judge-facing privacy transparency" prompt)
- **Branch:** `phase/5.3-privacy`. Reference: **`docs/privacy.md`** (pieces, wiring, config, endpoints, storage, gaps). No `docs/SRS.md`.
- **Backend (`app/privacy/`):** `detectors.py` (NID, passport, BD/CN phone, account incl. starred alphanumeric ids, IBAN mod-97, SWIFT with context, email, known + labelled holder names, amounts; NFKC / Bangla digits / zero-width / spaced-digit normalisation with span map), `vault.py` (per request, never serialised), `gateway.py` (`mask*/unmask/protect/scan`, `StreamUnmasker`), `records.py`, `views.py`, `eval.py`. Stub `app/security/privacy_gateway.py` removed. Table `privacy_records` (migration `a7d2c9e4b1f8`): masked payload + counters only.
- **Wired:** runner masks the graph input (root LangSmith run holds tokens); nodes `router/agent/respond` call `gateway.protect` before every model call; `tools` unmasks model-supplied args and masks results; `structured_call` (document extraction, all-string wire schema, prompt `forensics-extract@2`) uses the request gateway; runner unmasks answer/why/notes/cards and the SSE stream. Graph state and checkpoint stay masked; real tool payloads sit in `gateway.raw_results` for cards.
- **Config:** `PRIVACY_ENABLED` (true), `PRIVACY_MASK_AMOUNTS` (true).
- **API/web:** `POST /privacy/dry-run`, `GET /privacy/summary|messages/{id}|documents/{id}|admin/overview`; eye-icon Privacy X-ray on assistant messages and document viewer, `/demo/privacy-playground`, `/app/admin/privacy` (chart, last 20 masked records, "Prove it" LangSmith link), live counter in chat header, landing before/after strip, EN/BN/zh.
- **Dev-split numbers (`python -m app.privacy.eval dev`, 100 packs / 600 docs):** masking ON: detectable identifiers in payload 0, ground-truth bank identifiers leaked 1/600 (a seller company name equal to the holder; company names are not masked by design), masked ACCT 400, SWIFT 200, NAME 509, AMT 900; OFF detectable 2490; field copy round-trip 1200/1200. OFF: 600/600 ground-truth leaked, 2275 detectable. Numeric chat set (landed cost, shortfall 1,560): correct with masking on and off. Test split not scored (P24).
- **Security review: PASS WITH FIXES, fixed.** (H) tool runs sent raw inputs/outputs to LangSmith (tools now run without tracing callbacks; trace test covers raw tool values); (M) key-labelled JSON identifiers (`bank_account`, `phone`, `holder_name` …) masked by field name; detector bypasses closed (label/value on separate lines, unlabelled 13-18 digit numbers, dotted/double-spaced/bracketed phones, `86…` without `+`, Cyrillic look-alike labels); `⟦AMT⟧` in tool args restored as plain numbers; only exact tokens are restored and token look-alikes in tool/document/user text are defanged; known values scoped to parties the caller can read (+ own display name); args_summary built from masked args; a payload with a surviving identifier now blocks the call (`PrivacyBlocked`). **Not done:** masking lives in the nodes and `structured_call`, not one client wrapper (CLAUDE.md rule 4 wording); chat TOOL rows are stored real (intended, see below).
- **Decision:** chat TOOL rows keep the real deterministic tool output (history rebuilds cards from it); the model-facing history is the masked checkpoint.
- **Known gaps:** tokens from earlier turns cannot be restored (shown as `[protected X]`); unlabelled long digit strings in chat are not masked; amounts masked means the model cannot compare them; Bangla/Chinese strings not native-reviewed; no injection-classifier model call exists.
- **Verified:** pytest 965 passed (needs local pgvector DB), ruff clean, web lint + tsc clean, vitest 225 passed, Playwright `e2e/privacy-playground.spec.ts` passed against a running stack (agent in mock mode on a local DB).
- **Next phase reads:** this block, `docs/privacy.md`, `app/privacy/gateway.py`.

### 5.4 (from the user's "P19 Layered prompt-injection defence + live attack console" prompt)
- **Branch:** `phase/5.3-privacy` (work not yet merged). Reference: **`docs/injection.md`**. No `docs/SRS.md`.
- **Layers (`app/security/injection/`):** 1 `wrap.py` (`<untrusted src id=rand>`, after masking, rule in system prompt, prompts system@2/agent@8/respond@6); 2 `detector.py` (NFKC, look-alikes, zero-width, spaced letters, base64/URL decode; EN/BN/ZH rules; score, source, masked snippet; optional `INJECTION_LLM_CHECK` can only raise a borderline score); 3 `events.py` (always on: `injection_events` table, migration `b3e8d5a1c7f2`, `flags_deal` -> `instruction_from_document` via `deal_context` and `release_facts`, FRAUD alert, signed audit; `DOC_INSTRUCTION` now applies to ALL money actions, not only release); 4 `gating.py` (money tools need intent + the user's own words + no detection in the turn; `INJECTION_BLOCKED_TOOL`); 5 `guard.py` (money claims, prompt leaks, echoed instructions; plain "ignored it and flagged the deal" sentence; tokens held back for risky turns); 6 `switch.py` (`INJECTION_DEFENCES=on|off` switches layers 2, 4, 5 only; `layer_on(3)` raises; ignored when `APP_ENV=prod`).
- **Wiring:** `Nodes.tools` (gate, per-call deal link, durable events in their own session so a rolled-back turn cannot lose a flag), `registry.guard` (new detector, keyed placement sources), KB retrieve/ingest (new detector added), document pipeline (event per placement), `ChatResponse.security` + `meta.security`, `GET /documents/{id}/hidden-text` -> `injection`.
- **Judge-facing:** `/demo/attack-console`, `/app/admin/security`, scoreboard, viewer reveal, chat "Security check" chip, landing 5-layer row. API `/security/injection/{gallery,run,scoreboard,scoreboard/rerun,events,events/{id}/resolve}` (admin/judge; resolve admin, audited as INJECTION_RESOLVED).
- **Evaluation:** `python -m app.security.injection.suite dev` (real nodes + obedient mock model + sandbox propose stubs + real risk engine) -> `eval/results/injection_dev.json`. Attack split fixed in code ((variant + style index) even = dev; 13 dev / 12 test). **Dev numbers (13 attacks): attack success OFF 100% -> ON 0%; gate + guard only (no detector) 0%; money moved 0 in all modes; detection recall 100%; false positives 0/300 clean dev documents.** Test split not run (P24). Synthetic ceiling: the obedient mock ignores delimiters, so layer 1 is not measured.
- **Security review: PASS WITH FIXES, fixed:** (H) events written in the turn session were lost on rollback (now durable own-session commit); (H) resolve was unaudited (now signed row); (M) DOC_INSTRUCTION only escalated release (now all money actions); (M) `off` ignored in prod; rerun single-flight, atomic file write, fallback tempdir reuse; gate verbs tightened. **Not fixed:** detector evasions (MIME/double base64, HTML entities, leetspeak, polite paraphrase, text past 60k chars); streaming sends raw tokens on turns with no untrusted tool (final event carries the guarded text); negation suppresses money-claim detection anywhere in the sentence; BLOCKED_TOOL flags only the chat's focus deal; `off` still disables the pre-P19 intent allow-list and legacy tool-result scan; snippets masked only by the privacy gateway; Bangla/Chinese strings not native-reviewed; frontend not browser-checked, Playwright `e2e/attack-console.spec.ts` not run.
- **Verified:** ruff clean; pytest 1092 passed (needs a local pgvector DB and DATABASE_URL for tests/registry); web lint + tsc clean, vitest 234 passed.
- **Next phase reads:** this block, `docs/injection.md`, `app/security/injection/suite.py`.

### 5.5 (from the user's "P20 Signed hash-chained audit log + execution evidence + judge verification" prompt)
- **Branch:** `phase/5.3-privacy` (continued). Full reference: **`docs/audit.md`**. No `docs/SRS.md`.
- **Scheme `setu-audit-v2`:** body `{seq, ts, actor_type, actor_id, deal_id, action, tier, decision, payload}`; `payload_hash = sha256(canonical_json(body))`; `entry_hash = sha256(prev_hash|payload_hash|seq|ts)`; `signature = Ed25519(entry_hash bytes)`; genesis = 64 zeros. Code: `app/audit/{scheme,keys,keygen,mask,writer,verify,export,timeline,tamper,middleware}.py`, `app/api/audit.py`. `app.security.audit` keeps only hash helpers and `record_event`.
- **Writer:** `app.audit.write_audit(db, actor, action, tier, params, result, deal_id, actor_id)`; advisory-lock single writer; payload PII-redacted with the P18 detectors (amounts kept; UUIDs/digests untouched); no key = no row; `ts` taken after the lock. Migration `c4f9e2a6d1b3` renames `result`->`decision`, `params_hash`->`payload_hash`, adds `actor_id`, `payload`, a BEFORE UPDATE/DELETE trigger, and **empties `audit_log`** (run `pnpm db:reset-demo`; stale `audit_seq` references otherwise). Seed history re-signed; `seed(reset=True)` appends `DEMO_RESET` (with previous head seq/hash). Actor id comes from the signed session cookie via `AuditActorMiddleware`.
- **Keys:** private = `AUDIT_SIGNING_KEY` or the git-ignored dev key under `keys/`; `python -m app.audit.keygen` never overwrites; public key committed at `docs/submission/audit-public-key.pem` (fingerprint 8030dcc6...d074, from the local dev key; **set the host `AUDIT_SIGNING_KEY` to the matching key for prod**, or commit the new PEM) and copied to `apps/web/public/`.
- **Commands:** `pnpm audit:keygen`, `pnpm audit:verify` (`--file F --pubkey PEM`, `--from/--to`), `pnpm audit:export` (writes `docs/submission/execution-evidence/operation-log-<date>.jsonl` + `.md`, then verifies). API: `GET /audit/{public-key,summary,entries,entries/{seq},verify,export}`, `POST /audit/tamper-demo` (in-memory copy, read-only connection).
- **Coverage (real code, asserted in `tests/audit/test_coverage_flow.py`):** `TOOL:<name>` (actor llm, own short transaction so it survives a turn rollback), KYB_CHECKED, DOC_UPLOADED/DOC_CHECKED/DOC_INSTRUCTION_DETECTED, REGISTRY_*, RISK_DECISION, APPROVAL_REQUESTED/APPROVED/REJECTED/EXPIRED/LOCKED, APPROVAL_OTP_FAILED, ESCROW_FUNDED, TRANCHE_RELEASED, ESCROW_REFUNDED, FX_LOCKED, BENEFICIARY_CHANGE_REQUESTED/CHANGED, EMAIL_BENEFICIARY_CHANGE_BLOCKED (+ locked CHANGE_BENEFICIARY approval), INJECTION_DETECTED, PRIVACY_LEAK_ALERT, DEMO_RESET. Notes: a Tier 2 release request is logged as `RELEASE_APPROVAL_REQUESTED` (not `APPROVAL_REQUESTED`); live fund/release tiers differ from seeded history (0/2 vs 1/1).
- **Web:** `/verify` (public, browser-only, Web Crypto with @noble/ed25519 fallback), `/app/admin/audit` + `/demo/audit` (live chain, drawer, tamper panel, evidence dashboard), receipts with QR (`/verify?seq=&hash=#e=<entry>`), Activity tab shows EN/BN text, landing line. Fixtures: `apps/web/e2e/fixtures/audit/` (test key; regenerate with `uv run python -m tests.audit.make_fixtures`).
- **Review: PASS WITH FIXES, fixed:** (H) tool-audit write could fail on hostile tool names/NUL chars (now truncated/sanitised) and was lost on turn rollback / held the audit lock for the turn (now own short session, 2 s lock timeout, falls back to the turn session); (M) the unsigned header's `contiguous:false` let a doctored export pass (verifiers now report `missing_seqs` and say a partial export cannot prove completeness); (L) float/oversized ints, int PII under id keys, ts after lock, previous head in DEMO_RESET. **Not fixed:** TRUNCATE and `DISABLE TRIGGER` by the table owner (use a non-owner app DB role in prod); tail truncation of an export is undetectable without a live head (documented); `args_summary` stored as one flat string.
- **Verified:** ruff clean; pytest 1,240 passed (tests/registry needs `DATABASE_URL` pointing at a migrated+seeded DB, as before); tests/audit 163 passed; web lint + tsc clean, vitest 257 passed; Playwright `e2e/verify.spec.ts` 5/5 (before the last small edits); CLI verified a 493-entry export against the committed public key. **Not verified:** chain page, tamper panel, drawer, receipt dialog/PNG/print were never opened in a browser; QR URL (~1000 chars) not scanned; `@axe-core/playwright` is MPL-2.0 (dev only, licence not checked).
- **Next phase reads:** this block, `docs/audit.md`, `app/audit/scheme.py`.

### 6.2 (from the user's "P21 Guided end-to-end demo" prompt)
- **Branch:** `phase/p21-guided-demo`. Reference: **`docs/demo.md`** (design, API, UI contract, deviations). No `docs/SRS.md`.
- **Script:** `data/demo/demo_steps.yaml` (12 steps, 27 scenes, 17 scorecard items, EN/BN, presenter notes). Runner `app/demo/runner.py` calls the REAL API in-process as each scene's user, or a registered service call (`app/demo/actions.py`); expectations stored per scene; a failing or slow scene (`DEMO_STEP_TIMEOUT_SECONDS`) shows a friendly card and never blocks the next.
- **Sandboxes:** one Postgres schema per judge (`app/demo/sandbox.py`, `app/db/tenancy.py`, `SandboxMiddleware`), signed `setu_sandbox` cookie, seed profile `demo`, TTL 4 h, cap 40, per-sandbox and per-IP limits, live-AI budget 25, cleanup (lazy, `pnpm demo:cleanup`, `POST /demo/cleanup` with `CRON_SECRET`). Reset builds a NEW schema and swaps it in (signed `DEMO_RESET` with the previous head). Checkpoints are keyed `<schema>:<thread>`. Migration `d6b1f4a8c2e9` (`demo_sandboxes`).
- **Replay:** `app/llm/replay.py` wraps both model tiers and `structured_call`; keys = masked prompt + model; fixtures `data/demo/fixtures/llm/*.json` (7, real model via OpenRouter) + manifest. `pnpm demo:run|check|record|verify|cleanup`. `demo:check`: 27/27 scenes, 0 misses, ~3.5 s, offline.
- **Product changes the story needed:** `POST /documents/{id}/reject`; signed credit record on COMPLETED (`app/services/credit_record.py`, `GET /credit-records/{deal}`, `POST /credit-records/verify`; FR-8 was not wired); system prompt rule for privacy tokens (system@3; without it the model refused to quote masked amounts); advisory locks per schema.
- **Deviations (details in docs/demo.md):** step 4 applies supplier credit for the peak USD 2,160 (the escrow-backed Lender B loan is blocked by the registry on purpose); step 5 shows the already-confirmed schedule from both sides; step 8's Tier 3 is raised live (seed profile `demo` omits the pre-seeded one); step 12 has a labelled cash time-skip; 3 attacks blocked, not 2.
- **Web:** `/demo` landing (preflight, 3 entry buttons, `?step=N` deep link), `/demo/run` (iframe stage, spotlight, narration + read-aloud, scorecard, Demo phone, role switcher, live-AI, skip cooling-off, summary), presenter (`?mode=presenter`: arrows, Space, R, B, N, timer) and recording (`?mode=record`) modes, mobile tabs, embed mode (`?embed=1`), 23 `data-demo` anchors, credit-record card. Playwright `e2e/demo.spec.ts` 4/4.
- **Security review:** BLOCK -> fixed: schema-missing fell back to `public` (now checked on every checkout, 410), seeded chat thread shared checkpoints, malformed foreign cookie disabled routing, live budget reset by reset + non-atomic spend, reset/run buckets, XFF spoofing, skip-cooling-off in prod, debug dump in prod, transaction-pooler guard (`SANDBOX_POOLER`). **Not fixed:** credit records and sandbox audit chains share the production signing key (no environment tag); per-instance in-memory rate limits; the runner pool is shared (8 workers); a timed-out scene keeps running.
- **Known gaps:** spotlight falls back to a centred caption for scenes 8.1 (empty email form), 9.2/11.3 (rule trace only inside the release dialog) and 10.1 (registry box hidden for buyers); Bangla/Chinese not native-reviewed; speechSynthesis, fullscreen and keyboard-only not verified; 8 pre-existing web unit tests fail in files from earlier work (`pagePrompts`, `Testimonials`, `OnboardingChecklist`); `APP_ENV=prod` needs `DEMO_MODE=false`, which switches off the scam simulator the steps use.
- **Next phase reads:** this block, `docs/demo.md`.

### 6.3 (from the user's "P22 Landing page, design system, interaction polish, accessibility and full Bangla/Chinese coverage" prompt)
- **Branch:** `phase/p22-ui-polish` (cut from `phase/p21-guided-demo`). No `docs/SRS.md`; no `eval/results.json` (landing reads `apps/web/public/eval-results.json`, built only from dev numbers in 5.3/5.4).
- **Tokens (`app/globals.css`):** brand/accent/semantic colours, `brand-text`, `danger-solid`, `scrim`, radii, shadows (`shadow-pop`), motion durations/easing, `anim-*` classes (all disabled by reduced motion). Dark mode = `html[data-theme=dark]` variable overrides, pre-paint script in `layout.tsx`, `lib/theme.ts`, `ThemeToggle` (system -> light -> dark). Every `text-brand-700/800` became `text-brand-text`.
- **UI kit (`components/ui`):** Button (variants, loading, 44px), Badge (always icon + text), Card, KpiCard, CountUp (BigInt-scaled, no floats), Sparkline, DataTable (sortable, sticky header, card mode < md), Drawer, Modal (shared `lib/useDialog.ts`), Tooltip, Stepper, Timeline, Alert, Amount, TierBadge (risk/TierBadge re-exports it), StatusChip, EmptyState, SuccessMark, Icon (self-made paths, no icon library).
- **Landing (`app/page.tsx`, `components/landing`):** sticky header, hero with 3-state live preview (shortfall -> OTP approval -> forged B/L blocked), problem, how-it-works tabs, 7 feature cards with "See it" -> `/demo?step=N`, security band, impact, measured-results band (honest "dev split", "Coming soon" otherwise), fictional-persona slider, final CTA, footer. Judge mode = `demoLogin("judge@demo.setu")` -> `/demo?judge=1`. `/accessibility`, `robots.ts` (landing, /verify, /accessibility only), `sitemap.ts`, OG image, icons. Assets and licences: `apps/web/public/CREDITS.md`.
- **Shell:** role-grouped collapsible sidebar, top bar (search, language, theme, Bangla-digits toggle, bell, user, Simulated), Ctrl/⌘K palette (lazy), `/` opens chat (resizable sheet, per-page prompts), onboarding checklist, loading/error boundaries for the main routes, 404 and 500 pages (EN/BN/ZH, `global-error` reads the cookie), `lib/MeContext.tsx` (shell shares the loaded user).
- **i18n:** strings in `src/i18n/parts/{ui,landing,shell,pages}.{en,bn,zh}.json` (merged in `i18n/index.tsx`). `pnpm --dir apps/web i18n:check` fails on missing BN keys (all) and missing ZH in landing/a11y/notfound/errpage/sp/chg/common/lang/ui; wired into `pnpm lint` and a Vitest test. 2,149 keys, BN complete.
- **Verified:** vitest 420 passed, eslint + tsc clean, `next build` ok, Playwright `e2e/p22.spec.ts` 5/5 (landing -> demo, language persists, dark toggle persists, palette navigates, axe on `/` and `/accessibility`). Manual sweep (axe wcag2a/2aa/21aa + horizontal overflow + screenshots) over `/ /app /app/deals /app/approvals /demo /demo/run` x EN/BN/ZH x light/dark x 1440/360: no overflow; one serious issue (unreachable scroll region in the demo phone) fixed. Deal detail was not reached by the script.
- **Lighthouse (mobile, production build, local API):** `/` perf 93, a11y 100, best-practices 100, SEO 100. `/demo` perf 85, a11y 100, BP 100, SEO 63. `/app` perf ~77 (was 59; CLS 0.42 -> 0.008), a11y 100, BP 100, SEO 63. SEO 63 on `/app` and `/demo` is `is-crawlable`: they are `noindex` on purpose (robots allow landing and /verify only). `/app` LCP is about 5.5 s because the app is client-rendered and waits for hydration under CPU throttling.
- **Not met / gaps:** `/app` performance below 85; two problem-band figures are "[figure to verify]" and the ADB US$2.5 trillion figure was cited from memory; footer GitHub link and accessibility contact are placeholders; Bangla/Chinese not native-reviewed; no CI runs axe; no manual keyboard-only or screen-reader pass; the chat's older `chat.suggest.*` prompts have no ZH text; Documents nav links to `/app/deals` (no cross-deal documents API); digits toggle remounts the page (local state resets); chat resize drag untested; `src/app/favicon.ico` is the scaffold default.
- **Existing e2e not re-verified:** `approvals`, `chat` (KB citation) and `deals` (Activity tab) specs failed in this run. `GET /deals/SETU-2026-0001/activity` returns 500 on the running agent and the demo DB has no pending approvals, so these look like backend/data state, not the UI; not checked against a clean baseline. Run `pnpm db:reset-demo` against a LOCAL database first.
- **Next phase reads:** this block, `apps/web/public/CREDITS.md`, `docs/PLAN.md` Stage 8.

### 8.1 (from the user's "P23 Production deployment, judge access, README v1 and submission v1" prompt)
- **Branch:** `phase/p23-deploy`. **Nothing is deployed:** no Neon project, Vercel project, VPS, domain, uptime monitor or Anthropic spending cap was created (they need the user's accounts and secrets). Runbook: **`docs/deploy-prod.md`**. The brief's "Prisma" is Alembic here; Python is 3.13 not 3.11.
- **Agent hardening:** rich `GET /health` (`ready`, `kb_indexed`, `audit_key_loaded`, `replay_fixtures_present`, `git_sha`, `built_at`, `demo_mode`, `demo_replay`; status stays "ok", `ready` carries the verdict), in-process sliding-window rate limiter (`app/api/ratelimit.py`, per process, `X-Forwarded-For` only from `TRUSTED_PROXIES`), security-header middleware, 1 MB JSON body cap, `DOCUMENT_MAX_BYTES` 10 -> 4 MB (Vercel 4.5 MB), prod refuses `*`/empty `ALLOWED_ORIGINS`. Judge-permission tests added (own sandbox only). Env names: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_{CHAT,UPLOAD,SANDBOX_CREATE,GLOBAL}_PER_MINUTE`, `TRUSTED_PROXIES`, `MAX_BODY_BYTES`, `GIT_SHA`, `BUILD_TIME`, `DEMO_COOLING_OFF_SECONDS` (alias of `COOLING_OFF_SECONDS`), container-only `UVICORN_WORKERS`, `GRACEFUL_TIMEOUT`, `FORWARDED_ALLOW_IPS`, `PORT`.
- **Containers:** `services/agent/Dockerfile` (build with `docker build --build-context repo=. services/agent`; non-root, fastembed model baked in, 1.29 GB), `apps/web/Dockerfile` (context = repo root, `-f apps/web/Dockerfile .`, plain `next start`, 1.31 GB; build args `AGENT_URL`, `NEXT_PUBLIC_*`, `GIT_SHA`, `BUILD_TIME`), `docker-compose.yml` profile `full` (seed + agent + web; `db` unchanged), `docker-compose.env.example`, `docker-compose.prod.yml` + `infra/caddy/Caddyfile` (VPS). `docker compose config` and `caddy validate` pass; a clean-machine `compose up` was NOT run.
- **Web:** `/judges` (credentials-free one-click judge login, sandbox button, 60-second route, scorecard built from `docs/REQUIREMENTS.md` NOT the official criteria, QR codes), footer system-status chip and version badge, CSP/HSTS/nosniff/frame headers in `next.config.ts` (no CSP errors on a production build), `NEXT_PUBLIC_{JUDGE_EMAIL,JUDGE_NOTE,REPO_URL,VIDEO_URL,STATUS_URL,SITE_URL}`. Unset links show "Link coming", never a dead href.
- **Smoke:** `scripts/smoke_prod` (+ `.py`) passed 10/10 against a freshly built agent container and against the working tree on a spare port. Against the long-running local dev agent only 4/10 (old code, sandbox-create limit). `apps/web/e2e/smoke-prod.spec.ts`: landing, /judges, /verify, privacy playground pass; judge mode, guided demo and sandbox reset were blocked by the sandbox rate limit, attack console by a backend "unexpected error" (same failure in `attack-console.spec.ts`). **Prod smoke was never run twice.**
- **Secret scan:** gitleaks over full history: no `.env`/`keys/` ever committed; 15 `generic-api-key` hits are all false positives (14 sha256 cache keys in `data/demo/fixtures`, one variable name in a test).
- **Submission drafts (`README.md`, `docs/submission/*`):** technical documentation (+ PDF), deck outline, security self-assessment, execution evidence, checklist, email draft. Every unknown is `[TO FILL]`: team name, members, universities, URLs (live, judges, status, repo, video), project licence, production export, registration form + passport bio status. The production operation-log export does not exist yet.
- **Needs the user:** commit `docs/submission/audit-public-key.pem` (was ignored by `*.pem`, `.gitignore` now excepts it; set the host `AUDIT_SIGNING_KEY` to the matching key); rotate any key ever pasted into chat; run `make types`; the root disk was at 100% during builds (an agent pruned old Docker build cache, ~8 GB).
- **Known gaps:** registry tests fail without a migrated `DATABASE_URL`; attack-console backend error on the local agent not diagnosed; `/app` Lighthouse perf below 85 (see 6.3); two landing figures still "[figure to verify]"; wildcard CORS refusal only when `APP_ENV=prod`; judges without a sandbox cookie can still call `/demo/simulate/*` (shared data, by design); limits are per process (several workers or instances multiply them).
- **Next phase reads:** this block, `docs/deploy-prod.md`, `docs/submission/SUBMISSION_CHECKLIST.md`.

### P29 In-app Documentation Center (from the user's "Phase P29 — In-app Documentation Center" prompt)
- **Branch:** `phase/p29-docs-center`. No `docs/SRS.md`; requirements come from `docs/REQUIREMENTS.md` (mapped in `frontend/content/docs/requirements-map.json`). Paths in the brief (`apps/web`) are `frontend/` here. Authoring guide: `frontend/content/docs/AUTHORING.md`.
- **Content:** MDX in `frontend/content/docs/{en,bn,zh}/<section>/<name>.mdx`: 51 EN + 51 BN pages, 11 ZH (supplier guide + getting started). Sections: getting-started, buyer (16), supplier (7), admin (11), judge (5), security (6), faq, glossary. Every feature page follows the template (what-it-is / who / when / how-to / results / tips / security / try-it / related). Written by subagents from the real routes, i18n strings and backend docs; **106 `{/* REVIEW: ... */}` comments** mark claims nobody verified in a running app (list them with `grep -rn "REVIEW:" frontend/content/docs/en`).
- **Stack (all MIT):** `@mdx-js/mdx` (evaluate on the server, `remark-gfm`, `rehype-slug`, own `{#id}` heading-anchor plugin), `gray-matter`, `minisearch`, `unist-util-visit`. Code: `src/lib/docs/*` (content loader, MDX compile, search, route map), `src/components/docs/*`, routes `src/app/docs/[lang]/...`, `src/app/docs-data/{search/[lang],routes}`.
- **UI:** `/docs` -> `/docs/<lang>`; sidebar with role filter (All/Buyer/Supplier/Admin/Judge), "On this page" TOC, breadcrumbs, previous/next, language switch that keeps the page (falls back to the English page with a notice when untranslated), last-updated, thumbs up/down + comment (**stored in this browser's localStorage only**, no backend), print styles, "Download as PDF" = print view of a whole guide (`/docs/<lang>/guide/<buyer|supplier|admin>`, use the browser's Save as PDF), dark mode, 360 px (no horizontal overflow checked on one page). MDX components: Steps, Callout, Screenshot (zoom, falls back to EN image, then a labelled placeholder), RoleBadge, TierBadge, TryItButton, Kbd, FAQ, Video.
- **Search:** client-side MiniSearch, EN/BN/ZH tokenizer (Bangla words, CJK per character), `Ctrl/Cmd K` + `/` inside docs; the app command palette also shows guide results.
- **In-app help:** "?" button in the top bar (app and supplier portal) opens a drawer with the matching guide (iframe `?embed=1`, route -> page from each page's `routes`); (i) `InfoTip`s on tier badges, cooling-off timer, risk decision card and the KYB checks heading; one-time dismissible "New here?" hint per user per page (localStorage). Docs/Guide links in the public header, footer, app and supplier footers; `/docs` is in robots + sitemap.
- **Assistant (RAG):** `user_guide` source type, converter `uv run python -m app.rag.cli userguide` (EN+BN to `rag_agent/kb/sources/generated/user-guide/`), citations carry `guide_url`, chat Sources list shows an "Open guide" link (only for same-site `/docs/...` URLs), agent@9 / respond@7 prompts tell the model to answer how-to questions from the guide. **NOT finished:** see blockers.
- **Keeping docs accurate:** `pnpm docs:check` (Vitest, `src/lib/docs/*.test.ts`): every page compiles, every app route is documented, every documented route exists, every `FR/SR/NFR` maps to pages, internal links + anchors + app routes resolve, BN for all pages and ZH for supplier/getting-started, translations keep order/roles/routes/heading ids, screenshot alt text, template anchors. `pnpm docs:shots` (`scripts/docs-screenshots.mjs`): Playwright signs in as each demo role and writes `public/docs-images/<lang>/<name>.png` from the `<Screenshot route as wait click>` tags.
- **Verified:** vitest 99 files / 624 passed (includes the docs checks), tsc + eslint + i18n:check clean, `next build` ok (docs prerendered), Playwright `e2e/docs.spec.ts` 7/7 against a production build (filter Supplier -> page -> 中文 keeps the topic, search "OTP", Bangla page search, "?" on /app/approvals, Try it -> /demo, PDF print view, feedback persists); one screenshot of a docs page reviewed by eye at 1280 px.
- **Blockers / not done:**
  1. **Chat still cannot cite the guide.** Done (user-approved, security-reviewed PASS WITH FIXES, fixes applied): `kb_chunks.trusted` (migration `b7d3e9a1c4f6`), set only by `ingest.load_chunks` for `user_guide` sources with id `user-guide-*` whose parent folder is exactly `generated/user-guide`; trusted chunks skip the index-time refusal and `retrieve.search`'s detector passes, but are refused if they contain control/format characters other than ZWNJ/ZWJ (Bangla needs them). Detector, patterns and `<retrieved_document>` wrapping untouched. Real guide loads: 654 trusted chunks, EN how-to query ranks `buyer/approvals`, BN ranks `security/permission-tiers` (test embedder). **Still open:** `agent/registry.py` `scan_result` re-scans `search_knowledge` snippets and flags guide text (`MONEY_COMMAND`), which stops the turn with a Tier 3 `INJECTION_DETECTED`. Reviewer's minimal fix: add `trusted` (from the DB column only) to `Snippet`/`CitationSnippet`, and make `scan_result(data, tool)` skip a snippet only when `tool == "search_knowledge"`, card_type is citations and `trusted is True`; needs the user's approval (it edits the second gate) plus registry tests. The generated guide KB files are NOT committed/present: with them indexed, 4 hash-embedder ranking tests in `tests/api/test_rag.py` and `test_chunker.py` fail (guide pages outrank the fixtures); regenerate with `uv run python -m app.rag.cli userguide` then `kb:index`.
  2. **Demo replay fixtures are stale** (prompt bump): `tests/demo/test_cli.py` (2) and `test_run.py` (1) fail until `pnpm demo:record` runs with a real model key.
  3. **Screenshots were never generated** (no running seeded stack here): the pages show the labelled placeholder until `pnpm docs:shots` runs. Several shots need a specific record (a deal id, supplier UUID, Tier 3 approval, COMPLETED deal) or multi-step clicks; the pages list these as REVIEW items. Admin KB and evaluation pages have no screen (their screenshots point at the nearest real page).
  4. `schema.gen.ts` not regenerated (`make types` needs the agent running): `Citation` is extended by hand with `guide_url`.
  5. Judge `criteria` page is built from `docs/REQUIREMENTS.md`: the official criteria are not in the repo. No video/GIF assets. Bangla/Chinese not native-reviewed. Feedback is local only. No keyboard-only / screen-reader pass; axe not run on `/docs`.
- **App inconsistencies the writers found (not fixed):** `.claude/rules/security.md` vs code on the fraud-score scale (code: 0-100, Tier 3 above 60) and on which tiers the LLM can call (`MAX_LLM_TOOL_TIER = T0`); FX rate lock has no UI button; `/account-status` text still says onboarding "is coming"; several `doc.*`/`ms.*` keys have no ZH text; `chat.suggest.kb` means different things in EN and BN; Bangla uses "চুক্তি" / "ডিল" / "অর্ডার" for the same thing.
- **Next phase reads:** this block, `frontend/content/docs/AUTHORING.md`.

## Known issues / risks
- 1.2: the local `.env` / `.env.example` `DATABASE_URL` points at a hosted Postgres, so `db:migrate`/`db:seed` without
  an override write there. Local verification used `DATABASE_URL=postgresql://setu:setu@localhost:5435/setu`.
- Compose requires `POSTGRES_USER/PASSWORD/DB` from root `.env` (fails fast with a message if missing). On the dev
  machine host port 5432 is taken by a native Postgres — verification ran with `POSTGRES_PORT=5435`.
- Production routing of `/api/*` → FastAPI (prefix stripping) is decided in Phase 8.1; locally the Next rewrite strips it.

## Metrics (filled by Phase 7.2)
| Metric | Before | After | n |
|---|---|---|---|

## 2026-10-20 — Repo restructure (no behaviour change)
- `apps/web` → `frontend/`; `services/agent` → `backend/`; LangGraph agent + RAG (`app/agent`, `app/rag`, `kb/`) → `rag_agent/`.
- `app.agent` / `app.rag` still import unchanged: `backend/app/__init__.py` adds `rag_agent/app` to the package path.
- Tests stay in `backend/tests` (incl. `agent/`, `rag/`); verified identical to before: 768 passed / 31 failed (Postgres not running) / 538 skipped; vitest 433 passed.
- Env files: `frontend/.env.local`, `backend/.env`, `rag_agent/.env` (see the `.env.example` in each). Root `.env` is still read first.
- Older entries in this file use the previous paths (`apps/web`, `services/agent`).
