#!/usr/bin/env bash
# Run Setu locally: local Postgres container + API (mock AI) on :8000 + web on :3000.
# Safe to run from any folder and to run twice (it stops old copies first).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_URL="${DATABASE_URL:-postgresql://setu:setu@localhost:5437/setu_dev}"

docker start setu-p17-test >/dev/null 2>&1 || true
fuser -k 8000/tcp 3000/tcp >/dev/null 2>&1 || true
sleep 1

cleanup() { kill "${API_PID:-}" "${WEB_PID:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd "$ROOT/services/agent" && DATABASE_URL="$DB_URL" AGENT_MOCK_MODE=true DEMO_MODE=true \
  COOLING_OFF_SECONDS=30 uv run fastapi run app/main.py --port 8000) &
API_PID=$!
(cd "$ROOT" && pnpm --dir apps/web dev) &
WEB_PID=$!

echo "Web: http://localhost:3000   API: http://localhost:8000/docs   (Ctrl+C to stop)"
wait
