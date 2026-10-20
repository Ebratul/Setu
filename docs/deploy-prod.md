# Production deploy runbook (P23)

Two supported shapes: **A. Vercel Services + Neon** (web and agent behind one domain, `vercel.json` at the repo root) and
**B. one VPS** (`docker-compose.prod.yml`: Caddy with automatic HTTPS, web, agent; Neon for the database).
Everything money-related stays **simulated**. This file lists variable **names only**; set values in the Vercel dashboard, the VPS
`.env.prod` (git-ignored, `chmod 600`) or your password manager. Never commit or paste values.

> The brief mentions "Prisma migrations". This project uses SQLAlchemy models + **Alembic** (`backend/alembic`,
> `pnpm db:migrate`). Alembic is the single schema owner; there is no Prisma.

## 0. Pick the mode first

| | Judge / demo deployment (what we submit) | Locked-down deployment |
|---|---|---|
| `APP_ENV` | `dev` (the guided demo needs the simulated SMS inbox and scam simulator) | `prod` |
| `DEMO_MODE` | `true` | `false` (required by `APP_ENV=prod`; no OTP is ever shown) |
| `DEMO_REPLAY` | `true` (identical AI answers, works with no key) | `false` |
| Startup checks | CORS list is exact, cookie secret set (below) | the agent **refuses to start** unless `AUTH_MODE=neon`, `NEON_AUTH_BASE_URL` (https), `DEMO_SESSION_SECRET` >= 32 chars, `DEMO_COOKIE_SECURE=true`, `DEMO_MODE=false`, `DEMO_COOLING_OFF_SECONDS` >= 600, and `ALLOWED_ORIGINS` is an exact list (no `*`, not empty) |
| `Strict-Transport-Security` | not sent by the agent (Vercel / Caddy add it) | sent by the agent |

Even on the judge deployment keep `ALLOWED_ORIGINS` an exact list and `DEMO_COOKIE_SECURE=true` (the site is HTTPS).

## 1. Secrets and settings checklist (names only)

