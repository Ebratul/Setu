# Setu — Part-by-part build guide (28 parts)

প্রতিটা part একটা **নতুন Claude Code session**-এ করবে। নিয়ম:

1. Session শুরু → নিচের "Session prompt" paste করো।
2. Part শেষ → tests চালাও, `phase-handoff` skill চালাও (PROGRESS.md update + commit)।
3. তারপর `/clear` → পরের part।
4. Claude Code-এর বানানো `docs/PLAN.md`-এর সাথে কোথাও অমিল হলে **PLAN.md-ই প্রাধান্য পাবে**; এই guide শুধু ছোট ছোট ভাগ আর ক্রম ঠিক রাখার জন্য।

**Must-have by 19 Oct:** Part 1–20 + Part 23 (first submission)। **Cut if late:** Chinese UI, supplier scorecard, photo inspection, on-chain hash anchoring।

---

## Day 1 — 17 Oct: Foundation + Topic E core (40% score)

### Part 01 — Repo scaffold
- **Goal:** Monorepo চালু করা।
- **Done when:** `apps/web` (Next.js + TS + Tailwind) আর `services/agent` (FastAPI) দুটোই local-এ চলে; docker-compose-এ Postgres + pgvector; `.env.example`; lint/format কাজ করে।
- **Session prompt:**
  > Phase P01. Read CLAUDE.md, docs/PROGRESS.md, docs/PLAN.md (Stage 0 only). Scaffold the monorepo: apps/web (Next.js App Router, TypeScript, Tailwind), services/agent (FastAPI, Python 3.11, uv or pip-tools), docker-compose with Postgres 16 + pgvector, .env.example files (no secrets), lint/format setup (ESLint+Prettier, Ruff). Add a health endpoint to the agent and a placeholder home page. Verify both run. Then run the phase-handoff skill.

### Part 02 — Database schema
- **Goal:** SRS অংশ ৮-এর ৯টা entity।
- **Done when:** Prisma schema + migration; Python side-এ matching SQLAlchemy models (read/write ownership PLAN.md অনুযায়ী); migration সফল।
- **Session prompt:**
  > Phase P02. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md section 8, .claude/rules/money-logic.md. Implement the schema (Party, BankAccount, Deal, Milestone, Document, LedgerEntry, CashFlowItem, FinancingOption, AuditLog) plus a HashRegistry table. Money as Decimal/numeric, never float. Create migrations and matching SQLAlchemy models following the ownership model in docs/PLAN.md. Run migrations and a smoke test. Then phase-handoff.

### Part 03 — Seed data & mock catalogues
- **Goal:** Demo-র জন্য বাস্তবসম্মত mock data।
- **Done when:** ৩ supplier (একটার account নাম অমিল), ২ buyer (রহিমা আপা সহ), FX rates (USD/CNY/BDT), financing catalogue (≥৩ ধরন), ৯০ দিনের cash-flow items, রহিমা আপার USD 9,600 deal।
- **Session prompt:**
  > Phase P03. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md section 9. Create an idempotent seed script with: 3 Chinese suppliers (one with a mismatched account holder name), 2 Bangladeshi buyers including "Rahima Knitwear, Narayanganj" holding USD 6,000, mock FX rates USD/CNY/BDT, a financing catalogue (supplier credit, bank import loan, escrow-backed order loan) with rates and tenors, 90 days of cash-flow items, and the USD 9,600 fabric deal from a Shaoxing mill. Label all data as simulated. Then phase-handoff.

### Part 04 — Money logic library
- **Goal:** সব টাকার হিসাব deterministic code-এ।
- **Done when:** Python module: landed cost, margin, FX conversion, financing cost; সব Decimal; unit tests pass (SRS TC-10)।
- **Session prompt:**
  > Phase P04. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/money-logic.md, .claude/rules/testing.md. Build services/agent/finance/ with pure functions: landed_cost (goods, shipping, duty, bank charges, FX), gross_margin, convert_fx, financing_total_cost (rate, tenor, fees). Use Decimal with explicit rounding. Write thorough pytest unit tests including hand-calculated cases. No LLM code here. Then phase-handoff.

### Part 05 — FR-3 Business financial analysis
- **Goal:** Order analysis API + UI।
- **Done when:** `/analysis/order/{id}` landed cost + margin দেয়; web-এ Order Analysis page; monthly summary (S priority) সময় থাকলে।
- **Session prompt:**
  > Phase P05. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-3, .claude/rules/frontend.md. Expose FastAPI endpoints for order analysis (landed cost breakdown, gross margin) using the P04 library, and a Next.js "Order Analysis" page with a clear cost breakdown and margin. Add API tests. Supplier scorecard only if time remains. Then phase-handoff.

