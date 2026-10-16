#!/usr/bin/env bash
# Stop hook: non-blocking reminder when code changed but docs/PROGRESS.md did not.
# Compares the working tree (incl. untracked) against HEAD. No-op outside a git repo.
# See docs/claude-setup.md#hooks.
cat >/dev/null  # drain stdin
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

changed="$(git status --porcelain 2>/dev/null | awk '{print $NF}')"
[[ -z "$changed" ]] && exit 0
if grep -qx 'docs/PROGRESS.md' <<<"$changed"; then
  exit 0
fi
# Only remind when real code/config changed (not just scratch files)
if grep -Eq '^(apps/|services/|docs/|\.claude/|CLAUDE\.md)' <<<"$changed"; then
  echo '{"systemMessage": "Reminder: files changed but docs/PROGRESS.md was not updated. Run the phase-handoff skill before ending the phase."}'
fi
exit 0
