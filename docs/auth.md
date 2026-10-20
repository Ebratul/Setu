# Authentication (phase p24, steps A to D)

Two modes, chosen by `AUTH_MODE` on the agent (`backend/app/config.py`):

| | `demo` (default) | `neon` |
|---|---|---|
| Used by | judge deployment, tests, local dev | real accounts; **required** when `APP_ENV=prod` |
| Credential | none: pick a seeded user ("login as"), signed `setu_demo_session` cookie | Neon Auth (Managed Better Auth) JWT in `Authorization: Bearer` |
| Routes | `/auth/demo-users`, `/auth/demo-login` mounted | not mounted (404) |
| Users | `users.is_demo = true` | `users.is_demo = false`, linked by `auth_subject` |

## How a request is authenticated (neon mode)
1. The browser signs in through the same-origin proxy `/neon-auth/*` (Next route handler → Neon Auth). The session cookie lives on our domain.
2. The web app asks Neon for a 15-minute EdDSA JWT (`authClient.token()`), caches it in memory and sends it as a bearer token to the agent (`/api/*`).
3. `backend/app/auth/neon.py` verifies signature (JWKS, cached 10 min, one refetch per 15 s on an unknown `kid`), issuer, audience (both = origin of `NEON_AUTH_BASE_URL`), expiry, `sub`, and `banned`. Only `EdDSA` is accepted (no `none`, no HMAC confusion).
4. `backend/app/auth/deps.py::current_user` maps the identity to a local `users` row and enforces, in this order: `emailVerified` → account exists → `status = ACTIVE`. Failures are 403 with a stable `code`: `EMAIL_NOT_VERIFIED`, `ACCOUNT_NOT_ONBOARDED`, `ACCOUNT_PENDING`, `ACCOUNT_SUSPENDED` (401: `UNAUTHENTICATED`, `TOKEN_INVALID`; 503 if the JWKS cannot be reached and no key is cached; it never fails open).
5. Account linking: a real account created ahead of time (admin invite) is linked to the Neon `sub` on its first sign-in **only if the token's email is verified**; after that the account is pinned to that `sub`. Demo accounts are never linkable. Role and party always come from our database, never from the token.
6. Status changes (suspend) apply on the next request; there is no cached session on our side.

## Endpoints
- `GET /auth/config` → `{mode}` (public; the web app picks its login UI from this).
- `POST /auth/session` (neon): called once after sign-in; checks the account, sets `last_login_at`, writes the audit entry `auth.login` (`ok`, or `denied` with a reason). Garbage tokens get 401 and **no** audit row (so the chain cannot be flooded).
- `POST /auth/logout`: demo drops the cookie; neon records `auth.logout` (the browser ends the Neon session).
- `GET /auth/me`.
- Audit rows carry the local user id as `actor_id` (set by the app-wide `bind_actor` dependency).

## Schema
`users` gained `auth_subject` (unique), `status` (`PENDING|ACTIVE|SUSPENDED`, default `ACTIVE` so seeded users are unchanged), `last_login_at`, `mfa_enabled` (migration `e7a3c1d9b5f4`; `mfa_enabled` is set by the first successful step-up, below).

## Onboarding (phase p24, step B; neon mode)
A verified identity with no account calls `POST /onboarding`. The server creates, in one transaction, a Party (`kyb_status=PENDING`), the owner User (`status=PENDING`, role from `account_type`: BUYER or SUPPLIER only, never ADMIN/JUDGE), a `party_members` OWNER row, the bank account (`PENDING_CHANGE`) and an `onboarding_reviews` row with automatic checks from `app/domain/onboarding_kyb.py` (pure code, no LLM: sanctions screen of legal and holder names, holder-vs-legal name match, account type, country allow-list, tax-id format). Result: score and `AUTO_CLEAR | NEEDS_REVIEW | BLOCK`.
- Until approved the user gets 403 `ACCOUNT_PENDING` on everything except `GET /onboarding/status`, `/auth/session` and `/auth/logout`: no deals, approvals or analysis before KYB. A rejected user is `SUSPENDED` (403 `ACCOUNT_SUSPENDED`), party `kyb_status=FAILED`.
- Admin queue (ADMIN only; judges get 403): `GET /admin/onboarding?status=`, `GET /admin/onboarding/{id}`, `POST .../approve`, `POST .../reject {reason >= 10 chars}`. Approve activates the user, marks the party VERIFIED and the bank account ACTIVE. A decision is final (409 `ONBOARDING_DECIDED`); an admin cannot decide their own review (403 `SELF_DECISION`). Audit: `onboarding.submitted|approved|rejected|blocked` (ids only, no names or account numbers).
- Auto-approval: `ONBOARDING_AUTO_APPROVE=true` approves a clean `AUTO_CLEAR` submission at once (actor `system`). A sanctions hit (`BLOCK`) never auto-approves; the applicant is not told why (the sanctions check is hidden from `GET /onboarding/status`).
- Settings: `ONBOARDING_COUNTRIES` (default `BD,CN`), `ONBOARDING_AUTO_APPROVE` (default `false`).
- Members: `GET|POST /parties/{id}/members`, `DELETE /parties/{id}/members/{user_id}` for the party's OWNER and ADMIN. An invite pre-creates an ACTIVE account (no auth subject) that links on the invitee's first verified sign-in. Party roles: OWNER, FINANCE, VIEWER; a VIEWER is refused (403 `VIEWER_READ_ONLY`) on writes. A user with a party and no member row is treated as OWNER (seeded demo users). The last OWNER cannot be removed; a removed member is suspended and detached from the party.
- In neon mode a deal cannot use a supplier whose `kyb_status` is PENDING or FAILED (400 `SUPPLIER_NOT_VERIFIED`). Demo mode is unchanged.
- First admin: `python -m app.admin_cli create-admin --email X --name Y` (refuses when `AUTH_MODE=demo` unless `--force`).

