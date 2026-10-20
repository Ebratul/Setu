# Guided demo, judge sandboxes, presenter and recording modes (P21)

A judge, or our presenter, can walk the whole Setu story in about four minutes from one button, identically every time,
then explore freely in their own private sandbox. Every step calls the **real services**. All money is simulated.

## What runs

| Piece | Where | Notes |
|---|---|---|
| Script (12 steps, 27 scenes, 17 scorecard items) | `data/demo/demo_steps.yaml` | EN + BN text, presenter notes, highlight selectors. Validated at load (`app/demo/script.py`) |
| Orchestrator | `services/agent/app/demo/runner.py` | A scene's actions call the real API **in-process as the scene's user** (same routers, same permission checks), or a registered service call (`app/demo/actions.py`). Expectations are checked and stored per scene |
| Judge sandboxes | `app/demo/sandbox.py`, `app/db/tenancy.py` | One Postgres **schema** per sandbox, cloned from the seed (profile `demo`), routed by a signed cookie |
| LLM replay | `app/llm/replay.py` | Fixtures keyed by hash of the masked prompt + model: identical answers, works offline |
| Pre-flight | `app/demo/preflight.py`, `GET /demo/preflight` | Green/red list |
| CLI | `pnpm demo:run \| demo:check \| demo:record \| demo:cleanup` | See below |
| UI | `/demo` (landing), `/demo/run` (split screen) | `apps/web/src/components/demo/` |

## The story (matches the brief; see the YAML for exact text)

1 Rahima asks in Bangla (chat streams a Bangla answer with cards) · 2 KYB: Huaxin green, Huameng as contrast · 3 landed
cost USD 11,200, margin 18% · 4 cash-flow shows the USD 1,560 shortfall, financing compared, applied (simulated), the
shortfall alert resolves · 5 milestones 30/60/10 confirmed by both sides (buyer view, then supplier view) · 6 escrow
holds M1, Tier 2 one-tap release, paid in CNY with the FX saving · 7 production photos pass the spec check · 8 fake
"new Hong Kong account" email blocked, FRAUD alert, then the legitimate portal path becomes Tier 3 (cooling-off, wrong OTP
refused, cancelled) · 9 **WOW A** forged B/L: FAILED, hidden instruction revealed, rule trace shows Tier 3, chat says the
instruction was ignored · 10 **WOW B** the same invoice at Lender B: duplicate blocked · 11 admin closes the incident,
clean B/L + packing list + invoice pass, FX lock, **M2 released at Tier 1**, duty USD 800 and bill-of-entry alerts ·
12 bill of entry, final 10% released, **signed credit record**, audit chain verifies.

### Deliberate deviations from the brief (honest notes)

* **Step 4 loan.** The escrow-backed order loan (Lender B) is *blocked* on this deal on purpose: the invoice is already
  collateral at Lender A (P15). Step 4 therefore applies for the best *eligible* option (supplier credit, 60 days), for the
  peak gap USD 2,160 so the whole dip is covered. The blocked option is shown with its reason and sets up step 10.
* **Step 5 schedule.** The seeded deal already has its schedule confirmed by both sides and M1 deposited (the USD 1,560
  shortfall only exists in that state), and the schedule is locked once money is in escrow. Step 5 shows that real record from
  both sides (with confirmation timestamps); the propose/confirm screens remain in Deals.
* **Step 8 Tier 3.** The seed's pre-existing "pay the HK account" Tier 3 request would freeze every release before step 8,
  so sandboxes use seed profile `demo`, which leaves it out. The step raises a real Tier 3 request through the supplier
  portal instead, tries a wrong OTP, and the buyer cancels.
* **Step 12 cash.** A labelled time skip (`DEMO_CASH_RECEIPT`, audited) credits Rahima's simulated customer payments so she can
  fund the last tranche.
* **Attacks blocked = 3** (email, forged B/L, duplicate financing), not 2.
* New real features this needed: `POST /documents/{id}/reject` (a person withdraws a forged file), the **signed credit record on
  completion** (`app/services/credit_record.py`, `GET /credit-records/{deal}`, `POST /credit-records/verify`; FR-8 was not wired
  before), and a prompt rule for privacy tokens (without it the model refused to quote masked amounts).

## Sandboxes

