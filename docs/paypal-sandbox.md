# PayPal Sandbox checkout (simulated)

PayPal **Sandbox** only. No real money moves, and nothing here is a real escrow or a real payment
system: the escrow, the double-entry ledger and the "partner" stay the existing *simulated* ones.
The Sandbox payment is a separate record that a buyer can then choose to use to fund that
simulated escrow.

## Flow

```
buyer ──POST /payments/paypal/orders {deal_id, coverage}──▶ server derives amount ──▶ PayPal create order
buyer approves in the PayPal popup (JS SDK)
buyer ──POST /payments/paypal/orders/{id}/capture──▶ server re-reads the order, checks amount, captures
        status CAPTURED. Escrow and ledger are untouched.
buyer ──POST /payments/paypal/{id}/fund-escrow──▶ escrow.fund_escrow (role check, risk gate, ledger, audit)
        200 FUNDED · 202 PENDING_APPROVAL (nothing moved) · 409 RISK_BLOCKED / other refusal
PayPal ──POST /payments/paypal/webhook (signed)──▶ may move a payment's own status only
```

- **Amount** is the next unpaid tranche (`NEXT_TRANCHE`) or the remaining goods value (`REMAINING`),
  computed on the server from the deal, its milestones and escrow. Captured-but-undeposited payments
  count as covered, so a tranche is not paid twice.
- **Currency.** PayPal is charged in **USD**. A BDT/CNY deal is converted with the recorded FX table
  (rate stored on the payment). The escrow is funded with the deal-currency `amount`, not the USD
  charge.
- **Ownership.** The creator of the payment (or an admin) acts on it; every other caller gets 404.
  Judges can read. The request body never carries an amount, user or status (`extra="forbid"`).
- **Idempotency.** `Idempotency-Key` on create (same key → same payment); an identical open order
  made in the last 30 minutes is reused; capture is idempotent and sends a `PayPal-Request-Id`;
  funding is guarded by a row lock and a link written in the funding transaction
  (`escrow.fund_escrow(on_funded=…)`), so one payment deposits once.
- **Risk gate.** Funding goes through the unchanged gate. A BLOCK (for example supplier KYB failed)
  leaves the payment CAPTURED and unlinked. If the gate asks for approval the approval is linked to
  the payment and a later execution is detected on the next read. Releases are untouched: a Tier 3
  release still waits for a human.
- **Webhooks** are verified with PayPal's `verify-webhook-signature` before the body is read,
  de-duplicated by event id (`sandbox_payment_events`), and never post to the ledger. A refund
  before funding voids the payment; after funding it only raises a `NEEDS_REVIEW` audit entry.
- **Audit.** `PAYMENT_ORDER_CREATED`, `PAYMENT_CAPTURED`, `PAYMENT_FAILED`, `PAYMENT_CANCELLED`,
  `PAYMENT_ESCROW_LINKED`, `PAYMENT_ESCROW_PENDING_APPROVAL`, … in the signed hash-chained log.

## Setup

1. developer.paypal.com → Apps & Credentials → **Sandbox** → create a REST app.
2. Put these in `backend/.env` (never commit): 

   | Variable | Meaning |
   |---|---|
   | `PAYPAL_SANDBOX_ENABLED` | `true` to turn the checkout on (default `false`) |
   | `PAYPAL_SANDBOX_CLIENT_ID` | Sandbox app client id (public, served to the browser) |
   | `PAYPAL_SANDBOX_CLIENT_SECRET` | Sandbox app secret (server only) |
   | `PAYPAL_SANDBOX_WEBHOOK_ID` | id of the webhook registered for `https://<api>/payments/paypal/webhook` |
   | `PAYPAL_SANDBOX_TIMEOUT_SECONDS` | optional, default 10 |

3. Register the webhook for `PAYMENT.CAPTURE.COMPLETED`, `.DENIED`, `.DECLINED`, `.REFUNDED`, `.REVERSED`.
4. Pay with a Sandbox *personal* account from the Sandbox dashboard.

The API host is the constant `https://api-m.sandbox.paypal.com` in
`backend/app/services/payments/paypal_sandbox.py`; there is no setting for it.

## Data

Migration `b2d6f9a3c1e7` adds `sandbox_payments` (CHECK `simulated`, unique order/capture ids,
unique `(created_by_user_id, idempotency_key)`) and `sandbox_payment_events` (unique
`provider_event_id`). It is chained after `a9c4e7b2d5f8` (approvals step-up).

## Tests

`uv run --directory backend pytest tests/payments -q` (needs a local Postgres via
`TEST_DATABASE_URL`; the PayPal side is an in-memory fake, the adapter is tested with
`httpx.MockTransport`).
