# Setu — Submission Checklist (v1)

Deadline: **20 Oct 2026 23:59 Beijing = 21:59 Dhaka.** Internal target: send v1 early, then send a later version
if needed (the email says so). Status values: **done**, **draft** (exists, needs review or later phase), **TODO-user**
(only the team can do it), **blocked** (waits on another task).

Topic chosen: **E** (AI SME finance copilot).

| # | Item | Status | File or link | Notes |
|---|---|---|---|---|
| 1 | Registration form (International Track) | TODO-user: confirm already sent | [TO FILL: date sent, confirmation] | Status unknown to the authors of this file |
| 2 | Passport bio pages for all members | TODO-user: confirm already sent | [TO FILL] | Status unknown |
| 3 | Team list (name, members, universities, contact) | TODO-user | [TO FILL] | Needed in README, email and deck |
| 4 | Topic selection: E | done | stated in README, technical doc, email | |
| 5 | Technical documentation | draft | `docs/submission/TECHNICAL_DOCUMENTATION.md`, `docs/submission/TECHNICAL_DOCUMENTATION.pdf` | v1; numbers are dev-split, synthetic. Update after P24 test-split run. PDF is English only. Mermaid diagram appears as source text in the PDF (no image) |
| 6 | Presentation deck, 10 minutes | draft (outline only) | `docs/submission/DECK_OUTLINE.md` | Full deck is phase P28. Needs screenshots and the architecture image |
| 7 | Demo video, 5 minutes max | TODO-user | [TO FILL: video URL] | Record from `/demo/run?mode=record` on the final production build; upload and add the link here, in the README and in the email |
| 8 | Source code | draft | [TO FILL: repository URL] | Current branch `phase/p23-deploy`; the P23 changes are uncommitted. Confirm repo access for the organisers (public or invited). Make sure no `.env*` or `keys/` are committed |
| 9 | README with local run, deployment, tests | draft | `README.md` | v1. Depends on P23 Part B files (see 10) |
| 10 | Deployment instructions and Docker fallback | blocked on P23 Part B | `docs/deploy-prod.md`, `docker-compose.env.example`, `docker-compose.yml` (`full` profile), `services/agent/Dockerfile`, `apps/web/Dockerfile`, `scripts/smoke_prod` | None of these existed when README v1 was written; verify each after the other agents finish |
| 11 | Test cases | draft | `services/agent/tests/`, `apps/web/src/**/*.test.*`, `apps/web/e2e/` | Last recorded: pytest 1,240 passed (P20), Vitest 420 passed (P22). PLAN also lists `docs/submission/test-cases.md` (catalogue with counts): not written. Re-run the full suites and record the counts |
| 12 | Security self-assessment report | draft | `docs/submission/SECURITY_SELF_ASSESSMENT.md` | v1; known-risk list from PROGRESS.md |
| 13 | Execution evidence: operation-log export | TODO-user (after deploy) | `docs/submission/execution-evidence/operation-log-<date>.jsonl` and `.md` | Generate with `pnpm audit:export` after the production demo run. Do not fabricate |
| 14 | Execution evidence: how to verify | draft | `docs/submission/EXECUTION_EVIDENCE.md`, `docs/submission/audit-public-key.pem` | Confirm the production signing key matches the committed PEM |
| 15 | Live demo URL | TODO-user (after deploy) | [TO FILL: live URL] | Check `/demo` pre-flight is green on production |
| 16 | `/judges` page | blocked on P23 Part B | [TO FILL: live URL]/judges | Web agent is adding it |
| 17 | Status page / health URL | TODO-user | [TO FILL: status URL] | |
| 18 | Email to organiser | draft | `docs/submission/EMAIL_DRAFT.md` | To wangyr@pbcsf.tsinghua.edu.cn; fill all [TO FILL] first |
| 19 | Test-split evaluation (P24) | TODO (project) | planned | Not run. No test-split number may appear in any document until it is |
| 20 | Native-speaker review of Bangla and Chinese text | TODO-user | n/a | Not reviewed |
| 21 | Licences | draft | README "Third-party licences", `apps/web/public/CREDITS.md` | Add a project LICENSE file; replace `favicon.ico` (scaffold default, licence unverified) |
| 22 | Unverified landing-page figures | TODO (project) | `apps/web` landing "problem" band | Two figures are marked "[figure to verify]"; the ADB figure was cited from memory. Verify or remove before submission |
| 23 | Placeholders on the footer (GitHub link, accessibility contact) | TODO-user | landing footer | Fill in |

## Attachment list for the email (exact file names)

1. `TECHNICAL_DOCUMENTATION.pdf`
2. `DECK_OUTLINE.md` (replace with the full deck file from P28 when ready)
3. `SECURITY_SELF_ASSESSMENT.md`
4. `EXECUTION_EVIDENCE.md`
5. `audit-public-key.pem`
6. `operation-log-<date>.jsonl` (after the production run; not yet generated)
7. `README.md`

Links in the email body: live demo, `/judges`, repository, video. Large files should be linked, not attached.

## Final pre-send check

- [ ] Every [TO FILL] in README, docs/submission/*.md and the email is resolved or intentionally left
- [ ] All metrics quote their split (dev, synthetic); no test-split number
- [ ] "Simulated sandbox" and "no model trained" appear in README, technical doc, video and deck
- [ ] `pnpm run lint` and `pnpm run test` pass on the final commit; counts recorded
- [ ] Live URL opens in a private window; `/demo` pre-flight green; `/verify` loads without login
- [ ] `pnpm audit:verify` passes on the committed export
- [ ] No `.env*`, `keys/`, `data/generated/` committed