* `POST /demo/sandbox` creates (or resumes) the judge's sandbox and sets the signed `setu_sandbox` cookie. Sandbox = Postgres
  schema `sbx_<12 hex>` with copies of every demo table; `kb_chunks`, `llm_cache`, `demo_sandboxes` stay shared in `public`.
* `app/demo/middleware.py` sets `search_path = <schema>, public` for each request (pool hook in `app/db/tenancy.py`, so
  background tasks and own-session writes are routed too). A cookie that no longer resolves gets **410 `SANDBOX_EXPIRED`**; it never
  falls back to the shared data. Advisory-lock keys are per schema.
* Limits (env): `SANDBOX_TTL_HOURS` (4), `SANDBOX_MAX_ACTIVE` (40, then 503 `SANDBOX_CAPACITY`),
  `SANDBOX_REQUESTS_PER_MINUTE` (600), `SANDBOX_CHAT_PER_MINUTE` (12), `SANDBOX_UPLOAD_PER_MINUTE` (12) → 429
  `SANDBOX_RATE_LIMIT` (in-memory per instance).
* Cleanup: `pnpm demo:cleanup`, lazily on every create, or `POST /demo/cleanup` with `Authorization: Bearer $CRON_SECRET`
  (point a scheduler at it).
* Reset (`POST /demo/run/reset`): drops and rebuilds **only that schema**, appends a signed `DEMO_RESET` (with the previous
  chain head) to the new audit chain, clears threads, approvals, notifications and run state. `seed.verify` (profile
  `demo`) passes on the result. Nothing runs an unqualified TRUNCATE.
* "Use live AI": `POST /demo/sandbox/live-ai {enabled}`; needs a server key; budget `SANDBOX_LIVE_AI_BUDGET` (25 model
  calls) then it falls back to replay.
* "Skip cooling-off (demo only)": `POST /demo/sandbox/skip-cooling-off` ends the pause of the sandbox's open Tier 3 requests
  (audited `DEMO_COOLING_OFF_SKIPPED`). Separately `COOLING_OFF_SECONDS=30` shortens it for local runs.

## Replay fixtures

* Mode per call (`app/llm/replay.py`): inside a sandbox: replay (default) or live; outside: `DEMO_REPLAY=true` replays, else the
  plain model. `DEMO_RECORD=true` or `pnpm demo:record` records.
* Key = sha256(kind, canonical model id, normalised messages, tool names, schema name). Normalised: UUIDs, timestamps, random
  `<untrusted id=…>` ids and call ids. Files: `data/demo/fixtures/llm/<key24>.json` + `manifest.json` (script + prompt digests).
* A miss answers with the offline deterministic model and is counted. `pnpm demo:check` runs the 12 steps in a throwaway
  sandbox in replay and **fails** on any miss, failed scene, missing fixture file or stale manifest (script or prompts
  changed → re-record).
* `pnpm demo:record` needs `OPENROUTER_API_KEY` or `ANTHROPIC_API_KEY`; it writes 7 fixtures (scene 1.1: router, agent, agent, respond;
  scene 9.3: router, agent, respond). Commit them.

## API (all under the FastAPI service; the web app calls it through `/api`)

| Method + path | Purpose |
|---|---|
| `GET /demo/steps` | The script for the UI (no actions): steps, scenes (route **templates**), highlights, captions, scorecard defs |
| `GET /demo/preflight` | `{ok, replay, items[{id,label,ok,detail}]}` |
| `POST /demo/sandbox {fresh?}` | Create or resume; sets the cookie; returns `SandboxOut` |
| `GET /demo/sandbox` · `DELETE /demo/sandbox` | Status · end now (drops the schema) |
| `POST /demo/sandbox/live-ai {enabled}` | Live-AI switch |
| `POST /demo/sandbox/skip-cooling-off` | Demo-only control |
| `GET /demo/run` | `RunOut`: sandbox, cursor, every scene result, scorecard (ticked), progress |
| `POST /demo/run/scenes/{n}/{k}/run?force=` | Run scene n.k (a passed scene is not run twice); `RunOut.last` is its `SceneResultOut` with the **resolved `route`** |
| `POST /demo/run/goto {step}` | Run every earlier scene not yet run (deep link `?step=9`, jump) |
| `POST /demo/run/reset` | Rebuild this sandbox |
| `GET /demo/run/summary` | "What you just saw": numbers, attacks, links |

