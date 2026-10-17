# Setu (সেতু) — AI SME Finance Copilot

FinTechathon 2026 (Topic E). Financing, cash-flow and order analysis for Bangladeshi SMEs importing from China,
with milestone escrow and risk-tiered human approval. **All money movement is a simulated sandbox.**

## Local setup

### Prerequisites
- Node.js LTS (≥ 22) with pnpm (`corepack enable` or `npm i -g pnpm`)
- Python 3.13 (uv installs it automatically if missing)
- [uv](https://docs.astral.sh/uv/) — macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Docker Desktop (or Docker Engine + Compose v2)

### First run
```bash
cp .env.example .env            # local placeholders; never commit .env
pnpm install                    # web deps (pnpm workspace)
uv sync --directory services/agent
pnpm run db:up                  # Postgres 16 + pgvector on :5432, waits until healthy
```
If port 5432 is already in use, set `POSTGRES_PORT` (and the port in `DATABASE_URL`) in `.env`.

### Run the services
| Command | What it does |
|---|---|
| `pnpm run dev:agent` | FastAPI agent on http://localhost:8000 (`/health`, `/docs`) |
| `pnpm run dev:web` | Next.js web on http://localhost:3000 (proxies `/api/*` to the agent) |
| `pnpm run dev` | both together |
| `pnpm run db:down` | stop Postgres (data kept in the `setu-pgdata` volume) |
| `pnpm run db:migrate` | create/upgrade all tables (`alembic upgrade head`) |
| `pnpm run db:seed` / `db:reset-demo` | load the simulated demo data (idempotent) / wipe and reload it |
| `./scripts/verify_seed` | assert the key demo numbers; see `data/demo/README.md` |
| `pnpm run lint` / `format` / `test` | ESLint + tsc + Ruff / Prettier + Ruff format / pytest + Vitest |
| `pnpm run types` | regenerate `apps/web/src/lib/api/schema.gen.ts` from the running agent |

`npm run <script>` works too (pnpm must be installed). On macOS/Linux the `Makefile` wraps the same scripts:
`make up down dev test lint format types migrate seed reset-demo verify-seed eval`.

## Layout
- `apps/web` — Next.js (App Router) + TypeScript + Tailwind v4
- `services/agent` — Python FastAPI service (uv)
- `infra/db/init.sql` — enables the `vector` extension on first DB start
- `docs/` — plan, requirements, progress log

## Third-party licences
- [Recharts](https://github.com/recharts/recharts) — MIT (charts in `apps/web`)
- [sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) — Apache-2.0 (local KB embeddings via [fastembed](https://github.com/qdrant/fastembed), Apache-2.0; downloaded once to `~/.cache/setu-fastembed`, override with `KB_MODEL_CACHE_DIR`)
- [Noto Sans Bengali](https://fonts.google.com/noto/specimen/Noto+Sans+Bengali) — SIL Open Font License 1.1 (via `next/font/google`)
- [Inter](https://rsms.me/inter/) — SIL Open Font License 1.1 (via `next/font/google`)
