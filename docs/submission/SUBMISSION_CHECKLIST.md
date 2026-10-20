# Setu — Submission Checklist (v2)

Deadline: **20 Oct 2026 23:59 Beijing = 21:59 Dhaka.** Send a complete v1 early; a later version may follow (the e-mail
says so). Topic: **E** (AI SME finance copilot).

Status values: **done** (exists and checked), **draft** (exists, needs review), **TODO-user** (only the team can do it),
**blocked** (waits on another item). "Checked" below means checked against the repository, not run again.

## A. The six required deliverables

Source of the list: `docs/REQUIREMENTS.md` "Deliverables".

| # | Deliverable | Status | File or link | What is still needed |
|---|---|---|---|---|
| 1 | Technical documentation (architecture, core algorithms, security design) | draft, v2 | `docs/submission/TECHNICAL_DOCUMENTATION.md` and `.pdf` | Section 8 now holds the test-split results. PDF rebuilt from v2 (see the note under table B if it was not). Mermaid appears as source text in the PDF |
| 2 | Presentation deck, 10 minutes | draft (outline only) | `docs/submission/DECK_OUTLINE.md` | **Build the slides** [TO FILL: deck file name]; add screenshots and a rendered architecture image |
| 3 | Demo video, 5 minutes max | TODO-user | script: `docs/submission/DEMO_VIDEO_SCRIPT.md`; video: [TO FILL: video URL] | Record from `/demo/run?mode=record` on the final build; check length under 5:00; add the link to README, deck and e-mail |
| 4 | Source code with README, deployment instructions, test cases | draft | repo: [TO FILL: repository URL]; `README.md`; `docs/deploy-prod.md`; `backend/tests/`, `frontend/src/**/*.test.*`, `frontend/e2e/` | Public or invited access for the organiser; commit the files listed under C; add a project LICENSE; record final test counts |
| 5 | Security self-assessment | draft, v2 | `docs/submission/SECURITY_SELF_ASSESSMENT.md` | Review once more; P24 auth and PayPal changes have no recorded `security-reviewer` result |
| 6 | Execution evidence: sandbox operation log and demo video | TODO-user | `docs/submission/EXECUTION_EVIDENCE.md`, `docs/submission/audit-public-key.pem`, `docs/submission/execution-evidence/operation-log-<date>.jsonl` + `.md` | **The export does not exist yet.** Run the commands in `EXECUTION_EVIDENCE.md` section 6 on a local database, or on production after deploy; verify; paste the result line. The video is deliverable 3 |

## B. Supporting items

| # | Item | Status | File or link | Notes |
|---|---|---|---|---|
| 7 | Registration form (International Track) | TODO-user | [TO FILL: date sent, confirmation] | Status unknown to the authors |
| 8 | Passport bio pages, all members | TODO-user | [TO FILL] | Status unknown |
| 9 | Team list (name, members, universities, contact) | TODO-user | [TO FILL] | Needed in README, deck, e-mail |
| 10 | Topic selection E | done | README, technical doc, e-mail | |
| 11 | Live demo URL, `/judges`, `/verify`, status URL | TODO-user | [TO FILL: live URL], [TO FILL: status URL] | Nothing is recorded as deployed (`docs/PROGRESS.md` P23). After deploy: `BASE_URL=... scripts/smoke_prod` (the P23 notes say it was never run twice); `/demo` pre-flight green |
| 12 | Test-split evaluation | done | `backend/eval/results/metrics.json`, `metrics.md`, `injection_test.json` | Generated 2026-10-20. Harness `backend/eval/run.py`. Cite as "synthetic, test split, a ceiling" |
| 13 | Final test counts | TODO | run `make test` against a **local** database | Last recorded: pytest 1,313 passed + 23 registry failures without a migrated DB, Vitest 433 passed (P23). Auth, onboarding and payments tests have no recorded full-suite run. Do not run DB tests against the hosted Neon URL |
| 14 | Native-speaker review of Bangla and Chinese text | TODO-user | n/a | Not reviewed |
| 15 | Licences | draft | README "Third-party licences", `frontend/public/CREDITS.md` | Add a project LICENSE; replace `favicon.ico` (scaffold default, licence unverified); confirm pgvector licence line |
| 16 | Landing-page placeholders | TODO-user | landing "problem" band, footer | Two figures show "[figure to verify]"; footer GitHub link and accessibility contact are placeholders |
| 17 | E-mail to organiser | draft | `docs/submission/EMAIL_DRAFT.md` | To wangyr@pbcsf.tsinghua.edu.cn. Wording changed from "dev split" to "test split" in this pass; re-read before sending |
| 18 | Production signing key matches committed PEM | TODO-user | `GET /api/audit/public-key` -> `matches_committed_key` | Fingerprint in `EXECUTION_EVIDENCE.md` |
| 19 | Rotate any secret ever pasted into chat or a log | TODO-user | n/a | Noted in `docs/PROGRESS.md` P23 |

## C. Files to commit before sharing the repo

At the time of writing these were uncommitted (from `git status`): `backend/eval/run.py`, `backend/eval/__init__.py`,
`backend/eval/results/metrics.json`, `backend/eval/results/metrics.md`, `backend/eval/results/injection_test.json`,
`backend/eval/results.json`, the edit to `backend/app/forensics/eval_dev.py`, the edit to `backend/pyproject.toml`, and
the updated files under `docs/submission/` and `README.md`. Do not commit `.env*` (except `.env.example`), `keys/`,
`data/generated/`. Confirm `docs/submission/audit-public-key.pem` is tracked.

## D. Attachments for the e-mail (exact file names)

1. `TECHNICAL_DOCUMENTATION.pdf`
2. The deck file [TO FILL: deck file name] (until built, `DECK_OUTLINE.md`)
3. `SECURITY_SELF_ASSESSMENT.md`
4. `EXECUTION_EVIDENCE.md`
5. `audit-public-key.pem`
6. `operation-log-<date>.jsonl` (not yet generated)
7. `README.md`

Links in the body: live demo, `/judges`, `/verify`, repository, video. Link large files rather than attaching them.

## E. Final pre-send check

- [ ] Every [TO FILL] in `README.md`, `docs/submission/*.md` and the e-mail is resolved or intentionally left
- [ ] Every metric says "synthetic" and, where it is measured, "test split"; no dev-split number is presented as the result
- [ ] "Simulated sandbox" and "no model trained" appear in README, technical doc, deck and video
- [ ] `make lint` and `make test` pass on the final commit (local database); counts recorded
- [ ] Live URL opens in a private window; `/demo` pre-flight green; `/verify` loads without login
- [ ] `pnpm audit:verify` passes on the committed export
- [ ] No `.env*`, `keys/`, `data/generated/` committed
- [ ] Video under 5:00; deck under 10 minutes when rehearsed
- [ ] E-mail sent before 21:59 Dhaka; keep the sent copy