| Name | Where | Notes |
|---|---|---|
| `DATABASE_URL` | agent | Neon. **Direct** (non-pooled) host for the agent: judge sandboxes use a per-session `search_path`, which a transaction pooler breaks (the agent returns `SANDBOX_POOLER` for a `-pooler` host). Use the pooled URL only if sandboxes are switched off (`SANDBOXES_ENABLED=false`) |
| `ALLOWED_ORIGINS` | agent | exact origins, comma separated, e.g. the public https origin of the web app |
| `AUDIT_SIGNING_KEY` | agent | base64/hex 32-byte Ed25519 seed. Its public half must match the fingerprint of the committed `docs/submission/audit-public-key.pem` (check `GET /api/audit/public-key` -> `matches_committed_key: true`), or generate a new key and commit the new PEM (section 7) |
| `AUTH_MODE` | agent | `demo` (judge deployment) or `neon` (real accounts; mandatory with `APP_ENV=prod`). In `neon` mode `/auth/demo-*` do not exist and the API only accepts `Authorization: Bearer <Neon Auth JWT>` |
| `NEON_AUTH_BASE_URL` | agent, web | Neon Auth URL of the branch (`https://ep-….neonauth.<region>.aws.neon.tech/neondb/auth`). Public. The agent derives issuer, audience and JWKS from it |
| `NEON_AUTH_COOKIE_SECRET` | web | >= 32 random chars (`openssl rand -base64 32`); signs the session-cache cookie of the `/neon-auth/*` proxy. Secret |
| `DEMO_SESSION_SECRET` | agent | >= 32 random chars; signs the demo login and sandbox cookies and document links |
| `OTP_SECRET_SEED` | agent | random string; seeds the Tier 3 one-time codes |
| `DEMO_COOKIE_SECURE` | agent | `true` |
| `DEMO_MODE`, `DEMO_REPLAY` | agent | see section 0 |
| `DEMO_COOLING_OFF_SECONDS` (alias `COOLING_OFF_SECONDS`) | agent | `30` for the judge deployment, `600` (the real 10-minute rule) when `APP_ENV=prod` |
| `ANTHROPIC_API_KEY` | agent | optional with replay; needed for "Use live AI" and `pnpm demo:record`. Set a **spending cap** (section 6) |
| `MODEL_FAST`, `MODEL_SMART` | agent | default `claude-haiku-5-5`, `claude-sonnet-5-5` |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` | agent | optional tracing; PII is masked before it reaches the model |
| `CRON_SECRET` | agent | Bearer secret for `POST /demo/cleanup`; leave empty to disable the endpoint |
| `SANDBOX_TTL_HOURS`, `SANDBOX_MAX_ACTIVE`, `SANDBOX_CREATES_PER_HOUR_PER_IP`, `SANDBOX_LIVE_AI_BUDGET` | agent | sandbox capacity and the per-sandbox live-AI call cap (server-side) |
| `THREAD_TOKEN_BUDGET` | agent | per chat thread token budget, enforced server-side (default 60000) |
| `RATE_LIMIT_ENABLED`, `RATE_LIMIT_CHAT_PER_MINUTE` (20), `RATE_LIMIT_UPLOAD_PER_MINUTE` (10), `RATE_LIMIT_SANDBOX_CREATE_PER_MINUTE` (5), `RATE_LIMIT_GLOBAL_PER_MINUTE` (300) | agent | in-process sliding windows, **per process**: with `UVICORN_WORKERS=2` or several serverless instances the real ceiling is N x the number. `/health` is exempt |
| `TRUSTED_PROXIES` | agent | proxy IPs/CIDRs whose `X-Forwarded-For` is believed. Empty = the socket peer is the client. On the VPS, uvicorn already rewrites the client from Caddy (`FORWARDED_ALLOW_IPS`), so leave this empty |
| `MAX_BODY_BYTES` (1 MB), `DOCUMENT_MAX_BYTES` (4 MB) | agent | keep the upload limit <= 4 MB: Vercel functions reject bodies over 4.5 MB |
| `GIT_SHA`, `BUILD_TIME` | agent build | shown by `/health`; Vercel supplies `VERCEL_GIT_COMMIT_SHA`; Docker takes build args |
| `AGENT_URL`, `NEXT_PUBLIC_API_BASE` | web | `AGENT_URL` is the server-side `/api` proxy target (VPS: `http://agent:8000`, baked at web build time); `NEXT_PUBLIC_API_BASE=/api` |
| `SITE_ADDRESS`, `ACME_EMAIL` | VPS | Caddy hostname and the Let's Encrypt contact |
| `UVICORN_WORKERS`, `GRACEFUL_TIMEOUT`, `PORT` | VPS container | default 2 / 20 / 8000 |

Generate random values with `openssl rand -base64 48` (secrets) and `python -m app.audit.keygen` (signing key).

## 2. Database: Neon

1. Create a project (region close to the deployment) and a database. Keep two connection strings: **direct** and **pooled** (host
   contains `-pooler`).
2. Enable pgvector once, as the project owner, on the direct connection: `CREATE EXTENSION IF NOT EXISTS vector;`
   (`infra/db/init.sql` does this only for the local container).
3. From a trusted machine with the repo, export `DATABASE_URL` = the **direct** URL plus the production `AUDIT_SIGNING_KEY`,
   `DEMO_TODAY` (default `2026-10-20`) and `KB_EMBEDDER=fastembed`, then:

   ```
   pnpm db:migrate                                    # Alembic upgrade head
   uv run --directory backend python -m seed.cli seed        # idempotent demo data (first deploy)
   pnpm kb:sync && pnpm kb:index                      # knowledge base chunks + embeddings (model ~220 MB, downloads once)
   pnpm db:verify                                     # asserts the key demo numbers and idempotent re-seed
   pnpm demo:check                                    # runs the 12-step demo in replay in a throwaway sandbox; fails on any miss
   ```
