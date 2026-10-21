# Milestone escrow and deals (FR-5, Phase P13)

Simulated only: no payment rails. Every response says `simulated: true` and the UI labels it "Simulated".
Pure rules: `backend/app/domain/escrow.py`. Orchestration: `app/services/escrow.py` (money) and
`app/services/deals.py` (create, schedule, read models). API: `app/api/deals.py`. Schemas: `app/schemas/deals.py`.
Risk-engine plug point: `app/security/risk_hook.py`. Migration: `4822f40a71c9`.

## State machines (enforced in code; an illegal move raises `InvalidTransition`, HTTP 409 `INVALID_TRANSITION`)

Deal (`DealStatus`; PROPOSED, CONFIRMED, ARRIVED are new):

```
DRAFT -> PROPOSED -> CONFIRMED -> FUNDED -> IN_PRODUCTION -> SHIPPED -> ARRIVED -> COMPLETED
PROPOSED <-> (re-propose) PROPOSED, CONFIRMED -> PROPOSED (edit resets confirmations)
DISPUTED: from FUNDED, IN_PRODUCTION, SHIPPED, ARRIVED   (resumes to a later stage, COMPLETED or CANCELLED)
CANCELLED: from DRAFT, PROPOSED, CONFIRMED, FUNDED ... ARRIVED, DISPUTED
```

