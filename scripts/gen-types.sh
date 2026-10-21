#!/usr/bin/env bash
# Regenerate frontend/src/lib/api/schema.gen.ts from the running agent's OpenAPI schema.
set -euo pipefail
url="${AGENT_URL:-http://localhost:8000}/openapi.json"
root="$(cd "$(dirname "$0")/.." && pwd)"
if ! curl -fsS --max-time 5 "$url" >/dev/null; then
  echo "gen-types: agent not reachable at $url — start it with 'pnpm run dev:agent'" >&2
  exit 1
fi
pnpm --dir "$root/frontend" exec openapi-typescript "$url" -o src/lib/api/schema.gen.ts