4. **Audit re-sign.** Audit rows are signed with whichever key was configured when they were written. If you change
   `AUDIT_SIGNING_KEY` after seeding, old rows no longer verify. Re-seed under the new key on a demo-only database:
   `uv run --directory backend python -m seed.cli reset-demo --allow-remote` (wipes demo rows, writes a signed `DEMO_RESET`),
   then `pnpm audit:verify -- --file <export> --pubkey docs/submission/audit-public-key.pem` or open `/verify`.
5. After the first deploy, `scripts/smoke_prod` (section 8) must be green.

## 3. Deploy A: Vercel Services

`vercel.json` (repo root) defines two services: `web` (`frontend`, Next.js) and `agent` (`backend`, FastAPI, entrypoint
`app/main.py`); `/api/*` goes to the agent with the prefix stripped, everything else to the web app.

1. `vercel link` the repo, add the variables from section 1 for **Production** (and Preview if you test there) in the dashboard or with
   `vercel env add NAME production`. Agent variables go to the agent service, `NEXT_PUBLIC_API_BASE` to the web service.
2. Do section 2 first (the database must be migrated and seeded before traffic).
3. `vercel deploy --prod` (or push to the production branch). Confirm `https://<domain>/api/health` shows `"ready": true` and the
   expected `git_sha`.
4. Limits to remember: function request bodies <= 4.5 MB (uploads are capped at 4 MB), serverless instances keep their own rate-limit
   counters, and the Postgres connection count grows with instances (use Neon's connection limit as the ceiling; sandboxes need the
   direct URL).
5. Optional: schedule `POST /api/demo/cleanup` with `Authorization: Bearer $CRON_SECRET` (Vercel Cron) to drop expired sandboxes
   (cleanup also runs lazily on every sandbox creation).

## 4. Deploy B: one VPS (Docker + Caddy)

Needs a Linux host with Docker, ports 80/443 open, and a DNS record for the hostname.

```
git clone <repo> && cd Setu            # or rsync the tree; the web Dockerfile lives in frontend
cp <your values> .env.prod             # names in section 1; chmod 600; never commit
docker compose -f docker-compose.prod.yml --env-file .env.prod build \
  --build-arg GIT_SHA=$(git rev-parse --short=7 HEAD)
# one-time, from the same host (direct Neon URL in .env.prod's DATABASE_URL):
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm agent alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm agent python -m seed.cli seed
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm agent python -m app.rag.cli sync
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm agent python -m app.rag.cli index
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

The agent image already contains the embedding model (`KB_MODEL_CACHE_DIR`), so nothing is downloaded on first request. Caddy gets
and renews the certificate by itself (`restart: unless-stopped`, json logs rotate at 10 MB x 5). `BASE_URL=https://<host> scripts/smoke_prod`
verifies it. Update: `git pull`, rebuild, `up -d` (Caddy keeps serving while the agent restarts; stop grace period 30 s).

Local rehearsal of the whole stack with throwaway placeholders (not for production):
`docker compose --env-file docker-compose.env.example --profile full up --build` (web `:3000`, agent `:8000`).

## 5. Backups and restore

* **Neon (primary):** history retention gives point-in-time restore. Set retention to >= 7 days (Project -> Settings -> Storage). Restore
  by creating a **branch from a past timestamp** (Console -> Branches -> Create branch -> "Past data"), check it, then point
  `DATABASE_URL` at the branch (or promote it). Drill it once before the deadline.
* **Daily logical backup (fallback, off-Neon copy):** from any machine with `pg_dump` 16+ and the **direct** URL in `DATABASE_URL`:

  ```
  pg_dump --format=custom --no-owner --file "setu-$(date +%F).dump" "$DATABASE_URL"
  # cron example:  15 2 * * *  /usr/local/bin/setu-backup.sh   (keep 14 days, store off the VPS, encrypt at rest)
  ```
* **Restore** into an empty database (pgvector enabled first):

  ```
  psql "$RESTORE_URL" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
  pg_restore --no-owner --clean --if-exists --dbname "$RESTORE_URL" setu-YYYY-MM-DD.dump
  ```
  Then `pnpm db:migrate`, `GET /health` (`ready: true`) and `GET /audit/verify` (the chain must verify with the committed public key).
  The audit table rejects UPDATE/DELETE by trigger; restores recreate it whole, never row by row.