Existing endpoints the UI also needs inside the sandbox: `POST /auth/demo-login {email}` (role switch; cookie), `GET /demo/phone`
(simulated SMS inbox, OTP), `GET /credit-records/{deal_ref}`.

Scene result: `status: passed|failed|pending|running`, `assertions[{label{en,bn},ok,expected,actual}]`, `facts{…}` (key numbers,
e.g. `landed_cost`, `shortfall`, `fx_saving_usd`, `hidden_text`, `tier`, `entries_verified`), `route`, `message{en,bn}` (friendly
text when a scene could not finish; never a stack trace), `error_code`, `llm{mode,fixtures_used,misses}`, `duration_ms`.
Roles for a scene: `login_as` (a demo email) and `view` (`buyer|supplier|admin|split`).

## UI contract

* `/demo` landing: three buttons (**Watch guided demo** → sandbox + `/demo/run?play=1`; **Start my own sandbox** → sandbox +
  `/app` (free exploration); **Presenter mode** → `/demo/run?mode=presenter`), the pre-flight list, a short EN/BN intro, the
  existing playground links. `/demo?step=9` redirects to `/demo/run?step=9` (deep link).
* `/demo/run`: left = the embedded real app (iframe of the scene's `route`, same origin, `?embed=1` hides the shell), right = narration,
  step list, controls, scorecard, Demo phone. Role switcher (Buyer / Supplier / Admin) and a **"Simulated sandbox – fictional
  data"** banner always visible. Navigation unit is the **scene**; a step has 1–4 scenes.
* Controls: Start, Next, Previous, jump to step, Auto-play (1× / 1.5× / 2×), Pause, Reset, language EN/BN, Use live AI,
  Skip cooling-off (demo only), End sandbox.
* Spotlight: dim the page, cut out the element matching the scene's `highlight` selector (`[data-demo="…"]`, looked up inside the
  iframe, same origin), caption bubble (EN/BN) next to it; falls back to a centred caption if the element is missing.
* Narration panel + optional read-aloud (browser `speechSynthesis`; EN, BN where a voice exists; mute toggle).
* Judge scorecard: three groups (Task completion · Security & compliance · Innovation & interaction), items tick as scenes pass,
  each links to the screen that proves it.
* "What you just saw": numbers, attacks, links to Risk Playground, Privacy Playground, Attack Console, `/verify`, **Explore freely**.
* Presenter mode (`?mode=presenter`): full screen, larger type; `→` next, `←` back, `Space` pause/play, `R` reset, `B` blackout,
  `N` notes pane (talking points per step) and a timer.
* Recording mode (`?mode=record`): clean 1920×1080 stage (scaled to fit), no cursor, step titles as lower-third captions,
  fixed steady auto-play pace, no panels.
* Mobile (< 768 px): stacked, tabs for App / Story / Score.

### `data-demo` anchors the pages must expose

`chat-answer` · `kyb-badge` · `landed-cost` · `shortfall-alert` · `financing-options` · `financing-applied` · `milestone-stepper` ·
`supplier-schedule` · `escrow-card` · `approve-button` · `settlement` · `doc-checks` · `email-verdict` · `cooling-off` ·
`otp-input` · `hidden-text` · `risk-trace` · `registry-box` · `injection-event` · `evidence-checklist` · `deadline-alerts` ·
`credit-record` · `audit-verify`.

## Tests

* `tests/demo/`: script validity, expression language, full 12-step run (27 scenes, scorecard 17/17), determinism (two runs: same
  outcomes, same fixture keys, timings within tolerance), isolation (two sandboxes at once, separate approvals, ledgers and audit
  chains), reset + `seed.verify`, middleware (410 / 429), `demo:check` fails when a fixture is missing, credit record, reject
  document.
* Playwright `apps/web/e2e/demo.spec.ts` (replay, no network).

## Known gaps

Bangla and Chinese strings are not native-reviewed; the in-memory rate limiter is per instance; sandbox cleanup needs a scheduler
(or the lazy cleanup on create); `APP_ENV=prod` requires `DEMO_MODE=false`, which switches off the simulated SMS inbox and the
scam simulator the steps use, so a judge deployment runs with `APP_ENV=dev`/`test` and `DEMO_MODE=true`.
