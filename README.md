# Setu (সেতু) — AI SME Finance Copilot

FinTechathon 2026 International Track, **Topic E**. Setu helps Bangladeshi SMEs that import from Chinese suppliers.
It compares financing options, forecasts cash flow, analyses order cost, checks supplier and trade documents,
and pays suppliers through milestone escrow with risk-tiered human approval.

> **All money movement is a simulated sandbox. No real payment rails, no real lenders, no real people.
> All data (people, companies, banks, rates, lenders) is fictional or mock. No model was trained.**
> Claude models are called only to explain results and to fill missing document fields.
> Every number comes from deterministic Python code.

- **Live demo:** [TO FILL: live URL]
- **Judge page:** [TO FILL: live URL]/judges (page is being added in P23 Part B; not verified here)
- **Demo video (≤ 5 min):** [TO FILL: video URL]
- **Status page:** [TO FILL: status URL]
- **Source:** [TO FILL: repository URL]
- **Team:** [TO FILL: team name, members, universities]

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

Not built or partly built: see [Limitations](#limitations-and-known-risks).

## Security model (summary)

| Control | Requirement | How it works |
|---|---|---|
| Permission tiers | SR-1, SR-2 | A deterministic engine (`app/services/risk/engine.py`, thresholds in `services/agent/config/risk.yaml`) decides Tier 0 to 3 or BLOCK. Highest tier wins. The agent can only queue requests. |
| Tier 3 step-up | SR-9 | Cooling-off pause (600 s default), then a 6-digit OTP (5 min life, 3 wrong codes lock the request). Shown as a simulated SMS in a "Demo phone" panel. |
| Privacy Gateway | SR-4 | Masks NID, passport, phone, account, IBAN, SWIFT, email, known names and amounts with reversible tokens before every model call. Code restores values in the answer. |
| Injection defence | SR-3 | Five switchable or fixed layers: structural wrapping, detector, capability control (money tools only propose; flagged documents force Tier 3), tool gating, output guard. |
| Audit log | SR-5 | Every agent, user and system action is an Ed25519-signed, hash-chained row. Anyone with the public key can verify an export (`pnpm audit:verify`, `/verify`). |
| Duplicate registry | SR-6 | Exact (file hash) and semantic (invoice fields) fingerprints across contexts and lenders. |
| Sandbox only | SR-8 | Every money action is labelled "Simulated". No payment rails exist in the code. |

Details: [`docs/submission/SECURITY_SELF_ASSESSMENT.md`](docs/submission/SECURITY_SELF_ASSESSMENT.md).

## Architecture

```mermaid
flowchart LR
  subgraph Browser["Browser (judge / SME / supplier)"]
    WEB["Next.js app<br/>apps/web<br/>EN / BN / ZH"]
    VER["/verify page<br/>Web Crypto, no upload"]
  end

  subgraph API["FastAPI service: services/agent"]
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

Stack: Next.js 16 (App Router, TypeScript, Tailwind v4) · FastAPI on Python 3.13 · LangGraph + LangChain ·
SQLAlchemy 2 + Alembic · PostgreSQL 16 + pgvector. Models: `claude-haiku-5-5` (router, agent, answers) and
`claude-sonnet-5-5` (document tasks), through Anthropic or OpenRouter. With no key the service runs an offline
deterministic mock model. Full description: [`docs/submission/TECHNICAL_DOCUMENTATION.md`](docs/submission/TECHNICAL_DOCUMENTATION.md).

## Measured results

Every number below is from the **dev split of synthetic data**. The test split has not been run (planned for
phase P24). These are ceilings on synthetic data, not real-world accuracy.

| Area | Result (dev split, synthetic) | Source |
|---|---|---|
| Document forensics | Precision and recall 1.00 on all 11 checks and all 10 fraud types (obvious and subtle); 0/50 clean packs flagged; 0/400 clean documents not PASSED. With WARN not counted, NAME_MATCH recall is 0.57. | `docs/forensics.md` (100 dev packs, 600 PDFs) |
| Duplicate-document registry | Byte-identical 3/3 EXACT; re-saved 2/2 NEAR; 5/5 caught | `python -m app.forensics.eval_registry` |
| Prompt injection | Attack success 100% with defences OFF, 0% ON (13 attacks); detection recall 100%; false positives 0/300 clean documents; money moved 0 in all modes | `services/agent/eval/results/injection_dev.json` |
| Privacy Gateway | Masking ON: detectable identifiers in payload 0; ground-truth bank identifiers leaked 1/600 (a seller company name equal to the account holder; company names are not masked by design). OFF: 600/600 leaked. | `python -m app.privacy.eval dev` |
| Demo numbers | Landed cost USD 11,200.00, margin 18.01%, shortfall USD 1,560.00 on 2026-11-07 | `docs/finance-formulas.md` |

Not measured yet: auto-vs-escalated action ratio, fraud results on the test split, real-model answer quality at scale.
The injection result uses an "obedient" mock model, so it does not show that layer 1 (delimiters) binds a real model.

## Run locally

### Option A: Docker (fallback, one command)

> This depends on files being added in P23 Part B (`docker-compose.env.example`, a `full` profile in
> `docker-compose.yml`, `services/agent/Dockerfile`, `apps/web/Dockerfile`). They were not present when this
> README was written. Check they exist before relying on this section.

```bash
docker compose --env-file docker-compose.env.example --profile full up --build
```

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
uv sync --directory services/agent
pnpm run db:up                  # Postgres 16 + pgvector on :5432, waits until healthy
pnpm run db:migrate             # create all tables
pnpm run db:seed                # load the simulated demo data
```
If port 5432 is already in use, set `POSTGRES_PORT` (and the port in `DATABASE_URL`) in `.env`.
With no `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`, the agent runs in offline mock mode (deterministic answers).
The RAG embedding model is downloaded once by `pnpm run kb:index` (about 240 MB).

#### Run the services
| Command | What it does |
|---|---|
| `pnpm run dev:agent` | FastAPI agent on http://localhost:8000 (`/health`, `/docs`) |
| `pnpm run dev:web` | Next.js web on http://localhost:3000 (proxies `/api/*` to the agent) |
| `pnpm run dev` | both together |
| `pnpm run db:down` | stop Postgres (data kept in the `setu-pgdata` volume) |
| `pnpm run db:migrate` | create/upgrade all tables (`alembic upgrade head`) |
| `pnpm run db:seed` / `db:reset-demo` | load the simulated demo data (idempotent) / wipe and reload it |
| `pnpm run kb:index` | embed the knowledge-base sources into pgvector |
| `./scripts/verify_seed` | assert the key demo numbers; see `data/demo/README.md` |
| `pnpm run lint` / `format` / `test` | ESLint + i18n check + tsc + Ruff / Prettier + Ruff format / pytest + Vitest |
| `pnpm run types` | regenerate `apps/web/src/lib/api/schema.gen.ts` from the running agent |

`npm run <script>` works too (pnpm must be installed). On macOS/Linux the `Makefile` wraps the same scripts:
`make up down dev test lint format types migrate seed reset-demo verify-seed demo-check`.

#### Try it
Open http://localhost:3000/demo for the guided 12-step walkthrough, or log in with "Login as"
(`/login`). The offline replay check runs without a network: `pnpm run demo:check`.
For the simulated SMS panel and the scam simulator, set `DEMO_MODE=true` (with `APP_ENV` = `dev`; see
`docs/demo.md`).

## Deployment

See [`docs/deploy-prod.md`](docs/deploy-prod.md) (written in P23 Part B; not verified here). Facts that exist in the repo:
- `vercel.json` defines two Vercel services: `web` (`apps/web`, Next.js) and `agent` (`services/agent`, FastAPI),
  with `/api/*` routed to the agent. It is in the working tree and not yet committed.
- Production database: PostgreSQL with pgvector (Neon was the plan); run `pnpm run db:migrate` against it.
- The agent refuses to start with `APP_ENV=prod` unless a 32+ character `DEMO_SESSION_SECRET`, a secure cookie
  and a non-wildcard `ALLOWED_ORIGINS` are set.
- Set `AUDIT_SIGNING_KEY` on the host to the key matching `docs/submission/audit-public-key.pem`.
- Never commit `.env*` files. Use `.env.example` for placeholders.
- A production smoke script is planned at `scripts/smoke_prod` (P23 Part B; not verified here).

## Tests and evaluation

| Command | What it runs |
|---|---|
| `make test` (= `pnpm run test`) | pytest (agent) + Vitest (web). DB tests need a local pgvector Postgres (see `.claude/rules/testing.md`) |
| `make lint` (= `pnpm run lint`) | ESLint, `i18n:check`, `tsc`, Ruff check and format check |
| `pnpm --dir apps/web i18n:check` | fails on missing Bangla keys (all areas) and missing Chinese keys (landing, accessibility, errors, supplier, common) |
| `pnpm --dir apps/web e2e` | Playwright end-to-end specs (needs a running stack and `E2E_BASE_URL`; use `E2E_RESET_DEMO=1` with a local `DATABASE_URL` to reset demo data) |
| `pnpm run demo:check` | replay the guided demo offline (27 scenes) |
| `uv run --directory services/agent python -m app.forensics.eval_dev` | forensics, dev split (needs `data/generated`) |
| `uv run --directory services/agent python -m app.forensics.eval_registry` | duplicate-hash catch rate, dev split |
| `uv run --directory services/agent python -m app.security.injection.suite dev` | injection attack success OFF vs ON, dev split |
| `uv run --directory services/agent python -m app.privacy.eval dev` | PII leakage ON vs OFF, dev split |
| `uv run --directory services/agent python -m synthetic.generator --clean 100 --tampered 100 --seed 42` | regenerate the synthetic trade-document set (git-ignored output) |
| `pnpm run audit:verify` / `audit:export` | verify the audit chain / export the operation log (see `docs/submission/EXECUTION_EVIDENCE.md`) |

`make eval` currently prints a notice only (`services/agent/eval/run.py` does not exist). Use the commands above.
Last recorded runs in `docs/PROGRESS.md`: pytest 1,240 passed (P20), Vitest 420 passed and Playwright `p22.spec.ts` 5/5 (P22).
Some earlier Playwright specs (`approvals`, `chat`, `deals`) failed in the P22 run and were not re-checked.

## Project structure

```
apps/web/                 Next.js app (src/app routes, src/components, src/i18n, e2e/)
services/agent/
  app/api/                FastAPI routers
  app/domain/             deterministic money logic (landed cost, financing, cash flow, FX, escrow, KYB)
  app/services/           orchestration, risk engine (services/risk), approvals, registry, credit record
  app/forensics/          PDF extraction, hidden-text detector, cross-checks, scoring, dev evaluation
  app/security/           tiers, policy, injection/ (layers 1-6), email guard
  app/privacy/            Privacy Gateway (detectors, vault, gateway, eval)
  app/audit/              signed hash-chained audit log (scheme, writer, verify, export)
  app/agent/              LangGraph nodes, tool registry and tools
  app/llm/                the only place models are called (+ replay fixtures)
  app/rag/                knowledge-base chunker, embeddings, hybrid retrieval
  app/demo/               guided demo runner and judge sandboxes
  app/db/, alembic/       SQLAlchemy models and migrations (single schema owner)
  config/risk.yaml        risk-tier thresholds
  kb/sources/             knowledge-base markdown (our own summaries)
  seed/, synthetic/       demo seed data, synthetic trade-document generator
  eval/results/           evaluation outputs
data/demo/                demo script, demo files, fixtures
docs/                     requirements, plan, progress, per-area references, submission/
infra/db/init.sql         enables the pgvector extension
scripts/                  run-local.sh, verify_seed, gen-types.sh
```

## Simulated data disclaimer

Setu is a competition prototype. Rahima, Karim, the suppliers, banks, lenders, FX rates, duty
rates, price bands and sanctions list are fictional or mock. Financing products are simulated. OTP codes are shown
in a simulated SMS panel. The Bangladesh Bank figures in the knowledge base are simplified summaries, not
independently verified, and are marked "verify with the official circular". Nothing here is financial advice.

## Limitations and known risks

The full list with sources is in `docs/submission/SECURITY_SELF_ASSESSMENT.md`. Main points:
no real authentication (demo login by role), no real payment or SMS provider, synthetic-only evaluation,
Bangla and Chinese text not reviewed by native speakers, `/app` Lighthouse mobile performance about 77 (target was 85),
no on-chain registry anchor, audit-table owner can truncate the table (use a non-owner DB role in production).

## Third-party licences

Licences below were read from package metadata in the local installs (`uv` virtualenv and `node_modules`) on the
build machine, except where marked.

**Web (`apps/web`)**
- Next.js 16.4.1, React 19.3.0, React DOM, Tailwind CSS 4.3.3, Recharts 3.10.1 (charts), `qrcode` 1.5.4 (receipt QR codes), `@noble/ed25519` 3.0.0 (browser verification fallback) — MIT
- TypeScript 5.9.3, Playwright 1.64.1 (dev), jsQR 1.4.0 (dev, QR tests) — Apache-2.0
- `@axe-core/playwright` 4.14.0 (dev only, accessibility tests) — MPL-2.0
- Vitest 5.0.5 (dev) — MIT
- Fonts [Inter](https://rsms.me/inter/), [Noto Sans Bengali](https://fonts.google.com/noto/specimen/Noto+Sans+Bengali), [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) — SIL Open Font License 1.1 (via `next/font/google`)
- Icons: self-made SVG paths in `src/components/ui/Icon.tsx`; favicon, OG image and landing mock screens drawn for Setu. `src/app/favicon.ico` is the Next.js scaffold default; its licence is **unverified** (replace before submission). See `apps/web/public/CREDITS.md`.
- The Colorlib "Pexcon" template was visual inspiration only; no code, CSS, text or images were copied.

**Agent (`services/agent`)**
- FastAPI 0.143.3, Alembic 1.20.0, SQLAlchemy 2.1.4, pydantic-settings 2.16.0, LangChain 1.4.6, LangChain-core 1.6.12, langchain-anthropic 1.7.6, LangGraph 1.2.15, langgraph-checkpoint 4.3.0, langgraph-checkpoint-postgres 3.2.0, LangSmith SDK 0.14.11, pgvector (Python) 0.5.1, pyotp 2.10.0, PyYAML 6.0.3, rapidfuzz 3.14.6 — MIT
- structlog 26.1.0 — MIT OR Apache-2.0
- cryptography 50.0.2 — Apache-2.0 OR BSD-3-Clause
- fastembed 0.9.0 — Apache-2.0
- pdfplumber 0.11.10 — MIT (classifier)
- ReportLab 5.0.1 — BSD-style (synthetic trade-document PDFs)
- Pillow 12.3.0 — MIT-CMU; NumPy 2.5.4 — BSD-3-Clause and others (synthetic fabric photos)
- psycopg 3.3.6 and psycopg-pool 3.3.3 — **LGPL-3.0** (used unmodified as a dependency)
- Embedding model: [`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) — Apache-2.0 (as stated on the model card; not re-checked in this build; downloaded once to `~/.cache/setu-fastembed`)
- Models called by API: Claude Haiku 5.5 and Sonnet 5.5 (Anthropic, direct or through OpenRouter). Used under the provider terms; nothing was trained or fine-tuned.

**Infrastructure:** PostgreSQL 16 and the `pgvector` extension (docker image `pgvector/pgvector:pg16`) — [TO FILL: confirm licence text for the final submission if required].

Project licence of Setu itself: [TO FILL: choose and add a LICENSE file; none exists in the repo].

## Team

- Team name: [TO FILL]
- Members and universities: [TO FILL]
- Contact: [TO FILL]
