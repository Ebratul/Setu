# Setu — Progress log

Updated at the end of every phase by the `phase-handoff` skill. Newest entries at the bottom.
Times are Dhaka (UTC+6). Deadline: 20 Oct 2026 21:59 Dhaka. Must-have cut line: 19 Oct 23:59.

## Phase checklist
- [x] 0.1 · [x] 1.1 · [x] 1.2 · [ ] 1.3
- [x] 2.1 · [ ] 2.2 · [ ] 2.3 · [~] 2.4 (i18n, fonts, shell, client only) · [ ] 2.5 · [~] 2.6 (analysis half done; financing open)
- [ ] 3.1 · [ ] 3.2 · [ ] 3.3 · [ ] 3.4
- [ ] 4.1 · [ ] 4.2 · [ ] 4.3 · [ ] 4.4 · [ ] 4.5
- [ ] 5.1 · [ ] 5.2 · [ ] 5.3 · [ ] 5.4 · [ ] 5.5
- [ ] 6.1 · [ ] 6.2
- [ ] 7.1 · [ ] 7.2
- [ ] 8.1
- [ ] 9.1 · [ ] 9.2 · [ ] 9.3

## Log

| Phase | Date (Dhaka) | Status | What was done | Test result | Handoff note |
|---|---|---|---|---|---|
| setup | 2026-10-17 | done | Planning session: CLAUDE.md, rules, agents, skills, hooks, PLAN/REQUIREMENTS/PROGRESS docs. No app code. | hook pipe-tests pass | Start Phase 0.1 in a fresh session. |
| 0.1 | 2026-10-17 02:39 | done | Monorepo scaffold: pnpm workspace, Next.js 16 web + status card, FastAPI agent /health, pgvector compose, Makefile, env examples, README. | pytest 4 passed · vitest 2 passed · lint/tsc/ruff clean · build ok | Copy .env.example → .env; `pnpm run db:up`, `pnpm run dev`. Next: Phase 1.1 schema. |
| 1.1+1.2 | 2026-10-17 03:35 | done | All 26 tables + initial Alembic migration; Money helpers; audit-chain primitives; deterministic P03 demo seed (Rahima/SETU-2026-0001), reset-demo, verify_seed. | pytest 45 passed (incl. 7 db) · vitest 2 · ruff clean · verify_seed 18/18 · security review: pass with fixes (highs fixed) | Read data/demo/README.md + docs/data-model.md. Read endpoints deferred to next phase. |
| 2.1+2.6a (P05) | 2026-10-17 04:07 | done | FR-3 domain lib + 5 analysis endpoints, demo-login stub, /app shell, EN/BN i18n, order analysis, calculator, monthly summary, supplier scorecard pages. | pytest 105 passed · vitest 13 passed · Playwright smoke 1 passed · lint/tsc/ruff clean · next build ok · security review: pass with fixes (fixed) | Financing UI (2.6) + FR-1 engine (2.2) next. Margin is 18.01, not 18.00. |

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

## Known issues / risks
- 1.2: the local `.env` / `.env.example` `DATABASE_URL` points at a hosted Postgres, so `db:migrate`/`db:seed` without
  an override write there. Local verification used `DATABASE_URL=postgresql://setu:setu@localhost:5435/setu`.
- Compose requires `POSTGRES_USER/PASSWORD/DB` from root `.env` (fails fast with a message if missing). On the dev
  machine host port 5432 is taken by a native Postgres — verification ran with `POSTGRES_PORT=5435`.
- Production routing of `/api/*` → FastAPI (prefix stripping) is decided in Phase 8.1; locally the Next rewrite strips it.

## Metrics (filled by Phase 7.2)
| Metric | Before | After | n |
|---|---|---|---|