## Web screens (phase p24, step B; neon mode)
| Route | Who | What |
|---|---|---|
| `/onboarding` | verified identity without an account | 4-step form (type and name, company, bank account, review); client rules mirror the API (BD buyer TIN of 9-13 digits), 422 shown per field, 409 codes (`ONBOARDING_EXISTS`, `EMAIL_IN_USE`, `COUNTRY_NOT_SUPPORTED`, `LICENSE_EXISTS`) as friendly messages |
| `/onboarding/status` | applicant (any account status) | review state and public checks (never sanctions or a score); refreshes every 20 s while visible and not decided; on approval calls `POST /auth/session` and routes by role; a rejection goes to `/account-status?reason=suspended`, which shows the reviewer's reason |
| `/account-status` | suspended or rejected users | explanation, rejection reason, sign out |
| `/app/admin/onboarding` | ADMIN only (nav entry hidden for others; others see a no-access state) | review queue with status tabs, detail panel (company facts, masked bank account, checks), approve (confirm) and reject (reason of at least 10 characters) |
| `/app/team`, `/supplier/team` | party OWNER (and ADMIN via the API) | members with role and "signed in once", invite (no email is sent; the invitee registers with that address), remove with confirm; `LAST_OWNER` and `PARTY_NOT_VERIFIED` explained; write controls hidden for non-owners |

After sign-in or email verification the flow sends `ACCOUNT_NOT_ONBOARDED` to `/onboarding`, `ACCOUNT_PENDING` to `/onboarding/status` and `ACCOUNT_SUSPENDED` to `/account-status`. API failures are shown through `apiErrorText` (`lib/api/formErrors.ts`), which falls back to the shared `dealErr.*` messages (including `VIEWER_READ_ONLY`).

## Approvals, step-up, four-eyes (phase p24, step C; neon mode)

**Roles on approvals.** Approve, reject, cancel and resend-code need a party member who is not a VIEWER (403 `VIEWER_READ_ONLY`, checked at the endpoint and again in the service). OWNER and FINANCE members may approve; VIEWER may read the inbox and never decide; a supplier never decides a payment. ADMIN can still decide (existing behaviour) but is not an approver for the OTP mail or the four-eyes count. Tier logic is unchanged and stays in code (`app/security`, risk engine); the LLM tool layer still reaches Tier 0/1 only.

**Tier 3 code by email.** With `AUTH_MODE=neon` the 6-digit code is emailed (plain text + HTML, English and Bangla, deal reference, action label, 5-minute expiry, "never share", "reject if unexpected") to the active OWNER and FINANCE members of the buyer party, one mail per person. VIEWERs, suspended and removed members never get one. The code appears only in the mail body: not in any API response, audit payload, approval event or log (`ConsoleSender` logs a message id and the recipient domain). It is stored as an HMAC. Attempts (3), expiry, cooling-off and hash binding are unchanged. If no mail can be sent the call fails with 503 `could not send the code`; creating a request never fails because of mail, and "resend" (max 5) recovers. The demo phone is still used when `DEMO_MODE` and not prod. Settings: `MAIL_PROVIDER` (`console` | `resend`), `MAIL_FROM`, `MAIL_RESEND_API_KEY`.

**Cooling-off.** `cooling_off_until()` never returns less than 600 s when `APP_ENV=prod`, whatever `COOLING_OFF_SECONDS` says (and startup refuses a lower value).

**Four-eyes.** `approval_requests.requested_by_user_id` is the signed-in person whose HTTP request created the approval (NULL for agent and system requests). With `FOUR_EYES_ENFORCE` (default on in neon mode, off in the demo) that person cannot approve it: 403 `FOUR_EYES`, when another active OWNER/FINANCE member of the party could. If they are the only one (a one-person company) it is allowed and the `APPROVAL_APPROVED` audit entry carries `four_eyes_waived: true`. Rejecting or cancelling your own request is always allowed.