### Part 06 — FR-2 Cash-flow + alerts
- **Goal:** ৯০ দিনের calendar আর alert engine।
- **Done when:** Shortfall, deadline (milestone, duty, bill of entry) আর FX alert generate হয়; UI-তে calendar + alert list; TC-08 pass।
- **Session prompt:**
  > Phase P06. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-2. Build a deterministic cash-flow forecaster (90 days, inflows/outflows, running balance) and an alert engine (shortfall with exact amount and date, deadline alerts for milestone payments, duty and bill of entry, FX timing alert). Expose endpoints and a Next.js Cash Flow page with a calendar/timeline and alert list. Tests must cover TC-08. Then phase-handoff.

### Part 07 — FR-1 Financing matching
- **Goal:** Financing gap + ৩টা option তুলনা।
- **Done when:** Gap হিসাব; option গুলো মোট খরচ, মেয়াদ, শর্তসহ ranked; UI comparison table; TC-09 pass।
- **Session prompt:**
  > Phase P07. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-1. Implement financing gap calculation and option matching from the catalogue: compute total cost, tenor and conditions for each, rank them deterministically, and return a structured reason for the top pick (the LLM will phrase it later). Endpoint + Next.js Financing page with a side-by-side comparison. Tests for TC-09. Then phase-handoff.

---

## Day 2 — 18 Oct: Agent + edge features

### Part 08 — LangGraph agent skeleton
- **Goal:** Chat endpoint যেটা Claude + LangGraph দিয়ে চলে।
- **Done when:** `/chat` endpoint; Haiku/Sonnet routing; LangSmith tracing দেখা যায়; streaming বা simple response।
- **Session prompt:**
  > Phase P08. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/agent-python.md. Create the LangGraph agent graph (state, router node, tool node, response node) using langchain-anthropic (Haiku default, Sonnet for document reasoning), LangSmith tracing via env vars, and a /chat endpoint. No money-moving tools yet. Add a test with a mocked model. Then phase-handoff.

### Part 09 — Core tools + chat UI
- **Goal:** Agent FR-1/2/3 ব্যবহার করতে পারে।
- **Done when:** `analyze_order`, `forecast_cashflow`, `match_financing` tools; Next.js chat page (English + Bangla toggle); প্রতিটা উত্তরে plain-language explanation।
- **Session prompt:**
  > Phase P09. Read CLAUDE.md, docs/PROGRESS.md, .claude/skills/new-agent-tool/SKILL.md, docs/SRS.md section 5.2. Wrap the P05–P07 logic as LangChain tools analyze_order, forecast_cashflow, match_financing (all Tier 0). Build the Next.js chat UI with an English/Bangla toggle that renders tool results as cards plus a one-line explanation. Tests for tool wiring. Then phase-handoff.

### Part 10 — RAG knowledge base
- **Goal:** Rules আর catalogue থেকে cited উত্তর।
- **Done when:** ছোট knowledge base (BB advance-payment rule সারাংশ, Incoterms, document field definitions, financing catalogue) pgvector-এ; `retrieve_knowledge` tool citation দেয়।
- **Session prompt:**
  > Phase P10. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/agent-python.md. Create services/agent/kb/ with short markdown sources (Bangladesh Bank advance-payment rule summary incl. USD 20,000 limit, Incoterms basics, trade-document field definitions, financing catalogue). Embed into pgvector, add a retrieve_knowledge tool that returns snippets with source names, and make the agent cite them. Keep it small. Tests for retrieval. Then phase-handoff.

### Part 11 — Synthetic trade documents
- **Goal:** Clean আর জাল document pack বানানো (testing ও eval-এর জন্য)।
- **Done when:** Generator ~১০০ clean + ~১০০ tampered pack (~৮ fraud type, hidden-text injection সহ); demo-র জাল B/L।
- **Session prompt:**
  > Phase P11. Read CLAUDE.md, docs/PROGRESS.md, .claude/skills/generate-synthetic-docs/SKILL.md. Build a generator for trade-document packs (proforma invoice, packing list, bill of lading, certificate of origin) as PDFs/JSON: ~100 clean and ~100 tampered across ~8 fraud types (quantity/value mismatch, vessel/date mismatch, name mismatch, duplicate invoice, price outlier, altered beneficiary, hidden white-text instruction, wrong port). Save labels to a manifest. Keep generated files out of git if large. Then phase-handoff.

### Part 12 — Supplier KYB
- **Done when:** `verify_party` license/invoice/account নাম মেলায়, personal/new account flag করে; TC-01 pass।
- **Session prompt:**
  > Phase P12. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-4. Implement verify_party: compare license name, invoice name and receiving account holder name (normalised fuzzy match), flag personal or newly seen accounts and registry history, return a structured result. Add as a Tier 0 tool and show the result in the deal view. Tests for TC-01. Then phase-handoff.

