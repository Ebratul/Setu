#!/usr/bin/env bash
# PostToolUse formatter (Edit|Write|MultiEdit).
# Python under backend -> ruff format + ruff check --fix (via uv).
# TS/JS/CSS/MD/JSON under frontend -> prettier --write (+ eslint --fix for ts/tsx).
# Silently no-ops when tools are not installed yet (before Phase 0.1). Always exits 0.
# See docs/claude-setup.md#hooks.
input="$(cat)"
f="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty' <<<"$input")"
[[ -z "$f" || ! -f "$f" ]] && exit 0
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"

case "$f" in
  */backend/*.py|backend/*.py|*/rag_agent/*.py|rag_agent/*.py)
    agent="$root/backend"
    if [[ -f "$agent/pyproject.toml" ]] && command -v uv >/dev/null 2>&1; then
      (cd "$agent" && timeout 20 uv run --quiet ruff format "$f" >/dev/null 2>&1 \
        && timeout 20 uv run --quiet ruff check --fix --quiet "$f" >/dev/null 2>&1)
    fi
    ;;
  */frontend/*.ts|*/frontend/*.tsx|*/frontend/*.js|*/frontend/*.jsx|*/frontend/*.css|*/frontend/*.json|*/frontend/*.md)
    web="$root/frontend"
    if [[ -x "$web/node_modules/.bin/prettier" ]]; then
      (cd "$web" && timeout 20 ./node_modules/.bin/prettier --write --log-level silent "$f" >/dev/null 2>&1)
      case "$f" in
        *.ts|*.tsx)
          [[ -x "$web/node_modules/.bin/eslint" ]] && \
            (cd "$web" && timeout 30 ./node_modules/.bin/eslint --fix --quiet "$f" >/dev/null 2>&1)
          ;;
      esac
    fi
    ;;
esac
exit 0
