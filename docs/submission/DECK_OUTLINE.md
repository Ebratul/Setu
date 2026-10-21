# Setu — Deck Outline (10 minutes), v2

Flow: problem with data, Setu demo, security, measured results, impact for Chinese exporters and Bangladeshi SMEs,
roadmap. Nine slides, 10:00 in total.

Say once, early: **all transactions are a simulated sandbox and no model was trained.**

Rules for every slide:
- Quote only numbers from `backend/eval/results/metrics.json` (test split) or from the seeded demo data.
- Say "synthetic test split, a ceiling, not real-world accuracy" every time a measured number is shown.
- No market-size figure goes on a slide until the team has checked a source. The landing page still has two placeholders
  marked "[figure to verify]"; do not read them out.
- Rubric reminder: task completion 40% · security and compliance 30% · innovation and interaction 30%.

Live URL: [TO FILL: live URL]. Guided demo: `/demo` (presenter mode `/demo/run?mode=presenter`, arrows to step).
Judge page: [TO FILL: live URL]/judges. Team: [TO FILL: team name, members, universities].

| # | Time | Slide | Live screen |
|---|---|---|---|
| 1 | 0:00–0:30 | Title and one-line pitch | `/` landing hero |
| 2 | 0:30–1:30 | Problem, with data | `/app` dashboard as Rahima |
| 3 | 1:30–2:30 | Solution, Topic E coverage, architecture | `/` how-it-works, architecture diagram |
| 4 | 2:30–5:30 | Live demo (3 minutes) | `/demo/run?mode=presenter` |
| 5 | 5:30–6:45 | Security design | `/demo/risk-playground`, `/demo/attack-console` |
| 6 | 6:45–8:00 | Measured results | `backend/eval/results/metrics.md`, `/verify` |
| 7 | 8:00–8:30 | Innovation | `/demo/privacy-playground` |
| 8 | 8:30–9:20 | Impact: Chinese exporters and Bangladeshi SMEs | supplier portal (EN/中文) |
| 9 | 9:20–10:00 | Roadmap, limits, close | `/` footer, `/judges` |

## Slide 1 — Title (0:00–0:30)
- On slide: "Setu (সেতু) — AI SME Finance Copilot", Topic E, team [TO FILL], a "Simulated sandbox" badge.
- Say: "Setu means bridge in Bangla. It links a Bangladeshi importer and a Chinese supplier with financing, cash-flow
  and safe payment. Everything you see is simulated. No model was trained. The AI explains; code decides."
- Show: landing hero with the three-state preview (shortfall, OTP approval, forged B/L blocked).

## Slide 2 — Problem, with data (1:00)
Use one worked case, not market statistics. Persona: Rahima, a fictional Dhaka fabric importer; order SETU-2026-0001.
- On slide (seeded demo numbers, labelled "simulated"):
  - Goods USD 9,600.00; landed cost USD 11,200.00 once freight, insurance, duty and bank charges are added.
  - Sale value USD 13,660.00, so gross margin is 18.01%.
  - Milestones 30/60/10: USD 2,880 / 5,760 / 960. On 2026-11-07 her balance is USD 4,200 against a USD 5,760 payment:
    **a shortfall of USD 1,560.00**, found 18 days ahead.
- Three pains (say in your own words): (1) the cash gap is not visible before a supplier payment; (2) a forged bill of
  lading or a reused invoice can cost the whole advance; (3) a "please pay our new account" e-mail redirects the money.
- Market context: [TO FILL: one or two sourced figures with source and year, or leave out].
- Show: `/app` dashboard, the shortfall alert of USD 1,560 on 2026-11-07.

## Slide 3 — Solution, coverage, architecture (1:00)
- On slide: nine requirements in one row: FR-1 financing, FR-2 cash flow, FR-3 order analysis, FR-4 supplier KYB,
  FR-5 milestone escrow, FR-6 document forensics and duplicate-financing registry, FR-7 FX route and rate lock, FR-8
  signed credit record, FR-9 explained chat in English, Bangla and Chinese.
- Also on slide: the Mermaid diagram from `docs/architecture.mmd`, rendered to an image (not produced yet).
- Say: "The web app only talks to the API. Domain code has no LLM. One module calls models. Everything is written to a
  signed log. Where something is mock, we label it: FX spreads are mock, lenders are fictional."

## Slide 4 — Live demo (3:00)
Use the guided demo in presenter mode. Run the pre-flight first (`/demo` shows a green/red list). Fallback: offline
replay (`pnpm run demo:check`, 27 of 27 scenes recorded at P21) or the video [TO FILL: video URL].
Demo steps are numbered as in `docs/demo.md`.

| Time | Step | What to show | Say |
|---|---|---|---|
| 2:30 | 1, 4 | Rahima asks in Bangla; cash-flow card shows USD 1,560 shortfall; financing compared; supplier credit applied (simulated) | "Numbers come from code. The AI explains." |
| 3:15 | 6 | Tier 2 one-tap release of tranche 1, paid in CNY, FX saving shown | "Money moves only after a person taps." |
| 3:45 | 9 | **Wow A.** Forged B/L: FAILED, hidden white text revealed, rule trace shows Tier 3, chat says it ignored the instruction | "Document text is data, never instructions." |
| 4:30 | 10 | **Wow B.** Same invoice offered at Lender B: duplicate blocked | "One invoice, one loan." |
| 5:00 | 12 | Signed credit record; audit chain verifies | "Anyone can check the log." |

