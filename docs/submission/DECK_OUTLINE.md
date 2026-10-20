# Setu — Deck Outline (10 minutes), v1

The full deck is built in phase P28. This file fixes the flow, timing, speaker notes and the live screen for each
slide. Every number is from `docs/PROGRESS.md` and is **dev split, synthetic** unless it is a seeded demo number.
Say once, early: **all transactions are a simulated sandbox and no model was trained.**

Live URL: [TO FILL: live URL]. Guided demo: `/demo` (presenter mode `/demo/run?mode=presenter`, arrows to step).
Judge page: [TO FILL: live URL]/judges.

Rubric reminder: task completion 40% · security and compliance 30% · innovation and interaction 30%.

| # | Time | Slide | Live screen |
|---|---|---|---|
| 1 | 0:00–0:45 | Title and the one-line pitch | `/` landing hero |
| 2 | 0:45–1:45 | Problem | `/` problem band |
| 3 | 1:45–2:30 | Persona and scenario | `/app` dashboard as Rahima |
| 4 | 2:30–3:30 | Solution overview and Topic E coverage | `/` how-it-works |
| 5 | 3:30–6:00 | Live demo (guided) | `/demo/run` |
| 6 | 6:00–7:15 | Security design | `/demo/risk-playground`, `/demo/attack-console` |
| 7 | 7:15–8:15 | Evidence and measured results | `/verify`, `/app/admin/audit` |
| 8 | 8:15–9:00 | Innovation | `/demo/privacy-playground` |
| 9 | 9:00–9:30 | Architecture | diagram slide |
| 10 | 9:30–10:00 | Limits, roadmap, close | `/` footer, status chip |

## Slide 1 — Title (0:00–0:45)
- On slide: "Setu (সেতু) — AI SME Finance Copilot", Topic E, team name [TO FILL], "Simulated sandbox" badge.
- Notes: "Setu means bridge in Bangla. It bridges a Bangladeshi importer and a Chinese supplier with financing, cash-flow
  and safe payment. Everything you see is simulated. No model was trained. The AI explains; code decides."
- Show: landing hero with the three-state preview (shortfall, OTP approval, forged B/L blocked).

## Slide 2 — Problem (1:00)
- On slide: three pains: unclear cash gap before a supplier payment, document fraud and duplicate financing, payment
  redirection scams.
- Notes: SMEs pay Chinese suppliers by LC or TT in tranches. A missed gap stops production. A forged bill of lading or
  a changed bank account costs the whole advance. Market-size figures: use only figures you have verified; the landing
  page has two figures marked "[figure to verify]" (see `PROGRESS.md` 6.3), so do not quote them.
- Show: landing problem band (read only; do not read the unverified figures).

## Slide 3 — Persona (0:45)
- On slide: Rahima, Dhaka fabric importer (fictional), order SETU-2026-0001: 8,000 m fabric, goods USD 9,600,
  landed cost USD 11,200, three suppliers, one suspicious.
- Notes: one persona, one order, followed from question to final payment. Seeded demo numbers: cash USD 6,000, escrow
  holds the first tranche USD 2,880.
- Show: `/app` dashboard: KPIs and the shortfall alert of USD 1,560 on 2026-11-07.

## Slide 4 — Solution and Topic E coverage (1:00)
- On slide: FR-1 financing, FR-2 cash flow, FR-3 analysis, FR-4 KYB, FR-5 escrow, FR-6 forensics + registry,
  FR-7 FX route, FR-8 signed credit record, FR-9 explained chat (EN/BN/ZH).
- Notes: "Nine requirements, all built. Where something is mock we label it: FX spreads are mock, lenders are fictional."
- Show: landing "how it works" tabs.

## Slide 5 — Live demo (2:30)
Run the guided demo (12 steps, about 4 minutes full; present the highlights). Use presenter mode. Pre-flight first
(`/demo` shows a green/red list). Fall back to the offline replay if the network fails (`pnpm run demo:check` proves it).

