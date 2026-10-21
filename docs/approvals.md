# Human approvals (SR-1, SR-2, SR-6, SR-9, Phase 5.2 / P17)

The risk engine (`docs/risk.md`) escalates; a person decides here. Tier 2 = one tap. Tier 3 = a 6-digit
code plus a cooling-off pause. Nothing in this flow is an agent tool: the LLM can only queue requests.

## Lifecycle
`PENDING -> APPROVED -> EXECUTED`, or `REJECTED | CANCELLED | EXPIRED | LOCKED | superseded (CANCELLED + superseded_by)`.
`APPROVED` means "a person said yes but the action could not run yet" (e.g. evidence missing): the buyer can tap Approve again
with no new code. Open = PENDING or APPROVED; open Tier 3 requests freeze the escrow of that buyer's deals only.

## `app/services/approvals.py`
- **Who:** the deal's buyer, or an admin. Supplier, judge or another buyer: 403 on every decision endpoint; reads of a request you cannot see are 404.
- **Approve body:** `{otp?}` only (`extra=forbid`). The action and parameters are the stored ones; the same service function that created the request
  executes it (`release_tranche`, `fund_escrow`, `lock_fx`, `confirm_milestones`, `propose_milestones`, `change_beneficiary`) with the `approval_id`,
  which re-runs the risk engine on fresh facts and re-checks the binding hash, tier, params and cooling-off.
- **Tier 3:** cooling-off first (no attempt is consumed before it ends), then the OTP. OTP = 6 digits, HMAC-SHA256 with the approval id (never stored in clear),
  5-minute life, **3 wrong codes lock the request** (status `LOCKED`, tranche thawed; a resend does not reset the counter). Resend allowed up to 5 times.
- **Re-evaluation:** if the fresh decision needs a higher tier (`APPROVAL_TIER_STALE`), nothing executes: the old request is `CANCELLED` (superseded) and the
  service opens a stricter one (`outcome: RE_ESCALATED`, `context_changed`). A BLOCK at execution closes the request.
- **Idempotent:** an `EXECUTED` request answers `EXECUTED` + `idempotent_replay` again. Release uses the idempotency key `approval-<id>`.
- **Expiry:** `expires_at = created + APPROVAL_EXPIRY_MINUTES` (1440). Lazily applied by list/get/approve/notifications (`expire_due`); closing a release request
  thaws the tranche (`release_approval_closed`), closing an account change retires the never-approved account.
- **Seeded requests** get their code, expiry and a fresh cooling-off the first time the buyer opens them (the pause starts when a person can see it).
- **Config (`app/config.py`, env):** `DEMO_MODE` (true), `COOLING_OFF_SECONDS` (600; demos 30), `APPROVAL_EXPIRY_MINUTES` (1440), `OTP_TTL_SECONDS` (300),
  `OTP_MAX_ATTEMPTS` (3), `OTP_SECRET_SEED` (HMAC key; falls back to the demo session secret).

## Simulated OTP delivery ("Demo phone")
`demo_phone_messages` holds the simulated SMS (the only place the code exists in clear). It is written, and `GET /demo/phone` answers, **only when `DEMO_MODE=true`
and `APP_ENV != prod`**, and only for the buyer's party (or an admin). With `DEMO_MODE=false` no message is stored and the endpoint is 404. No other response
carries a code (tests grep for it).

## Beneficiary change (SR-6)
- **In-app only.** Supplier portal `POST /supplier/accounts/change-request {deal_id, ...}`: account stored as `PENDING_CHANGE` (`change_requested_via='portal'`,
  opened/first seen today, number prefixed `SIM-`), KYB re-run, then `beneficiary.change_beneficiary(supplier_request=True)` creates the Tier 3 request for the buyer.
  Nothing is paid to the account until the buyer approves; approval switches only that deal's pointer and activates the account.
- **Never from e-mail.** `change_beneficiary` refuses any account with `change_requested_via='email'` (`BENEFICIARY_VIA_EMAIL`), and approving an
  e-mail-originated request is refused (it can only be rejected, which retires the pending account). The seeded HK request is exactly that case.
- **Check a suspicious e-mail:** `POST /inbox/email-check {text, deal_reference?}` (buyer/admin). `app/security/email_guard.py` is deterministic (EN/BN/ZH patterns).
  A request to pay another account = `BLOCKED`: nothing is created or changed, one FRAUD alert per email (key from the text hash), a signed
  `EMAIL_BENEFICIARY_CHANGE_BLOCKED` audit row (Tier 3, hash + codes only, never the text), a feed event. Other injected instructions = `SUSPICIOUS`
  (audit `EMAIL_INSTRUCTION_DETECTED`).

## Endpoints
`GET /approvals?status=pending|history|<STATUS>` · `GET /approvals/{id}` (with evidence snapshot) · `POST /approvals/{id}/approve|reject|cancel|resend-otp` ·
`GET /demo/phone` · `GET /notifications` · `POST /notifications/read` · `GET /deals/{id}/timeline` · `POST /inbox/email-check` · `GET /inbox/demo-email` ·
`POST /supplier/accounts/change-request` · `GET /supplier/accounts/change-requests` · `POST /demo/simulate/{redirect-email|supplier-account-change|large-advance}`.

## Storage
Migration `f1c7a3b9d204`: `approval_requests` + `context_hash, expires_at, otp_hash, otp_expires_at, otp_attempts, otp_verified_at, decision_note, superseded_by`,
status `LOCKED`; `approval_events` (feed + deal timeline; `party_id` NULL = timeline only); `demo_phone_messages`. Audit actions: `APPROVAL_APPROVED`,
`APPROVAL_EXECUTED`, `APPROVAL_REJECTED|CANCELLED|EXPIRED|LOCKED`, `APPROVAL_OTP_FAILED`, `APPROVAL_OTP_SENT`, `APPROVAL_TOO_EARLY`, `APPROVAL_REESCALATED`,
`BENEFICIARY_CHANGE_REQUESTED`, `EMAIL_*`.

## Decisions / known gaps
- Approve returns 200 with `outcome` (not an HTTP error) for `RE_ESCALATED`.
- Large-advance scam simulator is a dry run of the real engine (no deal of 22,000 is created).
- The OTP is a simulated SMS; a real SMS provider would replace `approval_otp.issue_otp`. Judges are read-only and cannot see the demo phone.
- Supplier events reach the bell only for account-change requests; there is no supplier-side OTP.
