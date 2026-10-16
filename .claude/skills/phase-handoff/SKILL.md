---
name: phase-handoff
description: Closes a Setu phase — runs tests, checks acceptance criteria, updates docs/PROGRESS.md with a handoff note, and commits. Use at the end of every phase before /clear.
---

# Close a phase

1. **Identify the phase** id and its section in `docs/PLAN.md` (Grep `### Phase <id>` — read only that section).
2. **Run the phase's "Tests to run"** commands. Also run `make lint` if code changed. Capture only the summary lines.
   If anything fails: fix it, or mark it explicitly as a known issue — never claim green when it isn't.
3. **Check each acceptance criterion** one by one; note ✅/❌ with a few words of evidence.
4. **Security gate**: if the diff touches `app/security`, `app/tools`, `app/graph`, `app/llm`, `app/forensics`, escrow,
   approvals or audit, run the `security-reviewer` subagent on `git diff main...HEAD` and resolve critical/high findings.
5. **Update `docs/PROGRESS.md`**: append a row to the log table and a handoff block:
   ```
   | <id> | <YYYY-MM-DD HH:MM Dhaka> | done / partial / blocked | <what was done, ≤25 words> | <test summary line> | <handoff ≤25 words> |
   ```
   and under "Handoff notes" add `### <id>` with: new files/endpoints, env vars added, decisions made, known issues,
   what the next phase must read. Also tick the phase in the checklist at the top of PROGRESS.md.
6. **If `.env.example` needs new keys**, add placeholder lines (never real values).
7. **Commit**: `git add -A && git commit -m "<type>(<id>): <summary>"` on the phase branch; merge to `main` with
   `--no-ff` if acceptance criteria pass (ask the user first if any ❌ remain).
8. **Tell the user**: status, test line, and the ready-to-paste prompt of the next phase from `docs/PLAN.md`;
   remind them to `/clear` before starting it.
