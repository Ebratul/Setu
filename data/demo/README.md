# Setu demo data — Simulated data

> **All companies and people are fictional; all data is simulated.** No real company names, people, bank
> accounts or payment rails are used. Every account number starts with `SIM-`. All money movement is a
> simulated sandbox and the UI labels it "Simulated".

The seed lives in `services/agent/seed/` (Python owns the schema and the seed). One module per domain:
`parties` (parties, bank accounts, KYB), `users`, `deals` (deals, costs, milestones, escrow, ledger),
`cashflow`, `fx`, `financing`, `documents` (documents, findings, hash registry), `alerts_approvals`,
`audit` (audit log, credit records), `scores`, `chat`. `cli.py` is the only file that writes to the DB.

## Commands

| Command | What it does |
|---|---|
| `pnpm run db:migrate` (`make migrate`) | `alembic upgrade head` |
| `pnpm run db:seed` (`make seed`) | Idempotent upsert of all demo rows (stable uuid5 ids). `audit_log` and `approval_requests` are insert-only, so a re-seed never rewrites history or resets a decided approval |
| `pnpm run db:reset-demo` (`make reset-demo`) | Wipe demo rows (everything except `kb_chunks`, `llm_cache`), then seed. Used by the Reset demo button later. Refuses a non-local DB unless `--allow-remote` is passed |
| `./scripts/verify_seed` (`make verify-seed`) | Seeds twice, checks that nothing changed, asserts every number below, and prints a table. `--no-reseed` skips the double seed |

`npm run db:seed` etc. work too: they are plain `package.json` scripts.

## Anchor date rule

- One anchor: `DEMO_TODAY` from env, default **2026-10-20**. Every date is `DEMO_TODAY ± n days`; seed keys
  use offsets, never absolute dates. So the demo never goes stale, and with any anchor it reconciles to the
  same numbers (tested with 2026-10-20, 2026-12-31 and 2027-02-14).
- After changing `DEMO_TODAY`, `db:seed` stops and asks for `db:reset-demo` (the stored anchor is in
  `demo_state.anchor_date`).
- Random variation (sales, utilities, FX walk, scores) uses `random.Random("setu-seed-v1:<stream>")`, which
  is fixed per stream. Amounts are integer ticks turned into `Decimal`, never floats.

## Key demo numbers (DEMO_TODAY = 2026-10-20)

| Item | Value |
|---|---|
| Main deal | **SETU-2026-0001**: Rahima Knitwear ← Shaoxing Huaxin Textile Co., Ltd., FOB Ningbo → Chittagong |
| Goods | 8,000 m dyed cotton jersey, HS 6006.22, USD 1.20/m = **USD 9,600.00** |
| Deal costs | freight 600.00 (T+19) · insurance 50.00 (T+14) · duty 800.00 (T+45 = arrival + 5) · bank charges 150.00 (T+2) |
| Landed cost | 9,600 + 600 + 50 + 800 + 150 = **USD 11,200.00** |
| Milestones 30/60/10 | **2,880.00** production start (T, READY; PI + production photos) · **5,760.00** shipment (T+18 = 2026-11-07; B/L + packing list + commercial invoice) · **960.00** arrival (T+40; bill of entry) |
| Expected sale value | **USD 13,660.00** |
| Gross margin | (expected sale − landed cost) ÷ expected sale = (13,660 − 11,200) ÷ 13,660 = **18.01%** |
| Escrow | Funded tranche by tranche. M1 (2,880.00) deposited at T−2 → escrow FUNDED, balance 2,880.00 |
| Rahima opening cash | USD 6,000.00 at the start of DEMO_TODAY |
| Balance on M2 date | 6,000 + receipts 3,665.00 − payments 5,465.00 = **USD 4,200.00** |
| Shortfall | 5,760.00 − 4,200.00 = **USD 1,560.00** (critical SHORTFALL alert) |
| Karim opening cash | USD 18,500.00 (no shortfall) |
| FX today (mock) | USD/BDT 122.5900 · USD/CNY 7.0990 · CNY/BDT 17.2686 |
| Good CNY day | T+2 (2026-10-22): CNY/BDT 16.9682 vs 30-day mean 17.2865 (−1.84%, mock forecast) |
| Tier 2 pending | Release M1 of SETU-2026-0001. Reason `FX_RATE_LOCK`: USD 2,880.00 is paid into Huaxin's CNY account, so a USD/CNY lock is needed |
| Tier 3 pending | Beneficiary change to Huaxin's new Hong Kong account (requested by email; reasons BENEFICIARY_CHANGE, CHANGE_VIA_EMAIL, HOLDER_NAME_MISMATCH, NEW_ACCOUNT); OTP required, cooling-off 10 min |
| Duplicate financing | PI `HX-PI-2026-118` of SETU-2026-0001 already registered at **Lender A** (Meghna Commercial Bank, loan ref MCB-IMPLOAN-2026-0412). Any second financing of the same invoice is a duplicate hit |

