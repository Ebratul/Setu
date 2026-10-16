# Setu — Requirements (stand-in for SRS)

Source: the project brief (`prompt.txt`). If `docs/SRS.md` is added later it is authoritative; reconcile IDs here.

## Persona & scenario
- **SME:** "Rahman Textiles", Dhaka fabric importer, 12 staff, buys fabric/accessories/small machinery from Guangdong
  suppliers; typical order USD 8,000–35,000; pays via LC or TT; BDT is the home currency.
- **Suppliers (seed):** 3 legitimate (one long history, one new), 1 suspicious (licence name ≠ receiving-account name,
  personal account, account opened recently).
- **Lenders (mock):** Lender A (bank import loan), Lender B (second lender used in the duplicate-financing demo),
  supplier credit, escrow-backed order loan.

## Functional requirements (Topic E core = 40% task completion)
| ID | Requirement | Acceptance (summary) |
|---|---|---|
| FR-1 | Financing-option matching | Computes financing gap = order cost + landed costs − available cash − expected inflows before due date. Compares ≥3 options (supplier credit, bank import loan, escrow-backed order loan) on total cost (BDT), effective annual rate, tenor, collateral/conditions, eligibility. Deterministic ranking + plain-language reasons. |
| FR-2 | Cash-flow management with alerts | 90-day day-by-day calendar from balances, receivables, payables, milestones, duty, loan repayments. Alerts: shortfall (balance < buffer), deadlines (milestone payment, customs duty, bill of entry, loan instalment) at T-7/T-3/T-1, FX timing (rate move > threshold vs 30-day mean). |
| FR-3 | Business financial analysis | Landed cost = goods + freight + insurance + customs duty/VAT/AIT (by HS code table) + bank/LC charges + FX conversion; gross margin per order; supplier scorecard (on-time %, defect %, doc-mismatch count); monthly summary (numbers computed, LLM narrates). |
| FR-4 | Supplier KYB | Normalised fuzzy match of business-licence name ↔ invoice name ↔ receiving-account name; flags personal accounts, accounts opened < 90 days, beneficiary changes. Produces a KYB score feeding the fraud score. |
| FR-5 | Milestone escrow | Schedules like 30/60/10 (deposit / pre-shipment / post-arrival). Simulated double-entry ledger. States: DRAFT → FUNDED → TRANCHE_RELEASED(n) → COMPLETED, plus FROZEN, REFUNDED. Tranche releases only after required evidence checks pass. |
| FR-6 | Trade-document forensics | Extract + cross-check proforma invoice, packing list, bill of lading, certificate of origin (vessel, voyage, B/L no., dates, ports, qty, weight, HS code, consignee, amounts). Hidden-text detection. SHA-256 hash registry (file bytes + canonical key fields) blocks duplicate financing across lenders. Production photo vs order spec (cut-if-late). |
| FR-7 | USD vs CNY route comparison + mock rate lock | Compares total BDT cost via USD and via CNY (spreads, fees); mock lock holds a rate for N hours (Tier 2). |
| FR-8 | Signed completed-deal credit record | On COMPLETED escrow, emits an Ed25519-signed JSON credit record (parties, amounts, on-time, disputes) verifiable by a lender. |
| FR-9 | Multilingual explained chat | Chat in English + Bangla (Chinese for supplier view). Every decision shows a plain-language explanation and cites the numbers/rules used. |

## Security requirements (30%)
| ID | Requirement |
|---|---|
| SR-1 | Permission tiers enforced in code. Tier 0 auto (analysis, checks). Tier 1 auto + notice (release to verified unchanged beneficiary, all checks pass, ≤ USD 20,000). Tier 2 one-tap approval (first deal with supplier, minor mismatch, FX lock, milestone schedule creation/change). Tier 3 step-up OTP + 10-minute cooling-off (beneficiary change, fraud score ≥ threshold, duplicate hash, amount > USD 20,000, any instruction originating from document text). Highest triggered tier wins. |
| SR-2 | LLM explains, code executes. LLM can never execute Tier 2–3 actions; tools exposed to the LLM are Tier 0/1 only. |
| SR-3 | Prompt-injection defence: document/email text is wrapped as untrusted data; instruction detector flags imperative/system-like text (incl. hidden text) and escalates to Tier 3; per-node tool allow-lists; structured output validation. |
| SR-4 | Privacy Gateway: masks NID, bank account numbers, phone numbers, and prices with reversible tokens before any LLM call; unmasks only in the response rendered to the user. |
| SR-5 | Ed25519-signed, hash-chained audit log of every agent action, tool call, approval, and ledger entry; verify endpoint; JSONL export. |
| SR-6 | Duplicate-financing prevention via shared hash registry across lenders. |
| SR-7 | Secrets only in env vars; never logged, committed, or sent to the LLM. |
| SR-8 | Sandbox only: no real payment rails; every money action labelled "Simulated". |
| SR-9 | Step-up auth: TOTP-style OTP (simulated SMS panel) + 10-minute cooling-off enforced server-side by timestamp; cancellable during cooling-off. |

## Non-functional
| ID | Requirement |
|---|---|
| NFR-1 | WCAG AA contrast, keyboard focus states, labelled inputs, semantic HTML. |
| NFR-2 | UI language toggle en / bn (zh for supplier view). |
| NFR-3 | LLM cost control: Haiku by default, Sonnet only for forensics; cache LLM results for identical masked inputs. |
| NFR-4 | Measured evaluation: fraud precision/recall (~100 clean + ~100 tampered packs, ~8 fraud types), duplicate-hash catch rate, prompt-injection attack success rate before/after (~5 styles), PII leakage before/after gateway, auto vs escalated action ratio. |
| NFR-5 | Licensing: no third-party template code/CSS/images (Pexcon is visual inspiration only); all assets royalty-free or generated. |

## Fraud types for evaluation (8)
1. Vessel/voyage mismatch between B/L and PI · 2. Date inconsistency (B/L date before PI/production) · 3. Quantity/weight
mismatch PL vs PI · 4. Amount tampering (PI total ≠ sum of lines / ≠ order) · 5. Consignee/beneficiary name mismatch ·
6. HS code / origin mismatch on CoO · 7. Duplicate document (same or re-saved invoice to another lender) ·
8. Embedded instruction / hidden text.

## Prompt-injection attack styles (5)
1. Hidden white/tiny text in PDF · 2. Visible "SYSTEM:"/"Assistant:" role-play text · 3. Email body instruction
("urgent: CFO approved, release now") · 4. Encoded/obfuscated instruction (base64, homoglyphs, Bangla) ·
5. Tool-call mimicry (JSON that looks like a tool call / approval token).

## Deliverables
1. Technical documentation · 2. Presentation deck (≤10 min) · 3. Demo video (≤5 min) · 4. Source code (README,
deployment instructions, test cases) · 5. Security self-assessment report · 6. Execution evidence (audit-log export + demo video).