**Step-up (email code, not TOTP).** Neon Auth has no TOTP plugin, so the second factor for sensitive actions is a fresh code emailed to the user's verified address. This proves control of the mailbox at that moment, not possession of a device, so it is weaker than an authenticator app; it still stops a stolen bearer token or an unattended session from approving money or admitting businesses. When Neon offers TOTP or passkeys, replace `app/services/stepup.py` behind the same `X-Stepup` contract.
- `POST /auth/stepup/start` (neon, signed in, active) -> `200 {"sent": true, "expires_in_seconds": 300, "starts_left": n}`. 429 `STEPUP_RATE_LIMIT` after 3 codes in 15 minutes; 503 if the mail failed (no code created). Demo mode: 404.
- `POST /auth/stepup/verify {"code": "123456"}` -> `200 {"token": "...", "expires_in_seconds": 600, "header": "X-Stepup"}`. Errors: 400 `STEPUP_INVALID` (wrong, 3 tries per code), 400 `STEPUP_NO_CODE` (none, expired or already used), 403 `STEPUP_LOCKED` (3 wrong tries; start again), 422 (not 6 digits).
- The token is `<user id>.<expiry>.<HMAC>` keyed from `OTP_SECRET_SEED`, bound to that user, valid 10 minutes. Send it as header `X-Stepup` on: `POST /admin/onboarding/{id}/approve|reject`, `POST /parties/{id}/members`, `DELETE /parties/{id}/members/{user_id}`, and `POST /approvals/{id}/approve` **for Tier 2**. Tier 3 has its own OTP and is not double-gated. Missing, malformed, expired or another user's token: 403 `STEPUP_REQUIRED`; the web app should run start/verify and retry. A non-admin calling an admin route gets the role error, not the prompt.
- First successful verify sets `users.mfa_enabled = true`. Audit `auth.stepup` (`ok` each time; `failed` deduplicated like `auth.login`), ids only.
- Switches: `STEPUP_REQUIRED` (default on in neon mode, never in the demo; `false` is refused in production).

## Production config guard (step D)
`check_prod_settings` refuses to start with `APP_ENV=prod` unless all of the following hold: neon mode with an https Auth URL; `DEMO_SESSION_SECRET`, `OTP_SECRET_SEED`, `DOCUMENT_URL_SECRET`, `CRON_SECRET` set and >= 32 chars; `DEMO_COOKIE_SECURE=true`; `DEMO_MODE=false`; cooling-off >= 600; `MAIL_PROVIDER=resend` with key and `MAIL_FROM`; `ALLOWED_ORIGINS` exact and https only; `DEMO_REPLAY`, `SANDBOXES_ENABLED`, `ENABLE_DEV_EVIDENCE`, `ONBOARDING_AUTO_APPROVE` false; `STEPUP_REQUIRED` and `FOUR_EYES_ENFORCE` not false. The OTP, demo-cookie and document-link secrets also raise in prod instead of falling back to a development value, in case the guard is bypassed. See `docs/deploy-prod.md` and `docs/secrets-rotation.md`.

## Environments and Neon branches
Neon Auth is branch-aware: each Neon branch has its own users and Auth URL.
- `production` branch: `https://ep-late-recipe-b5xcv6vj.neonauth.c-7.us-east-2.aws.neon.tech/neondb/auth` (holds the judge-deployment data; keep `AUTH_MODE=demo` there until the real launch).
- `auth-staging` branch (created from `production` for p24): `https://ep-raspy-mountain-b57daikq.neonauth.c-7.us-east-2.aws.neon.tech/neondb/auth`. Use this for development and the staging deployment.

## Neon Console settings that code cannot set (do before a real launch)
Neon Console → branch → Auth → Configuration (see Neon's "Auth production checklist"):
1. **Require email verification** (`require_email_verification`, `verify_email_on_sign_up`): currently `false` on both branches. The agent already refuses unverified emails, but turn it on so Neon blocks the sign-in itself. Method: email OTP.
2. **Trusted domains**: add the production web origin (and the Vercel preview origins you use).
3. **Allow Localhost**: switch off on the production branch.
4. **Custom SMTP** instead of the shared `auth@mail.myneon.app` sender (rate-limited).
5. Application name: "Setu".

## Environment variables
Agent: `AUTH_MODE`, `NEON_AUTH_BASE_URL`, `MAIL_PROVIDER`, `MAIL_FROM`, `MAIL_RESEND_API_KEY`, `OTP_SECRET_SEED`, `STEPUP_REQUIRED`, `FOUR_EYES_ENFORCE`. Web: `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (see `docs/deploy-prod.md`).

## Tests
`backend/tests/auth/` (token verification with a fake Neon key pair: tampering, algorithm confusion, rotation, outage; session/linking/status/audit through the real app on Postgres).
