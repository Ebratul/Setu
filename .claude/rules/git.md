# Git rules

- Default branch `main`. One branch per phase: `phase/<id>-<slug>` (e.g. `phase/2.1-landed-cost`). Parallel sessions use
  git worktrees (`claude --worktree` or `git worktree add ../setu-<id> phase/<id>-<slug>`).
- Commit after each completed task step inside a phase; final phase commit after `phase-handoff`.
- Conventional commits with the phase id: `feat(2.1): landed cost engine`, `test(5.1): tier boundary cases`,
  `docs(9.2): architecture section`, `chore(0.1): scaffold`. Allowed types: feat, fix, test, docs, chore, refactor, perf.
- Merge to `main` with `git merge --no-ff` when the phase's acceptance criteria pass; resolve `docs/PROGRESS.md`
  conflicts by keeping both entries in date order.
- Never commit: `.env*` (except `.env.example`), `keys/`, `synth/out/`, `eval/data/`, `node_modules/`, `.venv/`, `.next/`.
- Never force-push `main`; never rewrite history of merged branches. Push only when the user asks.
- `gh` CLI is not installed; create PRs (if any) from the GitHub web UI.