### Part 13 — Escrow & milestones
- **Done when:** Simulated ledger; milestone propose/confirm; `release_tranche` (এখনো tier ছাড়া, কিন্তু evidence check বাধ্যতামূলক)।
- **Session prompt:**
  > Phase P13. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-5, .claude/rules/money-logic.md. Build the simulated escrow ledger (fund, release, refund entries), propose_milestones (e.g., 30/60/10 with acceptance conditions, both parties confirm) and release_tranche that refuses unless the milestone's evidence status is verified. Leave a clear hook point for the risk-tier engine (P15). UI: deal timeline with milestones. Tests. Then phase-handoff.

### Part 14 — Document forensics
- **Done when:** `check_documents` extraction + cross-check (quantity, value, vessel, port, date); fraud score; TC-02, TC-03 pass।
- **Session prompt:**
  > Phase P14. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-6, .claude/rules/security.md. Implement check_documents: LLM extraction (Sonnet) into a strict pydantic schema, then deterministic cross-checks across documents and against the deal, producing a fraud score and reasons. Document text must never be treated as instructions. Cache results by file hash. Tests using P11 packs for TC-02 and TC-03. Then phase-handoff.

### Part 15 — Hash registry
- **Done when:** SHA-256 registry; একই invoice দ্বিতীয় lender-এ গেলে block; TC-05 pass।
- **Session prompt:**
  > Phase P15. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md FR-6.2. Implement the SHA-256 hash registry (hash → deal, lender, timestamp), check it on every document upload and financing request, and return a duplicate flag that P16 will map to Tier 3. Add a second mock lender to reproduce the demo. Tests for TC-05. Then phase-handoff.

---

## Day 3 — 19 Oct: Security layer + demo + first submission

### Part 16 — Risk-tier engine
- **Done when:** Tier 0–3 rule engine; সব money tool tier code-এ enforce করে; LLM Tier 2–3 চালাতে পারে না; TC-07 pass।
- **Session prompt:**
  > Phase P16. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/security.md, docs/SRS.md section 6.1. Build the deterministic risk-tier engine (inputs: amount vs USD 20,000, first deal, beneficiary change, fraud score, duplicate hash, instruction-from-document flag) and enforce it inside release_tranche, lock_fx and propose_milestones so the LLM cannot bypass it. Return pending-approval states for Tier 2–3. Tests for TC-07 and bypass attempts. Then use the security-reviewer subagent on the diff. Then phase-handoff.

### Part 17 — Approval UI + OTP
- **Done when:** One-tap approval modal (Tier 2); simulated OTP + ১০ মিনিট cooling-off (Tier 3); beneficiary বদল শুধু in-app (TC-06)।
- **Session prompt:**
  > Phase P17. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/frontend.md, .claude/rules/security.md. Build the approval flow: Tier 2 one-tap modal, Tier 3 simulated OTP plus a 10-minute cooling-off timer (configurable short value for demo), and an in-app-only beneficiary change flow. Email-originated change requests are blocked with a warning. Tests for TC-06. Then phase-handoff.

### Part 18 — Privacy Gateway
- **Done when:** NID, account, phone, price reversible token দিয়ে mask; LLM-এ আসল value যায় না; TC-11 pass।
- **Session prompt:**
  > Phase P18. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/security.md. Implement the Privacy Gateway as middleware before every LLM call: detect and replace NID numbers, bank account numbers, phone numbers and prices with reversible tokens, restore them in tool outputs shown to the user, and log leakage counts for evaluation. Tests for TC-11. Then phase-handoff.

### Part 19 — Prompt-injection defense
- **Done when:** Document/email-এর hidden instruction detect; উপেক্ষা + Tier 3 flag; ৫ ধরনের attack test; TC-04 pass।
- **Session prompt:**
  > Phase P19. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/security.md. Add injection defences: wrap untrusted document/email text as data, detect instruction-like content (including hidden white text from P11), never act on it, and raise the instruction-from-document flag to Tier 3. Write tests for ~5 attack styles and TC-04. Run the security-reviewer subagent. Then phase-handoff.

### Part 20 — Signed audit log
- **Done when:** প্রতিটা action Ed25519-signed + hash-chained; verify script; JSON export (execution evidence)।
- **Session prompt:**
  > Phase P20. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/security.md. Make every agent action write an AuditLog entry signed with Ed25519 and hash-chained to the previous entry; add a verify command that detects tampering and an export endpoint producing the operation-log file for submission. Show the log in an admin view. Tests. Then phase-handoff.