Milestone (`MilestoneStatus`; PROPOSED and PENDING_APPROVAL are new; the spec's LOCKED is the existing `PENDING`):

```
PROPOSED -> PENDING(locked) -> READY -> PENDING_APPROVAL -> RELEASED
                               READY / PENDING_APPROVAL / FROZEN -> REFUNDED
PENDING_APPROVAL -> READY (approval rejected / expired);  PENDING -> CANCELLED (never funded, deal refund)
```

Evidence (`EvidenceStatus`, new column `milestones.evidence_status`): `PENDING | VERIFIED | FLAGGED | REJECTED`.
Phase 14's document pipeline sets it through `escrow.set_evidence_status`. The dev/test endpoint
`POST /milestones/{id}/evidence` (404 unless `ENABLE_DEV_EVIDENCE=true`; never in `APP_ENV=prod`; `.env.example` sets it true for local dev, tests enable it explicitly) wraps it.

Escrow status (`EscrowStatus`, unchanged): DRAFT, FUNDED, TRANCHE_RELEASED, COMPLETED, FROZEN, REFUNDED.

## Flow

1. `POST /deals` - DRAFT deal + landed-cost lines (`deal_costs`), reference `SETU-<year>-NNNN` (max + 1 under an advisory
   lock). Runs KYB for the supplier on this deal (`services/kyb.verify`, which commits); the run id is stored in
   `deals.kyb_run_id`. If KYB cannot run (sanctions list missing) nothing is saved. Beneficiary = the supplier's newest
   ACTIVE account.
2. `POST /deals/{id}/milestones/propose` - template `30/60/10` or `custom` percents (2-5 tranches, each > 0, at most 2
   decimals, sum exactly 100). Amounts come from `split_by_ratios` (last tranche absorbs the remainder: 9,600.00 ->
   2,880.00 / 5,760.00 / 960.00). Tranche 1 = PRODUCTION_START (PROFORMA_INVOICE, PRODUCTION_PHOTO), last = ARRIVAL
   (BILL_OF_ENTRY), any in between = SHIPMENT (BILL_OF_LADING, PACKING_LIST, COMMERCIAL_INVOICE). Due dates: today + 7 / 35
   / 60 days for three tranches, otherwise evenly spread. Allowed in DRAFT/PROPOSED/CONFIRMED while nothing is in escrow;
   re-proposing updates rows in place (so documents and cash-flow mirror rows keep their ids), deletes extras and clears
   both confirmations. Refused when the supplier is KYB-BLOCKED. SR-1 lists schedule creation as Tier 2: this HTTP call
   is the human action (audited at tier 2) and both parties must still confirm.
3. `POST /deals/{id}/milestones/confirm` - BUYER and SUPPLIER each confirm once (idempotent; who and when stored in
   `milestone_confirmations`). Admin must pass `party_role`. When both exist the deal becomes CONFIRMED and tranches
   PROPOSED -> PENDING.
4. `POST /deals/{id}/escrow/fund` - buyer or admin. **Decision on `amount`:** any positive amount with at most 2 decimals,
   up to the goods value not yet deposited. Omitted = the next tranche that is not covered yet. So the buyer can deposit
   tranche by tranche (what the seed does: SETU-2026-0001 holds only M1) or the whole goods value at once. A tranche
   turns READY when cumulative deposits cover it and every earlier tranche is settled (`rules.ready_seq`). First deposit:
   deal CONFIRMED -> FUNDED, ledger `FUND`, buyer cash balance reduced (refused with `INSUFFICIENT_CASH`).
   `escrow_accounts.advance_over_20k` is set when total deposited (in USD) is strictly greater than 20,000
   (`security/policy.py::TIER1_MAX_USD`); 5.1 makes it a Tier 3 trigger. Alerts for the buyer are recomputed.
5. `POST /milestones/{id}/release` (see below).
6. `POST /milestones/{id}/refund` and `POST /deals/{id}/refund` - admin only. Milestone refund: a funded, unreleased
   tranche goes back to the buyer (ledger `REFUND`), the deal becomes DISPUTED and the other open tranches FROZEN. Deal
   refund: the whole balance returns, funded unsettled tranches become REFUNDED, unfunded ones CANCELLED, the deal
   CANCELLED. The buyer's cash is credited. `dispute_reason` and `dispute_count` are updated.

### Deal status advance on release

First tranche (PRODUCTION_START) -> IN_PRODUCTION; SHIPMENT -> SHIPPED; ARRIVAL -> ARRIVED; when no tranche is left
unsettled the deal also walks ARRIVED -> COMPLETED in the same transaction (`completed_on` set, escrow COMPLETED). A deal
never moves backwards and a DISPUTED deal is left alone (`rules.release_path`). Each hop is validated against the table.
Credit-record issuance on COMPLETED (FR-8) is not part of this phase.

## Release: check order and idempotency (`escrow.release_tranche`)

Locks: `SELECT ... FOR UPDATE` on the deal row, then its milestones and escrow row, re-read with `populate_existing`.
Two requests for one deal run one after the other. Authorization (buyer of the deal, or admin) happens first, again inside
the service; suppliers and judges get 403, foreign deals 404.

0. Idempotency: if the milestone is RELEASED and `release_idempotency_key` equals the request key, return the original
   result (`idempotent_replay: true`, same ledger rows). A different key -> 409 `MILESTONE_ALREADY_RELEASED`.
   A milestone already PENDING_APPROVAL returns the open approval (202) instead of creating another.
1. (a) milestone READY (`MILESTONE_NOT_READY`), deal in FUNDED..ARRIVED (`DEAL_NOT_ACTIVE`), `evidence_status == VERIFIED`
   (`EVIDENCE_NOT_VERIFIED`).
2. (b) escrow balance >= tranche amount (`INSUFFICIENT_ESCROW`).
3. (c) beneficiary: `deals.beneficiary_account_id` belongs to the supplier (`BENEFICIARY_NOT_SUPPLIERS`), is ACTIVE
   (`BENEFICIARY_NOT_ACTIVE` for PENDING_CHANGE and RETIRED), the supplier is not KYB-BLOCKED (stored status and a live
   `kyb.evaluate`, `KYB_BLOCKED`), the account currency is supported. A WARNING supplier is passed to the hook, not refused.
   Then, unless the call carries a verified `approval_id`: escrow status FROZEN -> `ESCROW_FROZEN`; an open
   (PENDING or APPROVED-but-not-executed) Tier 3 approval on the deal or on any of the supplier's accounts, e.g. the
   seeded `CHANGE_BENEFICIARY` -> `TIER3_APPROVAL_PENDING`. Demo note: while that seeded Tier 3 is undecided, no Huaxin
   money moves; decide it first.
4. (d) `risk_hook.evaluate(RELEASE_TRANCHE, context)` (below). BLOCK -> 409 `RELEASE_BLOCKED`. Open approvals count as
   PENDING and APPROVED-unexecuted: without `approval_id` a release never posts past one, it returns the open approval.
5. (e) ALLOW: one transaction. Ledger `RELEASE` (two balanced rows in the deal currency; for a CNY account `fx_rate` (8 dp,
   latest HISTORY row) and `counter_amount`/`counter_currency` = round_half_up(amount x rate) are stored on the postings),
   escrow balance/released updated, milestone RELEASED (+ key, `released_at`), next tranche READY if covered, deal status
   advance, alerts recomputed, `TRANCHE_RELEASED` audit row (tier = hook tier). Invariant checked before commit.

Every refusal writes a `TRANCHE_RELEASE_REFUSED` audit row (result `REFUSED:<CODE>`) and returns problem JSON with a stable
`code`. A tranche never ALLOWs past a still-open human approval: the seeded Tier 2 approval for SETU-2026-0001 M1 keeps
that tranche at PENDING_APPROVAL until it is decided (use `escrow.release_approval_closed` after a rejection).

### The risk-hook contract for Phase 5.1 (`app/security/risk_hook.py`)

```python
evaluate(action: RiskAction, context: ReleaseContext) -> RiskResult   # RiskHook = Callable[[RiskAction, ReleaseContext], RiskResult]
RiskResult(decision: ALLOW | REQUIRE_APPROVAL | BLOCK, tier: 0..3, reasons: list[RiskReason(code, message)])
```

`ReleaseContext` (pydantic, frozen, `extra="forbid"`): deal/milestone ids and refs, `amount`, `currency`, `amount_usd`,
`settlement_currency`, `fx_rate`, `beneficiary_*` (status, verified, recently opened), `supplier_kyb_status`,
`supplier_deal_count` (earlier funded deals with this buyer), `evidence_status`, `escrow_balance`, `advance_over_20k`,
`requested_by_user_id/role`. 5.1 extends it with fraud score, duplicate-hash and document-instruction facts.

- Until 5.1, `default_evaluate` is an interim FAIL-CLOSED policy (`TODO(5.1)`), highest tier wins:
  Tier 3 when `amount_usd` > 20,000 (strict, on the UNROUNDED USD amount: 20,000.00 is Tier 1, 20,000.01 and
  20,000.0014 are Tier 3), `advance_over_20k`, or a receiving account opened < 30 days ago. Tier 2 when
  `supplier_deal_count == 0` (first deal) or the settlement currency differs from the deal currency (FX lock).
  Otherwise ALLOW tier 1 (auto + notice). So the seeded demo deal (Huaxin, CNY account, 2 completed deals) is Tier 2
  `FX_RATE_LOCK` for every tranche, which is exactly the seeded Tier 2 approval; the service reuses it instead of
  creating a second one. A USD account with a known supplier releases automatically at Tier 1. Replace the function (or call `set_hook`); tests inject
  fakes with `risk_hook.use_hook(...)` or `release_tranche(..., hook=fake)`.
- `normalise()` fails closed: ALLOW with tier >= 2 becomes REQUIRE_APPROVAL; REQUIRE_APPROVAL below tier 2 becomes tier 2.
- REQUIRE_APPROVAL creates an `ApprovalRequest` (action `RELEASE_MILESTONE`, params as in the seed:
  `deal_ref, milestone_seq, amount, currency, beneficiary_account_id, pay_currency`) with
  `params_hash = approval_binding_hash(action, tier, deal_id, milestone_id, bank_account_id, params)`, milestone ->
  PENDING_APPROVAL, audit `RELEASE_APPROVAL_REQUESTED`. Approval keys are unique per attempt (a request after a rejection
  never collides); an open approval of a lower tier is superseded (CANCELLED, audited `APPROVAL_SUPERSEDED`) by a stricter
  request; a refund cancels open release approvals (`APPROVAL_CANCELLED_BY_REFUND`). No ledger entry. Tier 3 also sets `otp_required`,
  `cooling_off_until = now + 10 min` and freezes the escrow (status FROZEN) until the approval is decided.
- Execution by Phase 5.5: after the human endpoint sets the approval to APPROVED (OTP and cooling-off checked there), call
  `release_tranche(db, milestone_id, user, key, approval_id=...)`. The service re-verifies: approval APPROVED and bound to
  this milestone/deal, stored params equal the params rebuilt from current state (`APPROVAL_PARAMS_CHANGED`), binding hash
  recomputed (`APPROVAL_HASH_MISMATCH`), the hook is re-run so the tier is recomputed (`APPROVAL_TIER_STALE` if it rose,
  `RELEASE_BLOCKED` on BLOCK), cooling-off over (`COOLING_OFF`). Then it posts and marks the approval EXECUTED. The
  `hook=` and `approval_id=` parameters are Python-level only; no HTTP endpoint exposes them.

## Locks, roles, audit

- Order: deal row, then milestones and escrow, then (fund, refund) the buyer's `parties` row `FOR UPDATE`, because the cash
  balance is shared by all of a buyer's deals (tests: concurrent funding of two deals, fund racing refund).
- 403s leave `<ACTION>_FORBIDDEN` audit rows (`FUND`, `RELEASE`, `REFUND`, `PROPOSE`, `CONFIRM`, `EVIDENCE`, `DEAL_CREATE`);
  a 404 (not your deal) leaves none. A READY -> PENDING_APPROVAL resync is audited (`RELEASE_PENDING_APPROVAL_RESYNC`).
- `GET /deals/{id}/activity` filters on `audit_log.deal_id`, which is **unsigned grouping metadata**: it is not part of
  the signed entry hash (putting it there would break verification of existing rows). The signed chain itself is
  verified by `/audit/verify` (5.4).
- Supplier projection (fields stay present, blank): `expected_sale_value` null, `costs` [], `dispute_reason` null,
  `kyb.score` null, `kyb.reason_codes` [], `approval.reasons` []; ledger `buyer:<code>:cash` shows as `buyer:cash` and
  refund memos hide the reason; activity keeps seq/ts/actor/action/tier and blanks `result`, `params_hash`,
  `entry_hash`, `key_id`.
- Goods value must be below 1,000,000,000,000 (400 `INVALID_AMOUNT`).

## Invariant

`funded_total = released_total + refunded_total + balance` (all >= 0). Enforced three ways: after every fund, release and
refund (`rules.check_invariant`, raises `InvariantViolation` -> 500, transaction rolled back), by a DB CHECK
(`ck_escrow_accounts_escrow_invariant`), and in tests, which also re-derive the totals from the debit side of the ledger
by kind. Every ledger `txn_ref` balances (debits = credits); the ledger endpoint reports `balanced`.

## Seed compatibility

The seed funds tranche by tranche and is unchanged in numbers (`./scripts/verify_seed`: 19/19). It now also writes
`kind`/`milestone_id` on ledger rows, `condition_text` and `evidence_status` on milestones (released and the main deal's M1
= VERIFIED, frozen = FLAGGED, else PENDING), `partner`/`refunded_total`/`advance_over_20k` on escrow, and both
confirmations for every deal past DRAFT. Cash flow already derives unfunded tranches from `escrow.funded_total`, so fund,
release and refund need no cash-flow row changes and nothing is double counted (`cashflow.ACTIVE` gained ARRIVED).
Re-seeding resets seeded deals; deals created through the API are untouched but a seeded deal that was released
through the API should be reset with `db:reset-demo`.

## Endpoints

| Method / path | Who | Notes |
|---|---|---|
| `POST /deals` | buyer, admin (names `buyer_id`) | 201 `DealDetail`; supplier and judge 403 |
| `GET /deals?status=` | buyer (own), supplier (own), admin, judge | `DealList` |
| `GET /deals/{id or reference}` | participants, admin, judge | `DealDetail`; foreign deal 404 |
| `POST /deals/{id}/milestones/propose` | buyer, admin | body `{template, percents?}` |
| `POST /deals/{id}/milestones/confirm` | buyer, supplier, admin (`party_role`) | idempotent |
| `POST /deals/{id}/escrow/fund` | buyer, admin | body `{amount?}`; supplier/judge 403 |
| `POST /milestones/{id}/release` | buyer, admin | body `{idempotency_key}`; 200 released or 202 pending approval |
| `POST /milestones/{id}/refund`, `POST /deals/{id}/refund` | admin | body `{reason}` |
| `GET /deals/{id}/ledger`, `GET /deals/{id}/activity` | participants, admin, judge | ledger rows with FX; signed audit rows |
| `POST /milestones/{id}/evidence` | buyer, admin, **dev/test only** | 404 unless `ENABLE_DEV_EVIDENCE=true` (default false) and `APP_ENV` is not `prod` |

Errors are RFC 7807 problem JSON plus a stable `code` (new optional field). Agent registry: `propose_milestones`
(max tier 2) and `release_tranche` (max tier 3) exist only so `guard()` returns `requires_approval_flow`; they are in no
intent allow-list, `llm_tools()` hides them and their bodies refuse too.
