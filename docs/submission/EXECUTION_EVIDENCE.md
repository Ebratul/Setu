# Setu — Execution Evidence (v1)

This document explains how a judge can check that Setu's operation log is genuine and untampered.
**All operations in the log are simulated sandbox actions.** The log records what the code did, including
simulated escrow funding and releases.

## 1. What the log is

Every agent, user and system action is one row in `audit_log`: tool calls by the AI agent, KYB runs, document
checks, registry hits, risk decisions, approvals (created, approved, rejected, expired, locked, executed), OTP
events, escrow funding and release, FX lock, beneficiary changes, blocked e-mails, injection detections, demo
resets. Rows are signed with Ed25519 and chained by hash (scheme `setu-audit-v2`, `docs/audit.md`).

```
payload_hash = sha256(canonical_json(body))
entry_hash   = sha256(prev_hash | payload_hash | seq | ts)
signature    = Ed25519(private_key, entry_hash bytes)        # first prev_hash = 64 zeros
```

Anyone holding only the public key can detect an edited, removed, reordered or forged entry.
Payloads are PII-redacted before signing (amounts are kept).

## 2. Public key

- File: `docs/submission/audit-public-key.pem` (also served at `GET /api/audit/public-key` and bundled in the web app).
- Fingerprint (sha256 of the 32 raw public-key bytes, hex), computed from the committed PEM when this file was written:
  `8030dcc6c48c93f3b2d1b19c3ee22f7b4694a6e4bb474ccd6a4c29ceb5b4d074`
- `PROGRESS.md` records that this key came from a local development key. **The production host must use the matching
  `AUDIT_SIGNING_KEY`, or the new public key must be committed.** [TO FILL: confirm the production key matches this
  fingerprint, or replace this section with the new fingerprint.]

## 3. How to verify

### 3.1 Command line (the committed export)

```bash
pnpm audit:verify --file docs/submission/execution-evidence/operation-log-<date>.jsonl \
                     --pubkey docs/submission/audit-public-key.pem
```

(Equivalent: `uv run --directory services/agent python -m app.audit.verify --file F --pubkey PEM`.)
Output is `OK: N entries verified ...` or `BROKEN at seq N: <reason>: <detail>` with exit code 1.
Reasons: `hash_mismatch`, `bad_signature`, `missing_seq`, `reordered`, `broken_link`, `malformed`.
Without `--file` the command verifies the database (needs `DATABASE_URL`); `--from` and `--to` select a range.

### 3.2 Browser (no login, nothing uploaded)

Open `/verify` on the live site: [TO FILL: live URL]/verify. Drop the `.jsonl` file. The check runs in the browser
with Web Crypto (with an `@noble/ed25519` fallback). The page can also check a single receipt
(`/verify?seq=&hash=#e=<entry>`; the signed entry travels in the URL fragment and is not sent to a server).

### 3.3 Live API (admin or judge login)

`GET /api/audit/verify`, `GET /api/audit/summary` (live head: last seq and hash), `GET /api/audit/entries`.
`POST /api/audit/tamper-demo` edits, deletes and reorders an **in-memory copy** of entries and shows the verifier
failing. The real table is not changed. Judge-facing pages: `/demo/audit` and `/app/admin/audit`.

## 4. What the export contains

`pnpm audit:export` (or `GET /api/audit/export?format=jsonl`):

- Line 1, a header: `scheme`, `genesis`, `public_key_fingerprint`, `generated_at`, `entry_count`, `first_seq`,
  `last_seq`, `contiguous`, `how_to_verify`.
- Then one entry per line: `seq`, `ts` (UTC), `actor_type`, `actor_id`, `deal_id`, `action`, `tier`, `decision`,
  `payload`, `payload_hash`, `prev_hash`, `entry_hash`, `signature`, `key_id`.
- The CLI also writes a readable `.md` next to it (per deal: actions, tiers, decisions, timestamps) and verifies the file.

**Limits to state honestly.**
- A truncated tail (newest entries cut off) still verifies as a shorter valid chain. Compare `last_seq` and
  `entry_hash` with the live head at `/api/audit/summary` or with a receipt.
- A deal-filtered export has gaps by construction (`contiguous: false`); each entry is checked on its own and against
  its direct neighbours. A partial export cannot prove completeness.
- The table owner could truncate the table or disable the trigger. Production should use a non-owner database role.
- Demo sandboxes (one schema per judge) have their own chains signed with the same key (known risk R12).

## 5. Existing evidence in the repository

| Item | Status |
|---|---|
| `docs/submission/audit-public-key.pem` | present |
| `docs/submission/execution-evidence/` | **not present** when this file was written (the directory is created by `pnpm audit:export`) |
| `apps/web/e2e/fixtures/audit/` | test fixtures signed with a **test** key, for the verifier tests only. Not production evidence. |
| `PROGRESS.md` (P20) | records the CLI verifying a 493-entry export against the committed public key on the development machine; that export is not committed |

## 6. Production demo run export (to be generated after deploy)

> **Not generated yet. Do not fabricate.** This must be produced by the user or the lead after the production
> deployment, from a real run of the guided demo on production.

Steps:
1. Deploy and confirm `AUDIT_SIGNING_KEY` matches `docs/submission/audit-public-key.pem` (or commit the new PEM).
2. Reset the demo data on the target database, run the guided demo (`/demo`, all 12 steps) or `pnpm demo:run`.
3. `pnpm audit:export` (against the production `DATABASE_URL`, with the keys in place). It writes
   `docs/submission/execution-evidence/operation-log-<date>.jsonl` and `.md`, then verifies the file.
4. Run `pnpm audit:verify --file <that file> --pubkey docs/submission/audit-public-key.pem` and keep the output.
5. Note the live head from `/api/audit/summary` at export time so tail truncation can be ruled out.

Production run export file: [TO FILL: file name, entry count, last seq, head hash, export date]
Verifier output: [TO FILL: paste the `OK: N entries verified` line]

## 7. Demo video

Link: [TO FILL: video URL]. Length limit 5 minutes. It is recorded from `/demo/run?mode=record` (recording mode).
The video shows simulated transactions only. [TO FILL: confirm the recording matches the final production build.]

## 8. Related references

`docs/audit.md` (scheme, keys, export format) · `docs/submission/SECURITY_SELF_ASSESSMENT.md` ·
`docs/demo.md` (guided demo) · `README.md` (commands).
