# Setu — Progress log

Updated at the end of every phase by the `phase-handoff` skill. Newest entries at the bottom.
Times are Dhaka (UTC+6). Deadline: 20 Oct 2026 21:59 Dhaka. Must-have cut line: 19 Oct 23:59.

## Phase checklist
- [x] 0.1 · [ ] 1.1 · [ ] 1.2 · [ ] 1.3
- [ ] 2.1 · [ ] 2.2 · [ ] 2.3 · [ ] 2.4 · [ ] 2.5 · [ ] 2.6
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

## Known issues / risks
- Compose requires `POSTGRES_USER/PASSWORD/DB` from root `.env` (fails fast with a message if missing). On the dev
  machine host port 5432 is taken by a native Postgres — verification ran with `POSTGRES_PORT=5435`.
- Production routing of `/api/*` → FastAPI (prefix stripping) is decided in Phase 8.1; locally the Next rewrite strips it.

## Metrics (filled by Phase 7.2)
| Metric | Before | After | n |
|---|---|---|---|
