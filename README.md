# Setu (সেতু) — AI SME Finance Copilot

**Setu** (Bangla: *bridge*) is an AI copilot for Bangladeshi small and medium businesses that **import from Chinese suppliers**.
It answers the questions an importer faces before and during every order: *Can I afford this order? Which financing is cheapest?
Will my cash run out before the goods arrive? Are this supplier and these documents genuine? Is this "new bank account" email a scam?*
Then it pays the supplier through **milestone escrow** with **risk-tiered human approval**.

Built for **FinTechathon 2026, International Track, Topic E**.

> **All money movement is a simulated sandbox. No real payment rails, no real lenders, no real people.
> All data (people, companies, banks, rates, lenders) is fictional or mock. No model was trained.**
> Claude models are called only to explain results and to fill missing document fields.
> **The LLM explains, code executes:** every number (cost, margin, gap, FX, fraud score, permission tier) comes from deterministic Python.

| | |
|---|---|
| **Live demo** | https://setu-rouge-omega.vercel.app (demo mode; the deployment is behind Vercel Authentication, so access is on request) |
| **Judge page** | `/judges` on the live demo |
| **Demo video (≤ 5 min)** | [TO FILL: video URL] |
| **Status page** | [TO FILL: status URL] |
| **Source** | https://github.com/Ebratul/Setu |
| **Team** | [TO FILL: team name, members, universities] |