### Part 21 — Demo scenario end-to-end
- **Done when:** রহিমা আপার ১২ ধাপ (SRS অংশ ৯) এক ক্লিকে চালানো যায়; wow moment (জাল B/L + duplicate) কাজ করে।
- **Session prompt:**
  > Phase P21. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md section 9. Build a "Run demo" mode that walks through Rahima's 12-step scenario with seeded data, including the forged bill of lading with hidden text and the duplicate-financing attempt at a second lender. It must be deterministic and resilient (cached LLM results as fallback). Add an end-to-end test. Then phase-handoff.

### Part 22 — UI polish + landing page
- **Done when:** Pexcon-inspired landing page (নিজস্ব Tailwind design, copy করা না); dashboard; mobile responsive; Bangla toggle সব জায়গায়।
- **Session prompt:**
  > Phase P22. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/frontend.md, .claude/skills/new-ui-page/SKILL.md. Build the landing page and polish the dashboard in a clean minimal business style inspired by Pexcon (sticky header, strong hero, hover cards, testimonial-style section, clear CTA) recreated from scratch in Tailwind with our own tokens and royalty-free assets — do not copy template code or images. Ensure responsive layout, WCAG AA contrast, focus states and the Bangla toggle. Then phase-handoff.

### Part 23 — Deploy + first submission
- **Done when:** Web Vercel-এ, agent service VPS বা Render-এ live; README-র প্রাথমিক version; registration ও প্রথম version email-এ জমা।
- **Session prompt:**
  > Phase P23. Read CLAUDE.md, docs/PROGRESS.md, docs/PLAN.md (Stage 8). Deploy apps/web to Vercel and services/agent to the chosen host with environment variables configured securely, run the demo on production, and write a first README (setup, deployment, test commands). Prepare a checklist of what to email for the first submission. Then phase-handoff.

---

## Day 4 — 20 Oct: Evaluation + deliverables (deadline Dhaka রাত 9:59)

### Part 24 — Evaluation harness
- **Done when:** Real metrics: fraud precision/recall, duplicate catch rate, injection success before/after, PII leakage before/after, auto vs escalated; results JSON + chart।
- **Session prompt:**
  > Phase P24. Read CLAUDE.md, docs/PROGRESS.md, .claude/skills/run-eval/SKILL.md, docs/SRS.md section 10. Build and run the evaluation harness on the P11 packs and attack set; record real numbers (no assumed values) to eval/results.json and a markdown summary with simple charts. Use the eval-runner subagent. Then phase-handoff.

### Part 25 — Technical documentation
- **Done when:** Architecture, core algorithm (risk engine, forensics, forecasting), security design — English।
- **Session prompt:**
  > Phase P25. Read CLAUDE.md, docs/PROGRESS.md, docs/SRS.md, eval/results summary. Use the docs-writer subagent to write docs/submission/technical-documentation.md: system architecture, core algorithm descriptions (risk-tier engine, document forensics, cash-flow forecaster, financing matcher), security design, and evaluation results. English, concise, with diagrams where helpful. Then phase-handoff.

### Part 26 — Security self-assessment
- **Done when:** Permission-tier implementation (code reference সহ) + known-risk list (SRS অংশ ১২) + test evidence।
- **Session prompt:**
  > Phase P26. Read CLAUDE.md, docs/PROGRESS.md, .claude/rules/security.md, docs/SRS.md section 12. Write docs/submission/security-self-assessment.md: permission-tier implementation with file/function references, known-risk list with mitigations, test and eval evidence, and residual risks. Have the security-reviewer subagent check it against the code. Then phase-handoff.

### Part 27 — Final README, tests, operation log
- **Done when:** README সম্পূর্ণ; সব test pass; audit log export file; GitHub repo public/শেয়ারযোগ্য।
- **Session prompt:**
  > Phase P27. Read CLAUDE.md, docs/PROGRESS.md. Finalise README (overview, architecture image, setup, deployment, test commands, demo steps, licence notes for third-party assets), make sure all tests pass, export the sandbox operation log from a fresh demo run to docs/submission/execution-evidence/, and verify the repo is ready to share. Then phase-handoff.

### Part 28 — Deck outline, video script, final submission
- **Done when:** ১০ মিনিটের deck outline, ৫ মিনিটের video script, final email checklist।
- **Session prompt:**
  > Phase P28. Read CLAUDE.md, docs/PROGRESS.md, docs/submission/*. Write docs/submission/deck-outline.md (10-minute flow: problem with data, Setu demo, security, measured results, impact for Chinese exporters and Bangladeshi SMEs, roadmap) and docs/submission/demo-video-script.md (under 5 minutes, scene by scene). Produce a final submission checklist covering all 6 required deliverables. Then phase-handoff.
