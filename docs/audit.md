# Signed, hash-chained audit log (SR-5, scheme `setu-audit-v2`)

Every agent, user and system action is one row in `audit_log`. Rows are append-only, signed with
Ed25519 and chained by hash, so anyone holding only the **public key** can check that nothing was
changed, removed or reordered. All money in Setu is simulated; the log says so by construction
(`ESCROW_FUNDED … SIMULATED_OK`).

## Entry

Body (what is signed): `{seq, ts, actor_type, actor_id, deal_id, action, tier, decision, payload}`

| Field | Meaning |
|---|---|
| `seq` | 1, 2, 3 … strictly sequential |
| `ts` | UTC, fixed width: `2026-10-20T09:30:00.000000Z` |
| `actor_type` / `actor_id` | `user` (user id), `llm` (`agent`), `system` (`system`) |
| `deal_id` | UUID or `null` (derived from `payload.deal_id` when the call site omits it) |
| `action`, `tier`, `decision` | what happened, permission tier 0–3, outcome (`RELEASED`, `PENDING`, `BLOCKED` …) |
| `payload` | facts about the action, **PII-redacted before signing** (`[redacted:PHONE]` …). Amounts are kept |

Computed fields:

```
canonical_json = sorted keys, no whitespace, UTF-8 (not \u-escaped), Decimal as string, floats refused
payload_hash   = sha256(canonical_json(body))
entry_hash     = sha256(prev_hash + "|" + payload_hash + "|" + seq + "|" + ts)     # ASCII, hex digests
signature      = Ed25519_sign(private_key, bytes.fromhex(entry_hash))               # 64 bytes, hex
prev_hash      = entry_hash of seq-1;  seq 1 uses GENESIS = 64 × "0"
```

`app/audit/scheme.py` is the reference implementation; `apps/web/src/lib/audit/verify.ts` mirrors it
and is tested against fixtures produced by the Python code (`tests/audit/make_fixtures.py`).

## Keys

* Private key: `AUDIT_SIGNING_KEY` (32-byte seed, hex or base64) in the environment/secret store, or
  the git-ignored dev key file under `keys/`. It is never logged, returned or committed.
* `python -m app.audit.keygen` creates a dev key **only if none exists** (never overwrites) and writes
  `docs/submission/audit-public-key.pem` if that file is absent. It exits non-zero if the committed
  PEM does not match the key in use.
* Public key: `docs/submission/audit-public-key.pem` (committed), also `GET /api/audit/public-key`
  and bundled in the web app for `/verify`. Fingerprint = sha256 of the 32 raw public-key bytes (hex);
  `key_id` is its first 16 characters.
* Production: set `AUDIT_SIGNING_KEY` on the host to the key whose public half is committed. If the
  key is rotated, commit the new PEM and keep the old one next to it for older exports.

## Writing

`app.audit.write_audit(db, actor=, action=, tier=, params=, result=, deal_id=, actor_id=)` appends in
the caller's transaction (the caller commits) and returns the `seq`. A transaction-scoped Postgres
advisory lock serialises writers, so `seq` and `prev_hash` are strictly sequential; the second
writer waits for the first to commit. No signing key means no row (`ServiceUnavailable`): the log is
never unsigned. A database trigger rejects `UPDATE` and `DELETE` (TRUNCATE is allowed so the demo can
be reset; the reset is itself logged as `DEMO_RESET`). `actor_id` comes from the signed session
cookie via `AuditActorMiddleware`.

## What is logged

Chat tool calls (`TOOL:<name>`, actor `llm`, masked args, result status) · KYB runs · document
uploads, check results, instruction findings · registry hits · risk decisions with reason codes ·
approvals created/approved/rejected/cancelled/expired/locked/executed · OTP sent/failed/too-early ·
escrow fund/release/refund · FX lock · beneficiary change requested/changed/blocked · blocked
redirection emails · injection detections and resolutions · privacy leak alerts · demo reset.

## Verifying

```
python -m app.audit.verify --file operation-log.jsonl --pubkey docs/submission/audit-public-key.pem
python -m app.audit.verify [--from SEQ] [--to SEQ]          # the database
```

Output is `OK: N entries verified …` or `BROKEN at seq N: <reason>: <detail>` (exit 1). Reasons:
`hash_mismatch` (contents changed), `bad_signature` (wrong key or forged), `missing_seq` (entry
removed), `reordered`, `broken_link` (`prev_hash` does not match the previous entry), `malformed`.
The reported seq is the first seq that is not in its place. A range that does not start at 1 is
checked against the trusted entry just before it (`anchored: false` in the report).

* API: `GET /api/audit/verify?from=&to=` (admin/judge).
* Browser: `/verify` (no login) verifies a dropped JSONL with Web Crypto; nothing is uploaded.

**Limits.** A truncated tail (newest entries cut off) still verifies as a shorter valid chain; compare
`last_seq`/`entry_hash` with the live head (`/api/audit/summary`) or a receipt. A deal-filtered export
has gaps by construction (`contiguous: false` in the header): each entry is checked on its own and
against its direct neighbours only.

## Export (execution evidence)

`GET /api/audit/export?deal_id=&from=&to=&format=jsonl` → line 1 is the header
`{scheme, genesis, public_key_fingerprint, generated_at, entry_count, first_seq, last_seq, contiguous,
how_to_verify}`, then one entry per line with `payload_hash`, `prev_hash`, `entry_hash`, `signature`,
`key_id`. `pnpm audit:export` writes `docs/submission/execution-evidence/operation-log-<date>.jsonl`
and a readable `.md` (per deal: actions, tiers, decisions, timestamps) and verifies the file.

## Judge-facing

* `/app/admin/audit` and `/demo/audit`: live chain, entry drawer, evidence dashboard.
* Tamper demo (`POST /api/audit/tamper-demo`): edits/deletes/reorders an **in-memory copy** of a
  window of entries and verifies it. The real table is read on a read-only connection and never
  changed.
* Receipts: QR → `/verify?seq=&hash=#e=<entry>`; the signed entry travels in the URL fragment (never
  sent to a server) and is checked in the browser.
* Fixtures for the verifier tests: `apps/web/e2e/fixtures/audit/` (signed with a **test** key).

## Migration note

`c4f9e2a6d1b3` changes the scheme and empties `audit_log` (old rows cannot be re-signed in place).
Run `pnpm db:reset-demo` afterwards; rows elsewhere that cite an old `audit_seq` are then stale.
