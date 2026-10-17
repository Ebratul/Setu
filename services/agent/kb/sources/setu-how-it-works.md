---
id: setu-how-it-works
title: How Setu works
source_type: product_doc
original_reference: "Setu product documentation (internal); see docs/REQUIREMENTS.md, FR-5, SR-1 to SR-5"
language: en
last_reviewed: 2026-10-17
disclaimer: "Simplified summary for demo — verify with the official source. All money movement in this demo is simulated."
---
# How Setu works

Setu is an AI finance copilot for Bangladeshi small businesses that import from Chinese suppliers. It helps with financing, cash flow, order cost and supplier payment. All balances, payments and ledgers in this demo are simulated. No real bank is connected. No machine-learning model was trained for Setu.

## Milestone escrow

Escrow means money is held by a neutral party and released only when conditions are met. In Setu the escrow is simulated. A supplier payment is split into milestones. A common schedule is 30/60/10:

- 30% deposit when the order is confirmed,
- 60% pre-shipment, when shipping evidence is ready,
- 10% post-arrival, after goods arrive and are checked.

Each tranche is released only after the evidence checks pass, for example a matching bill of lading. The escrow moves through states such as draft, funded, tranche released and completed. It can also be frozen or refunded. While a Tier 3 approval is pending, the escrow is frozen.

## Permission tiers

Every money action is classified into a risk tier by code, not by the AI. The highest triggered tier wins.

| Tier | Name | What happens | Example triggers |
|---|---|---|---|
| 0 | Auto | Runs automatically | Read-only analysis, checks, calculations, knowledge search |
| 1 | Auto + notice | Runs and tells you | Release to a verified, unchanged beneficiary when all checks pass, amount at most USD 20,000, fraud score below 0.3 |
| 2 | One-tap approval | A human taps approve | First deal with a supplier, minor mismatch (fraud score 0.3 to 0.6), FX rate lock, milestone schedule creation or change |
| 3 | OTP + 10-minute cooling-off | A human enters an OTP and waits 10 minutes | Beneficiary or account change, fraud score 0.6 or higher, duplicate document hash, amount above USD 20,000, any instruction from document or email text, name mismatch on the receiving account |

During the cooling-off the user can cancel. The server rejects execution before the time has passed.

## What the assistant can and cannot do

The assistant can read data, calculate, search the knowledge base and explain results in plain language. It recommends. It cannot move money. Numbers such as cost, margin, gap, exchange rate, fraud score and tier come from deterministic code. The AI only explains them.

Tools that the AI can call are limited to Tier 0 and Tier 1. Tier 2 and Tier 3 actions create a pending approval that only a human can execute through a separate endpoint.

## Privacy Gateway

The Privacy Gateway masks sensitive data before text reaches the AI model. It targets items such as national ID numbers, bank account numbers, phone numbers, emails and amounts in documents. They are replaced with tokens such as account or phone placeholders. Deterministic code works on the real values, and only the final answer shown to the user is unmasked. The gateway is being rolled out, so coverage may be incomplete in this demo.

## Audit log

Every agent action is recorded in an append-only, hash-chained log. Each entry includes the actor, action, tier, a hash of the parameters, and the previous entry's hash. Each entry is signed with an Ed25519 key. Changing an old entry breaks the chain, which a verify endpoint can detect. Raw personal data is not stored in entries.

## Simulated demo

The demo uses synthetic suppliers, banks, lenders and documents. Lenders and providers in the financing catalogue are fictional. One-time passwords appear in a "Simulated SMS" panel. Nothing here is financial advice.
