#!/usr/bin/env bash
# Stage a Vercel bundle: the agent service root is backend/, so rag_agent/, data/demo and the audit
# public key are copied inside it. Usage: scripts/deploy_vercel.sh [STAGE_DIR] [vercel args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="${1:-$(mktemp -d)}"; shift || true
rm -rf "$STAGE"; mkdir -p "$STAGE"
EXC=(--exclude .venv --exclude node_modules --exclude .next --exclude __pycache__ --exclude .git \
     --exclude .pytest_cache --exclude .hypothesis --exclude .ruff_cache --exclude '.env*' --exclude keys --exclude tests --exclude 'storage/*' \
     --exclude /document_for_test --exclude /.claude --exclude /prompt.txt --exclude '/setu-*.md')
rsync -a "${EXC[@]}" --exclude backend --exclude rag_agent --exclude data --exclude docs "$ROOT/" "$STAGE/"
rsync -a "${EXC[@]}" "$ROOT/backend/" "$STAGE/backend/"
rsync -a "${EXC[@]}" "$ROOT/rag_agent/" "$STAGE/backend/rag_agent/"
mkdir -p "$STAGE/backend/data" "$STAGE/backend/docs/submission"
rsync -a "$ROOT/data/demo/" "$STAGE/backend/data/demo/"
cp "$ROOT/docs/submission/audit-public-key.pem" "$STAGE/backend/docs/submission/"
mkdir -p "$STAGE/.vercel" && cp "$ROOT/.vercel/project.json" "$STAGE/.vercel/"
cd "$STAGE" && vercel deploy --prod --yes "$@"