Cut for 2:30, in this order:
1. Rahima asks in Bangla: streamed answer with a cash-flow card (USD 1,560 shortfall). (steps 1, 4)
2. Financing comparison: supplier credit chosen, simulated. Say why the escrow-backed Lender B loan is blocked (the invoice is already pledged at Lender A). (step 4)
3. Tier 2 one-tap release of tranche 1, paid in CNY with the FX saving. (step 6)
4. **Wow A.** Forged B/L: FAILED, hidden white text revealed, rule trace shows Tier 3, chat says it ignored the instruction. (step 9)
5. **Wow B.** Same invoice offered at Lender B: duplicate blocked. (step 10)
6. Signed credit record and audit chain verifies. (step 12)

Notes: say each of these was done by the real API, not a mock-up. The deviations (blocked Lender B loan, a labelled
time skip for cash in step 12) are stated honestly in `docs/demo.md`.

## Slide 6 — Security design (1:15)
- On slide: tiers 0–3 table; "LLM can only propose"; OTP + cooling-off; injection layers; Privacy Gateway.
- Notes: "Tiers are decided by a deterministic engine in code. The model is offered Tier 0 tools only, and a test asserts
  that. Tier 3 needs a cooling-off pause and a one-time code, enforced by timestamp on the server."
- Show: `/demo/risk-playground` (change amount over USD 20,000: tier flips to 3, rule trace shown), then
  `/demo/attack-console` with a hidden-instruction document, defences OFF then ON.

## Slide 7 — Evidence and measured results (1:00)
- On slide (label every number "dev split, synthetic"):
  - Forensics: precision and recall 1.00 on 11 checks, 10 fraud types; 0/50 clean packs flagged.
  - Registry: 5/5 duplicates caught (3 exact, 2 re-saved).
  - Injection: attack success 100% (defences off) to 0% (on), 13 attacks; false positives 0/300; money moved 0.
  - Privacy: 0 detectable identifiers reach the model payload; 1/600 ground-truth identifier leaked (explain).
- Notes: "These are ceilings on synthetic data. The test split is not run yet. We will report it once." Be ready for
  the question "why is dev perfect?": the generator and checks share a team; the injection harness uses an obedient mock.
- Show: `/verify` with a dropped export (verifies in the browser, nothing uploaded) and the tamper panel in
  `/app/admin/audit` (note: the tamper panel and chain page were not browser-checked at P20; rehearse first).

## Slide 8 — Innovation (0:45)
- On slide: four ideas: (1) every tier decision is explained with a rule trace and "what would change it" hints,
  (2) Privacy X-ray shows what the model actually saw, (3) a live attack console, (4) anyone can verify the log with a
  public key, no login.
- Show: `/demo/privacy-playground` or the eye icon on a chat message.

## Slide 9 — Architecture (0:30)
- On slide: the Mermaid diagram from `docs/architecture.mmd` (render it into the final deck).
- Notes: web talks only to the API; domain code has no LLM; the model client is one module; Postgres + pgvector.

## Slide 10 — Limits, roadmap, close (0:30)
- On slide: honest limits: synthetic data and dev-split numbers, no real authentication or SMS, mock FX spreads and
  lenders, Bangla and Chinese not natively reviewed. Roadmap: test-split report (P24), real auth, SMS, lender sandbox
  integration, native-speaker review.
- Notes: Close with the link, the `/judges` page [TO FILL], and the verify command `pnpm audit:verify`.

## Backup plan
- If the live site is down: run `pnpm run demo:check` output or play the recorded video [TO FILL: video URL].
- If the model provider is slow: the guided demo uses recorded model replies (fixtures in `data/demo/fixtures/llm/`).
- If the Demo phone panel is empty: the deployment must run with `DEMO_MODE=true` (see `docs/demo.md`).

## Open items for P28
- Screenshots into `docs/submission/img/` (not produced yet).
- Render the architecture diagram as an image (not produced; Mermaid text only).
- Team and university details [TO FILL].
