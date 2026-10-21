# Setu — Demo Video Script (target 4:40, hard limit 5:00)

Format: screen recording with voice-over, from `/demo/run?mode=record` (recording mode) on the final build.
Language: English voice-over, English captions. Everything shown is a simulated sandbox with fictional data.
Word budget: about 600 spoken words (about 130 words a minute). Read each scene aloud once and time it.

Before recording:
- Pre-flight at `/demo` is all green. Use replay mode so answers are identical (`DEMO_REPLAY=true`).
- Use the deployment that will be submitted. Record the numbers as they appear; do not edit them.
- Keep a visible "Simulated" badge in frame. Hide any browser bookmark or tab that shows private data.
- Do not show `.env`, keys, or the Neon, PayPal or model-provider dashboards.
- Final video link: [TO FILL: video URL]. Team: [TO FILL: team name].

Numbers below are the seeded demo values (fictional) or from `backend/eval/results/metrics.md` (test split, synthetic).

| # | Time | Scene | Screen |
|---|---|---|---|
| 1 | 0:00–0:20 | Hook and disclaimer | Landing hero |
| 2 | 0:20–0:50 | The problem: a hidden cash gap | Dashboard, shortfall alert |
| 3 | 0:50–1:20 | Ask in Bangla, get a cited answer | Chat |
| 4 | 1:20–1:50 | Fix it: compare financing | Financing page |
| 5 | 1:50–2:15 | Pay safely: one-tap release | Deal page, approval |
| 6 | 2:15–3:00 | Attack 1: forged bill of lading with hidden text | Document viewer, rule trace |
| 7 | 3:00–3:25 | Attack 2: same invoice at another lender | Registry result |
| 8 | 3:25–3:50 | Big payment needs a pause and a code | Approvals, Demo phone |
| 9 | 3:50–4:20 | Proof: signed log, anyone can verify | `/verify` |
| 10 | 4:20–4:40 | Measured results and close | Results slide |

## Scene 1 — Hook (0:00–0:20)
- Screen: landing hero with the three-state preview. Badge "Simulated sandbox" in frame.
- Voice-over: "This is Setu, which means bridge in Bangla. It helps Bangladeshi small businesses that import from
  Chinese suppliers. Everything you see is a simulated sandbox with fictional data, and no model was trained.
  The AI explains. Code decides."
- On-screen text: "Simulated sandbox · no model trained".

## Scene 2 — The problem (0:20–0:50)
- Screen: log in as Rahima (judge/demo login); dashboard; zoom on the shortfall alert.
- Voice-over: "Meet Rahima, a fabric importer in Dhaka. She has one order from a Chinese supplier. Goods cost nine
  thousand six hundred dollars. With freight, insurance, duty and bank charges, landed cost is eleven thousand two hundred
  dollars, and her margin is eighteen percent. But Setu looks ahead. On the seventh of November she will be one thousand
  five hundred and sixty dollars short of the second supplier payment. She sees it eighteen days early."
- On-screen text: "Landed cost USD 11,200.00 · margin 18.01% · shortfall USD 1,560.00 on 2026-11-07 (simulated)".

## Scene 3 — Ask in Bangla (0:50–1:20)
- Screen: open chat; type a short Bangla question about the cash gap; show the streamed answer, the card and the "Why" line
  and a source tag such as [S1].
- Voice-over: "She asks in Bangla. The answer arrives with a card and a short 'why' line. Every number on that card was
  calculated by code, not by the model. The model only writes the explanation, and cites its source."
- Note: use a question that has a recorded replay fixture (guided demo step 1).

## Scene 4 — Compare financing (1:20–1:50)
- Screen: financing page, gap card, ranked options, the blocked escrow-backed loan with its reason, apply to supplier credit.
- Voice-over: "Setu compares the options by total cost, effective annual rate and tenor, and shows why each is eligible
  or not. The escrow-backed loan is blocked here, because this invoice is already pledged at another lender. Rahima
  applies for supplier credit. It is a simulated application, and the shortfall alert clears."
- On-screen text: "Simulated application".

## Scene 5 — One-tap release (1:50–2:15)
- Screen: deal page, tranche 1 release, rule trace showing Tier 2, tap to approve, FX saving for paying in CNY.
- Voice-over: "Paying the supplier goes through milestone escrow. The first release is Tier 2, so a person has to tap.
  The AI can only propose this payment. It cannot approve it. Here the payment goes out in Chinese yuan, and Setu shows
  the saving against the dollar route. Spreads in this demo are mock values."

## Scene 6 — Attack 1: forged bill of lading (2:15–3:00)
- Screen: supplier uploads a forged bill of lading; document viewer shows FAILED; reveal hidden white text; rule trace
  shows Tier 3; chat says it ignored the instruction.
- Voice-over: "Now an attack. A forged bill of lading arrives. Setu runs eleven cross-checks, and the document fails.
  Hidden in white text is an instruction telling the AI to release all funds. Setu shows that hidden text. Document text is
  data, never instructions. Finding an instruction raises the action to Tier 3, and the AI says it ignored it. No money
  moves."
- On-screen text: "Document text is data, never instructions".

## Scene 7 — Attack 2: duplicate invoice (3:00–3:25)
- Screen: the same invoice offered at Lender B; registry result "duplicate", blocked.
- Voice-over: "Next, the same invoice is offered to a second lender. Setu fingerprints documents by file hash and by invoice
  fields, across lenders, so the duplicate is caught. One invoice, one loan."

## Scene 8 — Pause and code (3:25–3:50)
- Screen: approvals inbox with a Tier 3 request; cooling-off timer; wrong code refused; Demo phone panel; cancel.
- Voice-over: "Big or risky actions are Tier 3. They need a cooling-off pause and a one-time code, checked on the server.
  A wrong code is refused. Here the code appears on a simulated phone. In the demo we shorten the pause."

## Scene 9 — Proof (3:50–4:20)
- Screen: `/verify`; drop the operation-log export; green result; then show the tamper demo failing.
- Voice-over: "Every action by the AI, the user and the system is written to a log, signed and linked by hash. Anyone with
  the public key can check it in the browser, without logging in or uploading anything. If an entry is changed, the check
  fails."
- Requires: the export file from `EXECUTION_EVIDENCE.md` section 6. If it does not exist yet, use the tamper demo
  on `/app/admin/audit` and do not claim a production log. Rehearse the tamper panel first.

## Scene 10 — Results and close (4:20–4:40)
- Screen: a slide or `metrics.md` with four lines; end card with repository and live links.
- Voice-over: "On our synthetic test set of one hundred document packs, fraud checks flagged every tampered pack and no
  clean pack. Injection attacks succeeded one hundred percent of the time with defences off, and zero percent with them on.
  These are ceilings on synthetic data, not real-world accuracy. Setu: the AI explains, and code decides."
- On-screen text: "Test split · synthetic · fraud flagged 50/50, clean flagged 0/50 · injection 100% -> 0% (12 attacks)".
- End card: repository [TO FILL], live demo [TO FILL], team [TO FILL].

## Checklist before upload
- [ ] Length under 5:00 (target 4:40); file size and format accepted by the organiser [TO FILL: upload method]
- [ ] "Simulated" and "no model trained" said and shown
- [ ] Every number matches the screen and `metrics.md`
- [ ] No secrets, keys, or private dashboards in frame
- [ ] Captions or clear audio; Bangla text readable at 1080p
- [ ] Link added to README, checklist and e-mail
