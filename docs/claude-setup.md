# Claude Code setup for Setu

How this repo is set up so that many small Claude Code sessions build Setu without losing context or wasting tokens.

## 1. Where knowledge lives (memory layers)

| Layer | File(s) | Loaded | Holds | Changes |
|---|---|---|---|---|
| Project memory | `CLAUDE.md` | every session, always | one-liner, stack, repo map, commands, the non-negotiable rules, pointers | rarely |
| Rules | `.claude/rules/*.md` | automatically when a file matching the rule's `paths:` is read/edited (`git.md` always) | detailed conventions per concern | when a convention changes |
| Skills | `.claude/skills/*/SKILL.md` | only the description is listed; full body loads when invoked | repeatable procedures (add tool, add page, close phase, generate docs, run eval) | when the procedure changes |
| Subagents | `.claude/agents/*.md` | when delegated to; run in their own context | focused workers with tool limits | rarely |
| Plan | `docs/PLAN.md` | **only the current phase's section** (Grep `### Phase X.Y`) | phases, dependencies, schedule, mappings | when re-planning |
| Per-phase memory | `docs/PROGRESS.md` | every session start | what was done, test results, handoff notes | end of every phase |
| Requirements | `docs/REQUIREMENTS.md` | when a phase lists it | FR/SR/NFR IDs, fraud types, attack styles | rarely |

Rule of thumb: *long-term truths* → CLAUDE.md / rules; *how-to* → skills; *what happened* → PROGRESS.md.
Don't put per-phase notes in CLAUDE.md, and don't inline rule files into CLAUDE.md with `@` imports (that would load them every time).

## 2. Session routine (one phase = one fresh session)

1. Start a fresh session in the repo root (or a worktree for a parallel phase: `claude --worktree phase-<id>`).
2. Paste the phase's **Ready-to-paste session prompt** from `docs/PLAN.md`. It tells Claude to read
   `CLAUDE.md`, `docs/PROGRESS.md`, the `### Phase X.Y` section of PLAN.md, and the phase's "Read first" files — nothing else.
3. Claude creates the branch `phase/<id>-<slug>`, works through the tasks, delegating to subagents where the phase says so.
4. Finish with the `phase-handoff` skill: tests → acceptance check → security review if needed → PROGRESS.md → commit → merge.
5. `/clear` (or close the session) before the next phase. Never carry one phase's context into the next.

## 3. Keeping context small

- **`/clear`** between phases — always. Continuity comes from PROGRESS.md, not from chat history.
- **`/compact`** only mid-phase when the context is getting long but you are in the middle of a task you can't checkpoint
  (e.g. debugging a failing test chain). Give it a focus: `/compact keep: failing test names, files changed, next step`.
  If a phase needs more than one compaction it was too big — split it and note that in PROGRESS.md.
- **Delegate to subagents** when work is (a) self-contained, (b) produces lots of output you don't need verbatim
  (test runs, reviews, eval runs, doc writing), or (c) can run in parallel. The subagent returns a ≤15–40 line report;
  the main context stays small. Typical: `agent-engineer` builds a module while main session plans; `security-reviewer`
  after security diffs; `eval-runner` for metrics; `docs-writer` for Stage 9.
- **Large files stay out of context**: generated data (`backend/synth/out/`, `backend/eval/data/`),
  `schema.gen.ts`, lockfiles, PDFs, `.next/`, `node_modules/`. Inspect with `ls | head`, `wc -l`, `jq 'length'`,
  or summary CLIs (`python -m synth.cli summary`). Never `cat` a PDF or a big JSONL.

## 4. Token-saving rules

- Don't read whole directories; Grep for the symbol, then Read with `offset/limit` around the hit.
- Read only the PLAN.md section for your phase (`grep -n "### Phase 3.2" docs/PLAN.md` then Read that range).
- Keep tool output short: `pytest -q`, `--tb=short`, `| tail -20`, `pnpm test --reporter=dot`; avoid verbose flags.
- Batch independent reads/searches in one turn; run long commands (dev servers, eval) in the background.
- Don't re-run a passing check until code has changed.
- Prefer editing existing files to rewriting them; don't paste large code blocks back into chat.
- LLM-cost side (the app itself): Haiku by default, Sonnet only for forensics, cached by masked-input hash; real-model
  tests are opt-in (`-m llm`).

## 5. Hooks (`.claude/settings.json`)

JSON can't hold comments, so they are explained here. Scripts live in `.claude/hooks/`, need `jq`, and are fast (<1 s typical).

| Event / matcher | Script | What it does | Blocking? |
|---|---|---|---|
| `PreToolUse` · `Edit\|Write\|MultiEdit\|NotebookEdit\|Bash` | `guard-secrets.sh` | Blocks writes to `.env`, `.env.*` (except `.env.example`/`.env.sample`), `*.pem`, `*.key`, SSH keys, anything under `keys/`. Blocks Bash that reads `.env` files (`cat/grep/source …`), dumps the environment (`env`, `printenv`, `export -p`, bare `set`), echoes `$…KEY/SECRET/TOKEN/PASSWORD/DATABASE_URL…` variables, or prints private keys. | Yes — exit 2, reason shown to Claude |
| `PostToolUse` · `Edit\|Write\|MultiEdit` | `format.sh` | Python in `backend/` → `ruff format` + `ruff check --fix` via `uv run`; TS/TSX/JS/CSS/JSON/MD in `frontend/` → `prettier --write`, and `eslint --fix` for TS/TSX. No-ops until Phase 0.1 installs the tools. 20–30 s timeouts. | No — always exit 0 |
| `Stop` | `progress-reminder.sh` | If `git status` shows changes under `apps/`, `services/`, `docs/`, `.claude/` or `CLAUDE.md` but `docs/PROGRESS.md` is unchanged, shows a reminder to run `phase-handoff`. No-op outside a git repo. | No — `systemMessage` only |

Permissions in the same file also **deny** `Read`/`Edit` on `.env`, `.env.local`, `.env.production` (any depth) and `keys/**`,
and pre-allow common read-only/test commands (`git status/diff/log`, `make test/lint`, pytest, ruff, pnpm test/lint/typecheck).

Review or disable hooks with `/hooks`. If a hook misbehaves, run it by hand:
`echo '{"tool_name":"Write","tool_input":{"file_path":".env"}}' | .claude/hooks/guard-secrets.sh; echo $?` (expect 2).

## 6. Parallel work (solo, ≤2 sessions)

- Main session follows the critical path; a second session in a git worktree takes a phase marked ∥ in PLAN.md whose
  dependencies are merged. Never run two sessions on the same phase or on phases that edit the same files.
- Each worktree has its own branch; merge to `main` after `phase-handoff`; the next session pulls `main` first.
- Shared files that can conflict: `docs/PROGRESS.md` (append-only — keep both rows), `frontend/src/i18n/*.json`
  (append keys), `app/tools/registry.py`, Alembic migrations (only one phase at a time creates migrations — see PLAN.md).