## Contents
[The problem](#the-problem) · [What it does](#what-it-does) · [Who uses it](#who-uses-it) · [Accounts, onboarding and verification](#accounts-onboarding-and-verification) ·
[Security model](#security-model-summary) · [Architecture](#architecture) · [Measured results](#measured-results) · [Run locally](#run-locally) ·
[Configuration](#configuration) · [Deployment](#deployment) · [Documentation](#documentation) · [Tests](#tests-and-evaluation) ·
[Project structure](#project-structure) · [Limitations](#limitations-and-known-risks) · [Licences](#third-party-licences)

## The problem

A Bangladeshi garment or trading SME that imports fabric, accessories or machinery from China typically faces four problems at once:

1. **Financing gaps.** The supplier wants an advance, the buyer's cash arrives weeks later, and the options (bank LC, supplier credit,
   invoice financing, overdraft) are hard to compare on real total cost.
2. **Cash-flow timing.** Duty, freight, FX moves and deadlines pile up on specific days, and a shortfall is only noticed when it hits.
3. **Supplier and document risk.** Fake or tampered bills of lading, invoices that were already financed elsewhere, and names that
   almost match but do not.
4. **Payment-redirect fraud.** An urgent email "from the supplier" says the bank account changed and asks to pay today.

Setu puts all four in one place, in English, Bangla and Chinese, and never lets an AI model move money on its own.

## What it does

Setu's rule: **the LLM explains, code executes.** The model can read tool results and write plain-language
answers (English, Bangla, Chinese). It cannot move money. Tools offered to the model are Tier 0 only.
Tier 2 and Tier 3 actions need a person to press a button (and, for Tier 3, enter a one-time code after a pause).

### Features mapped to Topic E requirements

IDs come from [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) (the stand-in for the SRS).

| ID | Requirement | What is built | Where to see it |
|---|---|---|---|
| FR-1 | Financing-option matching | Financing gap (shortfall mode and order mode), 5 simulated options ranked by total cost, effective annual rate, tenor, collateral, eligibility, with reasons | `/app/financing` |
| FR-2 | Cash-flow management and alerts | 90-day day-by-day forecast, what-if scenarios, alerts for shortfall, deadlines (notice and action windows, critical at one day) and FX timing | `/app`, `/app/cashflow` |
| FR-3 | Business financial analysis | Landed cost, gross margin, break-even, supplier scorecard, monthly summary | `/app/orders/[id]/analysis`, `/app/analysis` |
| FR-4 | Supplier KYB | Fuzzy name match (licence / invoice / account holder), personal-account, account-age, country, sanctions (mock list), pending-change checks; KYB score | `/app/suppliers` |
| FR-5 | Milestone escrow | 30/60/10 or custom schedule, state machines, double-entry simulated ledger, evidence-gated release | `/app/deals` |
| FR-6 | Trade-document forensics | PDF extraction, hidden-text detection, 11 cross-checks, fraud score, SHA-256 + semantic registry that blocks duplicate financing across lenders | document viewer, `/app/admin/registry` |
| FR-7 | USD vs CNY route + rate lock | Route comparison (spreads and fees are labelled MOCK) and a mock FX lock (Tier 2) | chat, deal page |
| FR-8 | Signed credit record | Ed25519-signed JSON record when escrow completes; verify endpoint | deal page, `/api/credit-records/...` |
| FR-9 | Multilingual explained chat | EN and BN chat (ZH for the supplier view), "Why" line on answers, cited knowledge base | `/app/chat` |
| (extra) | Real accounts | Sign in with Google (through Neon Auth) or email and password; role-based onboarding with automatic checks, an admin verification queue and a hard "not verified" lock on every money action | `/login`, `/onboarding`, `/app/admin/verifications` |
| (extra) | Documentation Center | 50+ role-based guides (buyer, supplier, admin, judge, security, FAQ, glossary), EN and BN, ZH for the supplier guide; client-side search; in-app "?" help; the chat assistant can cite them | `/docs` |
| (extra) | Guided demo and judge sandboxes | 12-step scripted walkthrough that replays recorded AI answers offline; per-judge sandbox data | `/demo`, `/judges` |

Not built or partly built: see [Limitations](#limitations-and-known-risks).

## Who uses it

| Role | Who | What they can do |
|---|---|---|
| **Buyer** | A Bangladeshi importer (SME) | Everything above for their own company: analysis, financing, cash flow, deals and escrow, document checks, team members |
| **Supplier** | A Chinese exporter | See their deals, propose or confirm milestones, upload evidence, request a payout-account change (always a Tier 3 approval) |
| **Admin** | Setu staff | Review company verifications (approve, request changes, reject, suspend), KYB, registry, audit log. Needs authenticator-app (TOTP) 2FA |
| **Judge** | A competition judge | Read-only tour with their own sandbox data; cannot move money or reach admin decisions |

## Accounts, onboarding and verification

Setu supports two sign-in shapes (`AUTH_MODE`): **demo** (pick a pre-made account, no password; the judge deployment) and **neon**
(real accounts through Neon Auth: Google, or email and password). With `AUTH_MODE=neon` the demo login is off unless a
staging-only flag turns it on, and production refuses to start with it on.

```mermaid
flowchart LR
  G["Continue with Google<br/>(email must be verified)"] --> R["Choose role<br/>buyer or supplier<br/>(admin = allowlist, judge = invite code)"]
  R --> C["Contact + phone OTP"] --> B["Business details<br/>(role-specific, validated)"]
  B --> D["Upload documents<br/>(magic-byte check, private storage)"] --> K["Consent + optional TOTP 2FA"]
  K --> S["Review and submit"] --> A["Automatic checks<br/>duplicate company, sanctions,<br/>KYB, document reuse"]
  A --> Q["Admin queue<br/>approve / request changes /<br/>reject / suspend"] --> OK["ACTIVE<br/>money actions unlocked"]
```

- **Until a human approves the account it stays `PENDING_VERIFICATION`.** The user can read their own workspace, but every money action
  (create a deal, fund or release escrow, FX lock, payout-account change, financing application, approvals) returns `403 ACCOUNT_NOT_VERIFIED`.
  The check runs in the API layer and again in the service layer.
- **Buyer fields:** legal and trade name, trade licence (number, authority, expiry), IRC, TIN, address, business type, imports, volume range.
  **Supplier fields:** legal name in English and Chinese, Unified Social Credit Code (18 characters, official checksum), address, scope, export experience, bank account.
- **Sensitive values** (phone, licence, TIN, USCC, bank account) are encrypted at rest, shown masked, and never sent to a model.
- **Admin review:** decisions need a fresh authenticator code (email codes are not accepted), revealing a sensitive field needs a written reason,
  nobody can decide their own account, and every step is in the signed audit log.
- Why we ask for these details: see the in-app guide *Why Setu asks for these details* (`/docs`).

## Security model (summary)

| Control | Requirement | How it works |
|---|---|---|
| Permission tiers | SR-1, SR-2 | A deterministic engine (`app/services/risk/engine.py`, thresholds in `backend/config/risk.yaml`) decides Tier 0 to 3 or BLOCK. Highest tier wins. The agent can only queue requests. |
| Tier 3 step-up | SR-9 | Cooling-off pause (600 s default, floor in prod), then a 6-digit OTP (5 min life, 3 wrong codes lock the request). Demo mode: shown in a simulated "Demo phone" panel. Neon mode: e-mailed to approvers, plus a four-eyes rule. |
| Privacy Gateway | SR-4 | Masks NID, passport, phone, account, IBAN, SWIFT, email, known names and amounts with reversible tokens before every model call. Code restores values in the answer. |
| Injection defence | SR-3 | Five switchable or fixed layers: structural wrapping, detector, capability control (money tools only propose; flagged documents force Tier 3), tool gating, output guard. |
| Audit log | SR-5 | Every agent, user and system action is an Ed25519-signed, hash-chained row. Anyone with the public key can verify an export (`pnpm audit:verify`, `/verify`). |
| Duplicate registry | SR-6 | Exact (file hash) and semantic (invoice fields) fingerprints across contexts and lenders. |
| Account verification | SR-1 | `ACCOUNT_NOT_VERIFIED` gate on every money action; admin decisions need a TOTP step-up; suspending or rejecting a company freezes the whole business. |
| Data at rest | SR-4 | Application-level encryption (Fernet) for phone, licence, TIN, USCC and bank numbers; masked in every API response; revealing a field is audited. |
| Sandbox only | SR-8 | Every money action is labelled "Simulated". The escrow and ledger are internal; there is no external payment code. |

Details: [`docs/submission/SECURITY_SELF_ASSESSMENT.md`](docs/submission/SECURITY_SELF_ASSESSMENT.md).

## Architecture

```mermaid
flowchart LR
  subgraph Browser["Browser (judge / SME / supplier)"]
    WEB["Next.js app<br/>frontend<br/>EN / BN / ZH"]
    VER["/verify page<br/>Web Crypto, no upload"]
  end

  subgraph API["FastAPI service: backend"]
    direction TB
    ROUTERS["HTTP routers<br/>app/api"]
    AUTH["Session + role checks<br/>BUYER / SUPPLIER / ADMIN / JUDGE"]
    subgraph AGENT["LangGraph agent (Tier 0 tools only)"]
      PG["Privacy Gateway<br/>mask before every model call"]
      RT["router"] --> AG["agent + tools"] --> RS["respond"]
      WRAP["Injection layers 1,2,4,5<br/>wrap, detect, gate, guard"]
    end
    subgraph CODE["Deterministic code (no LLM)"]
      DOM["app/domain<br/>landed cost, financing, cash flow,<br/>FX route, escrow, KYB"]
      FOR["app/forensics<br/>extract, hidden text, 11 checks, score"]
      REG["hash registry<br/>exact + semantic"]
      RISK["risk-tier engine<br/>config/risk.yaml"]
      APPR["approvals<br/>Tier 2 tap, Tier 3 cooling-off + OTP"]
      ESC["escrow + simulated ledger"]
    end
    AUD["signed hash-chained audit log<br/>Ed25519, setu-audit-v2"]
  end

  subgraph DATA["PostgreSQL + pgvector"]
    DB[("business tables, audit_log,<br/>kb_chunks, checkpoints")]
  end

  LLM["Claude models via app/llm/client.py<br/>(Anthropic or OpenRouter, or offline mock)"]
  LS["LangSmith traces<br/>(masked input)"]

  WEB -->|"/api/*"| ROUTERS
  ROUTERS --> AUTH
  AUTH --> AGENT
  AUTH --> CODE
  PG --> LLM
  LLM --> LS
  AG -->|"propose only"| RISK
  RISK --> APPR
  APPR -->|"human click executes"| ESC
  FOR --> REG
  FOR --> RISK
  DOM --> RISK
  ESC --> AUD
  APPR --> AUD
  AGENT --> AUD
  CODE --> DB
  AUD --> DB
  VER -.->|"public key + JSONL export"| AUD
```

The same diagram is saved as [`docs/architecture.mmd`](docs/architecture.mmd). No SVG/PNG image was generated
(Mermaid CLI is not installed in this repo and was not fetched). GitHub renders the Mermaid block above.

### Stack

Next.js 16 (App Router, TypeScript, Tailwind v4) · FastAPI on Python 3.13 · LangGraph + LangChain ·
SQLAlchemy 2 + Alembic · PostgreSQL 16 + pgvector. Models: `claude-haiku-5-5` (router, agent, answers) and
`claude-sonnet-5-5` (document tasks), through Anthropic or OpenRouter. With no key the service runs an offline
deterministic mock model. Full description: [`docs/submission/TECHNICAL_DOCUMENTATION.md`](docs/submission/TECHNICAL_DOCUMENTATION.md).

## Measured results

Every number below is from the **test split of synthetic data** (`backend/eval/results/metrics.json`, generated
2026-10-20; thresholds were tuned on the dev split only). They are **ceilings on synthetic data, not real-world
accuracy.** No LLM extraction was used in this run.

| Area | Result (test split, synthetic) |
|---|---|
| Document forensics, 100 packs | WARN or FAIL = flagged: precision 1.0, recall 1.0 on 11 checks and all 10 fraud types. 0/50 clean packs flagged; 50/50 tampered packs have an unpassed document. FAIL only: recall 0.9508 (3 subtle name variants are WARN by design). |
| Duplicate-document registry | 5/5 caught (exact 2/2, near-duplicate 3/3) |
| Prompt injection, 12 attacks | Attack success: defences off 100%, on 0%, on without the detector 0%. Detection recall 100%; false positives 0/300 clean documents. Money moved 0 in all modes. |
| Privacy Gateway, 600 documents | Ground-truth bank identifiers in the model payload: masking off 600, on 0. Field extraction accuracy 1200/1200 in both modes. |
| Auto vs escalated (USD 3,000 release per pack) | Clean 50/50 auto (Tier 0/1); tampered 0 auto, 27 escalated (Tier 2/3), 23 blocked. Tampered packs auto-released: 0. |
| Demo numbers | Landed cost USD 11,200.00, margin 18.01%, shortfall USD 1,560.00 on 2026-11-07 (`docs/finance-formulas.md`) |

Not measured: real documents, a real model against the injection set (the harness uses an "obedient" mock model, so it
does not show that layer 1, the delimiters, binds a real model), real-model answer quality at scale.
Full method and limits: [`docs/submission/TECHNICAL_DOCUMENTATION.md`](docs/submission/TECHNICAL_DOCUMENTATION.md) section 8.

## Run locally

### Option A: Docker (fallback, one command)

```bash
docker compose --env-file docker-compose.env.example --profile full up --build
```
Builds `backend/Dockerfile` and `frontend/Dockerfile`, starts Postgres + pgvector, seeds the demo data and runs the
agent (http://localhost:8000/health) and the web app (http://localhost:3000) with recorded AI answers (no key needed).
The file holds harmless local placeholders only. A run on a clean machine is not recorded in `docs/PROGRESS.md`.

### Option B: development mode

#### Prerequisites
- Node.js LTS (≥ 22) with pnpm (`corepack enable` or `npm i -g pnpm`)
- Python 3.13 (uv installs it automatically if missing)
- [uv](https://docs.astral.sh/uv/) — macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Docker Desktop (or Docker Engine + Compose v2)

#### First run
```bash
cp .env.example .env            # local placeholders; never commit .env
pnpm install                    # web deps (pnpm workspace)
uv sync --directory backend
pnpm run db:up                  # Postgres 16 + pgvector on :5432, waits until healthy
pnpm run db:migrate             # create all tables
pnpm run db:seed                # load the simulated demo data
```
If port 5432 is already in use, set `POSTGRES_PORT` (and the port in `DATABASE_URL`) in `.env`.
**Use a local `DATABASE_URL`** (for example `postgresql://setu:setu@localhost:5435/setu`) for `db:migrate`, `db:seed` and
`db:reset-demo`: they write to whatever database `DATABASE_URL` points at.
With no `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` or `XAI_API_KEY`, the agent runs in offline mock mode (deterministic answers).
The RAG embedding model is downloaded once by `pnpm run kb:index` (about 240 MB).

#### Run the services
| Command | What it does |
|---|---|
| `pnpm run dev:agent` | FastAPI backend (includes the agent) on http://localhost:8000 (`/health`, `/docs`) |
| `pnpm run dev:web` | Next.js web on http://localhost:3000 (proxies `/api/*` to the agent) |
| `pnpm run dev` | both together |
| `pnpm run db:down` | stop Postgres (data kept in the `setu-pgdata` volume) |
| `pnpm run db:migrate` | create/upgrade all tables (`alembic upgrade head`) |
| `pnpm run db:seed` / `db:reset-demo` | load the simulated demo data (idempotent) / wipe and reload it |
| `pnpm run kb:index` | embed the knowledge-base sources into pgvector |
| `./scripts/verify_seed` | assert the key demo numbers; see `data/demo/README.md` |
| `pnpm run lint` / `format` / `test` | ESLint + i18n check + tsc + Ruff / Prettier + Ruff format / pytest + Vitest |
| `pnpm run types` | regenerate `frontend/src/lib/api/schema.gen.ts` from the running agent |

`npm run <script>` works too (pnpm must be installed). On macOS/Linux the `Makefile` wraps the same scripts:
`make up down dev test lint format types migrate seed reset-demo verify-seed demo-check`.

#### Try it
Open http://localhost:3000/demo for the guided 12-step walkthrough, or log in with "Login as"
(`/login`). The offline replay check runs without a network: `pnpm run demo:check`.
For the simulated SMS panel and the scam simulator, set `DEMO_MODE=true` (with `APP_ENV` = `dev` and `AUTH_MODE=demo`; see
`docs/demo.md`). Real sign-in (`AUTH_MODE=neon`, including Google) needs a Neon Auth project: see `docs/auth.md` and the Google section below.

### Google sign-in (real accounts)

Google is a social provider inside **Neon Auth**, so the Google client id and secret are entered in the Neon console and never
appear in our env files. Design and API: [`docs/p30-design.md`](docs/p30-design.md).

1. Google Cloud Console: create a project, then **APIs & Services > OAuth consent screen**. User type External, app name,
   support email, authorised domain (your production domain). Scopes: only `openid`, `email`, `profile`. While the status is
   *Testing*, add every tester under **Test users**; set it to *In production* to let anyone sign in.
2. **Credentials > Create credentials > OAuth client ID**, type *Web application*. Authorised redirect URIs: copy the exact
   callback URL shown in the Neon console (Neon Auth > Configuration > OAuth providers > Google). Authorised JavaScript origins:
   `http://localhost:3000` and your production origin.
3. Neon console: enable Google, paste the client id and secret, add `http://localhost:3000` and the production origin to the
   trusted origins, and keep account linking off for unverified providers.
4. Set (names only; see the `.env.example` files): `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (frontend);
   `AUTH_MODE=neon`, `NEON_AUTH_BASE_URL`, `FIELD_ENCRYPTION_KEY`, `ADMIN_EMAIL_ALLOWLIST`, `JUDGE_INVITE_CODES`,
   `DEMO_MODE=false` (backend).
5. First admin: put the admin's Google email in `ADMIN_EMAIL_ALLOWLIST`; they must enable TOTP before any admin access.

## Configuration

Names only. See the `.env.example` files (repo root, `backend/`, `frontend/`, `rag_agent/`). Never commit real values.

| Area | Variables |
|---|---|
| Database | `DATABASE_URL` (use a **local** URL for migrate, seed and tests) |
| Models | `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY` (none set = offline mock model), `SETU_MODEL_FAST`, `SETU_MODEL_REASONING` |
| Auth | `AUTH_MODE` (`demo` or `neon`), `DEMO_MODE`, `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (web), `DEMO_COOKIE_IN_NEON` (staging only) |
| Onboarding | `FIELD_ENCRYPTION_KEY`, `ADMIN_EMAIL_ALLOWLIST`, `JUDGE_INVITE_CODES` (16+ characters each), `TERMS_VERSION`, `SMS_PROVIDER`, `SMS_WEBHOOK_URL`, `SMS_WEBHOOK_TOKEN` |
| Secrets | `AUDIT_SIGNING_KEY`, `DEMO_SESSION_SECRET`, `DOCUMENT_URL_SECRET`, `OTP_SECRET_SEED`, `CRON_SECRET` |
| Safety rails | With `APP_ENV=prod` the agent refuses to start unless `AUTH_MODE=neon`, `DEMO_MODE=false`, strong secrets, an https webhook SMS provider and `FIELD_ENCRYPTION_KEY` are all set |

## Deployment

Runbook with variable names only: [`docs/deploy-prod.md`](docs/deploy-prod.md). Two shapes are supported:

- **Vercel Services + Neon.** `vercel.json` defines two services: `web` (`frontend`, Next.js) and `agent` (`backend`,
  FastAPI), with `/api/*` routed to the agent. Neon PostgreSQL with pgvector; run `pnpm run db:migrate` against it.
- **One VPS.** `docker-compose.prod.yml` with Caddy (automatic HTTPS), web and agent; Neon for the database.

Facts to know:
- Judge deployment: `APP_ENV=dev`, `AUTH_MODE=demo`, `DEMO_MODE=true`, `DEMO_REPLAY=true`. Locked-down: `APP_ENV=prod`
  needs `AUTH_MODE=neon`, `DEMO_MODE=false` and strong secrets; the agent refuses to start otherwise
  (`check_prod_settings`, `backend/app/main.py`).
- Set `AUDIT_SIGNING_KEY` on the host to the key matching `docs/submission/audit-public-key.pem`
  (`GET /api/audit/public-key` reports `matches_committed_key`).
- Never commit `.env*` files. Use `.env.example` for placeholders.
- Smoke test of a running deployment: `BASE_URL=https://... scripts/smoke_prod`.
- **Current production deployment (Vercel, demo mode):** `scripts/deploy_vercel.sh` stages a bundle (the agent root is `backend/`, so
  `rag_agent/`, `data/demo` and the audit public key are copied inside it; `.env*`, keys, tests and uploaded files are excluded) and runs
  `vercel deploy --prod`. Google sign-in is not active on that deployment until the Neon Auth variables are set.
- Database migrations are never run by a deploy. Run `alembic upgrade head` deliberately, against the right database, after taking a
  Neon snapshot or branch.

## Documentation

| Where | What |
|---|---|
| In the app: `/docs` | Role-based user guides (buyer, supplier, admin, judge, security, FAQ, glossary) |
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | Requirements (stand-in for the SRS) |
| [`docs/PLAN.md`](docs/PLAN.md), [`docs/PROGRESS.md`](docs/PROGRESS.md) | Phase plan and the running handoff log |
| [`docs/p30-design.md`](docs/p30-design.md), [`docs/p30-api-shapes.md`](docs/p30-api-shapes.md) | Google sign-in, onboarding and verification: design and API |
| [`docs/auth.md`](docs/auth.md), [`docs/prod-auth-plan.md`](docs/prod-auth-plan.md) | Authentication and the production plan |
| [`docs/risk.md`](docs/risk.md), [`docs/approvals.md`](docs/approvals.md), [`docs/escrow.md`](docs/escrow.md), [`docs/kyb.md`](docs/kyb.md) | Tier engine, approvals, escrow, KYB |
| [`docs/forensics.md`](docs/forensics.md), [`docs/registry.md`](docs/registry.md), [`docs/injection.md`](docs/injection.md), [`docs/privacy.md`](docs/privacy.md), [`docs/audit.md`](docs/audit.md) | Document forensics, duplicate registry, injection defence, Privacy Gateway, audit log |
| [`docs/deploy-prod.md`](docs/deploy-prod.md), [`docs/secrets-rotation.md`](docs/secrets-rotation.md) | Deployment runbook and secret rotation |
| [`docs/submission/`](docs/submission) | Submission documents (technical documentation, security self-assessment, checklist) |

## Tests and evaluation

| Command | What it runs |
|---|---|
| `make test` (= `pnpm run test`) | pytest (agent) + Vitest (web). DB tests need a local pgvector Postgres (see `.claude/rules/testing.md`) |
| `make lint` (= `pnpm run lint`) | ESLint, `i18n:check`, `tsc`, Ruff check and format check |
| `pnpm --dir frontend i18n:check` | fails on missing Bangla keys (all areas) and missing Chinese keys (landing, accessibility, errors, supplier, common) |
| `pnpm --dir frontend e2e` | Playwright end-to-end specs (needs a running stack and `E2E_BASE_URL`; use `E2E_RESET_DEMO=1` with a local `DATABASE_URL` to reset demo data) |
| `pnpm run demo:check` | replay the guided demo offline (27 scenes) |
| `make eval` or `uv run --directory backend python -m eval.run --split test` | the whole evaluation on the **test split** -> `backend/eval/results/metrics.json` and `metrics.md` (needs `data/generated` and a database for the duplicate-registry part) |
| `uv run --directory backend python -m app.forensics.eval_dev` | forensics, dev split (needs `data/generated`) |
| `uv run --directory backend python -m app.forensics.eval_registry` | duplicate-hash catch rate, dev split |
| `uv run --directory backend python -m app.security.injection.suite dev` | injection attack success OFF vs ON, dev split |
| `uv run --directory backend python -m app.privacy.eval dev` | PII leakage ON vs OFF, dev split |
| `uv run --directory backend python -m synthetic.generator --clean 100 --tampered 100 --seed 42` | regenerate the synthetic trade-document set (git-ignored output) |
| `pnpm run audit:verify` / `audit:export` | verify the audit chain / export the operation log (see `docs/submission/EXECUTION_EVIDENCE.md`) |

Last recorded runs (2026-10-21, local Postgres): backend pytest **1,636 passed, 2 skipped** (the whole suite except `tests/demo`;
3 demo-replay tests fail until the recorded fixtures are refreshed with `pnpm demo:record`); frontend Vitest **704 passed**;
Playwright `playwright.p30.config.ts` (mock Neon Auth server, real backend) **11 passed**: buyer onboarding through to approval,
supplier in Chinese, unverified email, demo-login visibility, validation errors, axe checks. Some older Playwright specs
(`approvals`, `chat`, `deals`) failed in an earlier run and were not re-checked.
**Do not run DB tests against a hosted `DATABASE_URL`**; use the local compose database.

## Project structure

```
frontend/                 Next.js app (src/app routes, src/components, src/i18n, e2e/)
backend/
  app/api/                FastAPI routers
  app/domain/             deterministic money logic (landed cost, financing, cash flow, FX, escrow, KYB)
  app/services/           orchestration, risk engine (services/risk), approvals, registry, credit record, onboarding, MFA, SMS
  app/forensics/          PDF extraction, hidden-text detector, cross-checks, scoring, dev evaluation
  app/security/           tiers, policy, injection/ (layers 1-6), email guard, field encryption, TOTP
  app/privacy/            Privacy Gateway (detectors, vault, gateway, eval)
  app/audit/              signed hash-chained audit log (scheme, writer, verify, export)
  app/auth/               demo login, Neon Auth JWT verification, account-status gate
  app/llm/                the only place models are called (+ replay fixtures)
  app/demo/               guided demo runner and judge sandboxes
  app/db/, alembic/       SQLAlchemy models and migrations (single schema owner)
  config/risk.yaml        risk-tier thresholds
  seed/, synthetic/       demo seed data, synthetic trade-document generator
  eval/                   evaluation harness (run.py) and results/
  tests/                  pytest (whole suite, including agent/ and rag/)
rag_agent/
  app/agent/              LangGraph nodes, tool registry and tools (runs inside the backend process)
  app/rag/                knowledge-base chunker, embeddings, hybrid retrieval
  kb/sources/             knowledge-base markdown (our own summaries)
data/demo/                demo script, demo files, fixtures
docs/                     requirements, plan, progress, per-area references, submission/
infra/                    db/init.sql (pgvector extension), caddy/Caddyfile
scripts/                  run-local.sh, verify_seed, smoke_prod, gen-types.sh
```

## Simulated data disclaimer

Setu is a competition prototype. Rahima, Karim, the suppliers, banks, lenders, FX rates, duty
rates, price bands and sanctions list are fictional or mock. Financing products are simulated. OTP codes are shown
in a simulated SMS panel. The Bangladesh Bank figures in the knowledge base are simplified summaries, not
independently verified, and are marked "verify with the official circular". Nothing here is financial advice.

## Limitations and known risks

The full list with sources is in `docs/submission/SECURITY_SELF_ASSESSMENT.md`. Main points:
the judge deployment uses demo login (Google and email sign-in through Neon Auth exist; the P30 code had two internal security-review passes and no external audit), no real payment rails and no live SMS provider (a generic webhook provider exists but is not connected to a service), synthetic-only evaluation (test split run once), the injection test uses a mock model,
Bangla and Chinese text not reviewed by native speakers, `/app` Lighthouse mobile performance about 77 (target was 85),
no on-chain registry anchor, audit-table owner can truncate the table (use a non-owner DB role in production).

## Third-party licences

Licences below were read from package metadata in the local installs (`uv` virtualenv and `node_modules`) on the
build machine, except where marked.

**Web (`frontend`)**
- `@neondatabase/auth` 0.6.0-beta (Neon Auth client) — Apache-2.0
- Next.js 16.4.1, React 19.3.0, React DOM, Tailwind CSS 4.3.3, Recharts 3.10.1 (charts), `qrcode` 1.5.4 (receipt QR codes), `@noble/ed25519` 3.0.0 (browser verification fallback) — MIT
- TypeScript 5.9.3, Playwright 1.64.1 (dev), jsQR 1.4.0 (dev, QR tests) — Apache-2.0
- `@axe-core/playwright` 4.14.0 (dev only, accessibility tests) — MPL-2.0
- Vitest 5.0.5 (dev) — MIT
- Fonts [Inter](https://rsms.me/inter/), [Noto Sans Bengali](https://fonts.google.com/noto/specimen/Noto+Sans+Bengali), [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) — SIL Open Font License 1.1 (via `next/font/google`)
- Icons: self-made SVG paths in `src/components/ui/Icon.tsx`; favicon, OG image and landing mock screens drawn for Setu. `src/app/favicon.ico` is the Next.js scaffold default; its licence is **unverified** (replace before submission). See `frontend/public/CREDITS.md`.
- The Colorlib "Pexcon" template was visual inspiration only; no code, CSS, text or images were copied.

**Agent (`backend`)**
- PyJWT 2.15.1 (Neon Auth token verification), langchain-xai 1.3.0 (last-resort model provider) — MIT; httpx 0.28.1 (mail and SMS-webhook calls; installed with `fastapi[standard]`) — BSD-3-Clause
- FastAPI 0.143.3, Alembic 1.20.0, SQLAlchemy 2.1.4, pydantic-settings 2.16.0, LangChain 1.4.6, LangChain-core 1.6.12, langchain-anthropic 1.7.6, LangGraph 1.2.15, langgraph-checkpoint 4.3.0, langgraph-checkpoint-postgres 3.2.0, LangSmith SDK 0.14.11, pgvector (Python) 0.5.1, pyotp 2.10.0, PyYAML 6.0.3, rapidfuzz 3.14.6 — MIT
- structlog 26.1.0 — MIT OR Apache-2.0
- cryptography 50.0.2 — Apache-2.0 OR BSD-3-Clause
- fastembed 0.9.0 — Apache-2.0
- pdfplumber 0.11.10 — MIT (classifier)
- ReportLab 5.0.1 — BSD-style (synthetic trade-document PDFs)
- Pillow 12.3.0 — MIT-CMU; NumPy 2.5.4 — BSD-3-Clause and others (synthetic fabric photos)
- psycopg 3.3.6 and psycopg-pool 3.3.3 — **LGPL-3.0** (used unmodified as a dependency)
- Embedding model: [`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) — Apache-2.0 (as stated on the model card; not re-checked in this build; downloaded once to `~/.cache/setu-fastembed`)
- Models called by API: Claude Haiku 5.5 and Sonnet 5.5 (OpenRouter, Anthropic direct, or xAI Grok as the last resort when quota is used up). Used under the provider terms; nothing was trained or fine-tuned.

**Infrastructure:** PostgreSQL 16 and the `pgvector` extension (docker image `pgvector/pgvector:pg16`) — [TO FILL: confirm licence text for the final submission if required].

Project licence of Setu itself: [TO FILL: choose and add a LICENSE file; none exists in the repo].

## Team

- Team name: [TO FILL]
- Members and universities: [TO FILL]
- Contact: [TO FILL]