Notes: say each step calls the real API. Be honest about the two deviations in `docs/demo.md`: the escrow-backed Lender B
loan is blocked on purpose (invoice already pledged at Lender A), and step 12 uses a labelled time skip for cash.

## Slide 5 — Security design (1:15)
- On slide: tier table 0 to 3 plus BLOCK; "LLM can only propose"; cooling-off 600 s then OTP; five injection layers;
  Privacy Gateway; signed hash-chained log. Map to SR-1 to SR-9.
- Say: "Tiers are decided by a deterministic engine in code. The model is offered Tier 0 tools only, and a test asserts
  that. Tier 3 needs a cooling-off pause and a one-time code, enforced by timestamp on the server."
- Show: `/demo/risk-playground` (set the amount over USD 20,000: tier flips to 3, rule trace shown), then
  `/demo/attack-console` with a hidden-instruction document, defences off then on.
- Honest line: "Judges use demo login. Real sign-in exists but has not had an independent review."

## Slide 6 — Measured results (1:15)
Title the slide: "Test split, synthetic data: a ceiling, not real-world accuracy". All from `metrics.json`, 2026-10-20.

| Area | Result |
|---|---|
| Fraud checks (100 packs, 11 checks, 10 fraud types) | precision 1.0, recall 1.0 (WARN or FAIL counts); FAIL only: recall 0.9508 |
| Clean packs flagged | 0 of 50 |
| Duplicate documents caught | 5 of 5 |
| Injection attack success (12 attacks) | defences off 100%, on 0% |
| Injection detector | recall 100%; false positives 0 of 300 clean documents |
| Money moved by injection | 0 |
| Bank identifiers reaching the model (600 documents) | masking off 600, on 0 |
| Tampered packs auto-released | 0 of 50 (27 escalated, 23 blocked); clean packs auto 50 of 50 |

- Say: "Why is it perfect? The data is synthetic and our team built the generator and the checks. The injection test uses
  an obedient mock model, so it does not prove the delimiters hold against a real model. We report it once, on the test
  split, after tuning only on dev."
- Show: `/verify` with a dropped export (verifies in the browser, nothing uploaded), or `metrics.md`. Rehearse the tamper
  panel in `/app/admin/audit` first; it was not browser-checked at P20.

## Slide 7 — Innovation (0:30)
- On slide: four ideas. (1) Every tier decision has a rule trace and "what would change it" hints. (2) A Privacy X-ray
  shows what the model actually saw. (3) A live attack console. (4) Anyone can verify the log with a public key, no login.
- Show: `/demo/privacy-playground` or the eye icon on a chat message.

## Slide 8 — Impact (0:50)
State clearly: these are design benefits shown in the demo, **not measured outcomes**. No customer or revenue figure.
- **Bangladeshi SMEs:** see the cash gap days before it bites (USD 1,560 in the demo); compare financing options by total
  cost; one place to check a supplier before paying; plain-language answers in Bangla.
- **Chinese exporters:** a supplier portal in Chinese; payment tranches released when evidence is verified, so the
  supplier knows the money is held; a signed credit record issued when a deal completes, which a lender can verify with the public key;
  changes to payout accounts only through the portal, which protects them from impersonation.
- **Lenders and banks:** a duplicate-financing registry across lenders and a signed, verifiable audit trail.
- Impact numbers: [TO FILL only if the team has a sourced figure or a pilot result; otherwise leave this out].

## Slide 9 — Roadmap, limits, close (0:40)
- Limits (say them): synthetic data and mock model in the injection test; judge deployment uses demo login; no SMS provider;
  PayPal is Sandbox only and optional; mock FX spreads and lenders; Bangla and Chinese text not reviewed by native speakers.
- Roadmap: (1) evaluate on real, consented documents and with a real model attacking; (2) independent security review of
  sign-in and approvals; (3) SMS or authenticator second factor and a non-owner audit database role; (4) lender and bank
  sandbox integrations; (5) HS-code duty table and loan repayment flow; (6) native-speaker review; (7) optional public
  anchor of the registry (an interface exists, nothing is wired).
- Close: repository [TO FILL], `/judges` [TO FILL], and `pnpm audit:verify`.

## Backup plan
- Live site down: play the recorded video [TO FILL: video URL] or show `pnpm run demo:check` output.
- Model provider slow: the guided demo uses recorded model replies (`data/demo/fixtures/llm/`).
- Demo phone panel empty: the deployment needs `DEMO_MODE=true` (see `docs/demo.md`).

## Open items
- Screenshots into `docs/submission/img/` (not produced).
- Render the architecture diagram as an image (not produced; Mermaid text only).
- Build the actual slides from this outline: [TO FILL: deck file name].