**Projected-balance formula** (`seed/cashflow.py`): balance available on day D = opening cash +
Σ inflows − Σ outflows over projected items with DEMO_TODAY ≤ date < D. Shortfall(D) = max(0, payment due
on D − balance). No other item falls on the M2 date. The local-purchase outflow on T+10 (USD 1,295.00) is
computed so that the balance lands on exactly 4,200.00. The seed fails if that figure ever leaves the
USD 500 to 2,500 range.

Cash-flow outflows from deals: tranches not yet funded are due on their milestone date, and deal costs on
their due date. Only FUNDED, IN_PRODUCTION and SHIPPED deals count; drafts are excluded. Rows dated before
DEMO_TODAY are `is_projected=false`.

## Cast

| Role / login | Party | Notes |
|---|---|---|
| BUYER `rahima@demo.setu` (bn) | Rahima Knitwear, Narayanganj | 4 deals: SETU-2026-0001 FUNDED · SETU-2025-0011 and SETU-2025-0019 COMPLETED with Huaxin (on time, 0 disputes, signed credit records) · SETU-2026-0006 DRAFT with Brightline (USD 1,850.00) |
| BUYER `karim@demo.setu` (en) | Dhaka Stitch Works, Mirpur | SETU-2026-0004 SHIPPED, Brightline, USD 7,400.00 · SETU-2026-0005 IN_PRODUCTION, Huameng, USD 4,300.00 · SETU-2026-0002 DISPUTED, Brightline, quality dispute · SETU-2026-0003 CANCELLED, Huaxin |
| SUPPLIER `huaxin@demo.setu` (zh) | Shaoxing Huaxin Textile Co., Ltd. | KYB VERIFIED: corporate CNY account, holder identical, first seen 400 days ago. Pending HK account change (Tier 3) |
| — | Ningbo Brightline Accessories Co., Ltd. | KYB VERIFIED: corporate USD account |
| — | Guangzhou Huameng Trading Co., Ltd. | **KYB WARNING**: licence name matches, but the receiving account is PERSONAL, held by "Chen Wei", first seen 3 days ago (TC-01) |
| ADMIN `admin@demo.setu` | — | |
| JUDGE `judge@demo.setu` | — | read-only demo access |

No passwords are stored. Demo mode will use a server-side "login as" switch (added with auth).

Lenders: Meghna Commercial Bank ("Lender A"), Setu Partner Finance ("Lender B"), Silk Route Export Credit
Cover (insurer), Shitalakshya Capital Finance PLC (NBFI). All are fictional.

Financing catalogue (5 active; `eligibility` is the `{"all": [{fact, op, value}]}` rule tree):
supplier credit via Huaxin (60 d, 0%, +2% price, ≥ 1 completed deal with the supplier) · Meghna import loan
(11.5% p.a., 0.5% fee, 90 d, min USD 2,000) · Setu Partner escrow-backed order loan (9.0% p.a., USD 40 fee,
until M3, needs funded escrow) · export-credit-insured supplier terms (90 d, 1.2% flat, ≥ 2 completed deals) ·
Shitalakshya working-capital line (14% p.a., 30–120 d).

Supplier scorecards: 6 monthly rows per supplier (Huaxin 96–99, Brightline 84–91, Huameng 53–58).
Score formula is in `seed/scores.py`.

## Documents (`data/demo/SETU-2026-0001/`)

Expected file names. The synthetic-document phase writes the real files here:

| File | Milestone | Seeded as |
|---|---|---|
| `proforma_invoice.pdf` | M1 | UPLOADED, checks PASSED, registered at Lender A |
| `production_photo_1.jpg`, `production_photo_2.jpg` | M1 | UPLOADED, checks PASSED |
| `bill_of_lading_clean.pdf` | M2 | PLACEHOLDER (variant CLEAN), no hash yet |
| `bill_of_lading_forged.pdf` | M2 | PLACEHOLDER (variant FORGED), no hash yet |

If a file exists, its `sha256` is computed over its bytes. Until then it is
`sha256("setu-demo-placeholder:<key>:v1")`. The hash-registry row always uses the same value as the
document row, so re-seeding after the real files arrive keeps the two in sync.

## Audit log and signing key

The 35 seeded audit entries cover the completed and disputed deals, the main deal and the Huameng KYB check.
They form a valid hash chain: `entry_hash = sha256(canonical_json(entry) + prev_hash)`, with `ts` in UTC,
signed with Ed25519. Credit records for the two completed deals are signed with the same key.

Key source: `AUDIT_SIGNING_KEY` from env if set (32-byte seed, base64 or hex). Otherwise a **dev key is
generated on the first seed run** and stored only in `keys/audit_dev_ed25519.key` (mode 0600; `keys/` is
git-ignored). Delete the file and run `db:reset-demo` to rotate it.