* Judge sandboxes are throw-away schemas (`sbx_*`); they are in dumps but safe to drop (`POST /demo/cleanup`).

## 6. Spending and abuse controls

* **Anthropic Console:** Settings -> Limits -> set a monthly **spend limit** (and a lower email alert threshold) on the workspace used by
  this key; use a dedicated workspace/key for the deployment. With `DEMO_REPLAY=true` and no key the site costs nothing.
* **Server-side caps already in code:** `SANDBOX_LIVE_AI_BUDGET` (live-AI calls per sandbox, then back to replay), `THREAD_TOKEN_BUDGET`
  (per chat thread), rate limits (section 1), 1 MB JSON / 4 MB upload body caps, `SANDBOX_MAX_ACTIVE`.
* Vercel: enable Spend Management and Attack Challenge Mode if the URL is public before judging.

## 7. Key rotation checklist

1. Anthropic / OpenRouter / LangSmith keys: create the new key, set it in the host, redeploy, confirm `/health` and one live-AI call,
   revoke the old key.
2. `DEMO_SESSION_SECRET`: rotating signs everyone out and invalidates sandbox cookies and document links (judges get a fresh sandbox).
3. `OTP_SECRET_SEED`: pending Tier 3 codes become invalid; cancel and recreate pending approvals.
4. `AUDIT_SIGNING_KEY`: **do not rotate casually.** Old rows verify only with the old public key. For a clean demo: new key ->
   `python -m app.audit.keygen` (writes the PEM) -> commit the new `docs/submission/audit-public-key.pem` (and the copy the web app
   bundles) -> `seed.cli reset-demo --allow-remote` -> `pnpm audit:verify`. Keep the old PEM next to the archive of any exported log.
5. Neon password: reset in the Console, update `DATABASE_URL` everywhere, redeploy, run `GET /health`.
6. `CRON_SECRET`: rotate in the host and in the scheduler together.
7. If a secret may have leaked: rotate it first, then check `git log -p` and the platform logs; `.env*` is git-ignored and blocked by hooks.

## 8. Verify after every deploy

```
BASE_URL=https://<domain> scripts/smoke_prod            # AGENT_URL=... if the API is on another origin
```
It checks `/health` ready, the landing page, judge sandbox + login, the full 12-step replay, the hidden-text attack is BLOCKED, the signed
audit export verifies, Privacy Gateway masking, sandbox reset, and prints per-step timings (non-zero exit on any failure). The browser
flavoured companion is `frontend/e2e`.

`GET /health` (public, no secrets, no LLM call) returns `status`, `service`, `db`, `version` plus `ready`, `kb_indexed`,
`audit_key_loaded`, `replay_fixtures_present`, `git_sha`, `built_at`, `demo_mode`, `demo_replay`. `status` stays `ok` while the
process is up; **`ready` is the deploy gate** (database, knowledge base, audit key and replay fixtures all present).

## 9. Uptime monitoring

* Add an HTTPS monitor (UptimeRobot, Better Stack or Vercel Checks) on `https://<domain>/api/health`, every 1-5 minutes, expecting HTTP 200
  and the keyword `"ready":true` (alert on keyword missing, not just on non-200: the endpoint answers 200 with `ready:false` when the
  database or knowledge base is gone).
* Second monitor on `https://<domain>/` for the web app. Alert by email plus one chat channel.
* The endpoint is rate-limit exempt and answers in milliseconds, so a 1-minute interval is fine.

## 10. Rollback

* **Vercel:** Deployments -> pick the last good one -> Promote to Production (instant, same env vars). Or `vercel rollback`.
* **VPS:** keep images tagged by `GIT_SHA` (compose tags `setu-agent:<sha>`); `GIT_SHA=<old> docker compose -f docker-compose.prod.yml up -d`
  or `git checkout <old>` and rebuild.
* **Database:** migrations are forward-only in practice; roll back app code first. If a migration must be undone, restore from Neon PITR
  to a branch taken just before the deploy (section 5) rather than running `alembic downgrade` on live data.
* After any rollback run `scripts/smoke_prod`.
