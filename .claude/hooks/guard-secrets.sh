#!/usr/bin/env bash
# PreToolUse guard (Edit|Write|MultiEdit|NotebookEdit|Bash).
# Blocks (exit 2) writes to secret files and shell commands that would print secrets.
# See docs/claude-setup.md#hooks.
set -u
input="$(cat)"
tool="$(jq -r '.tool_name // empty' <<<"$input")"

block() {
  echo "BLOCKED by .claude/hooks/guard-secrets.sh: $1" >&2
  echo "Secrets live only in .env files you edit yourself. Use .env.example for placeholders." >&2
  exit 2
}

if [[ "$tool" == "Bash" ]]; then
  cmd="$(jq -r '.tool_input.command // empty' <<<"$input")"
  # Reading/printing env files (allow .env.example / .env.sample)
  if grep -Eq '(cat|less|more|head|tail|bat|grep|sed|awk|cp|mv|source|\.)[[:space:]][^|;&]*\.env([.][A-Za-z0-9_-]+)?([[:space:]]|$|[|;&])' <<<"$cmd" \
     && ! grep -Eq '\.env\.(example|sample)' <<<"$cmd"; then
    block "command reads a .env file"
  fi
  # Dumping the environment
  if grep -Eq '(^|[|;&[:space:]])(printenv|env|export -p|set)[[:space:]]*($|[|;&>])' <<<"$cmd"; then
    block "command dumps environment variables"
  fi
  # Echoing secret-looking variables
  if grep -Eiq '(echo|printf|print)[^|;&]*\$\{?[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD|PASSWD|DATABASE_URL|PRIVATE)[A-Z0-9_]*' <<<"$cmd"; then
    block "command prints a secret-looking variable"
  fi
  # Private keys
  if grep -Eq '(cat|less|head|tail)[[:space:]][^|;&]*(\.pem|\.key|id_ed25519|id_rsa|/keys/)' <<<"$cmd"; then
    block "command prints a private key file"
  fi
  exit 0
fi

path="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")"
[[ -z "$path" ]] && exit 0
base="$(basename "$path")"
case "$base" in
  .env.example|.env.sample) exit 0 ;;
  .env|.env.*|*.env) block "writing to $base" ;;
  *.pem|*.key|id_rsa*|id_ed25519*) block "writing to private key $base" ;;
esac
if [[ "$path" == */keys/* || "$path" == keys/* ]]; then
  block "writing inside a keys/ directory"
fi
exit 0
