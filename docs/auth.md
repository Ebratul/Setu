# Authentication (phase p24, step A)

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
`users` gained `auth_subject` (unique), `status` (`PENDING|ACTIVE|SUSPENDED`, default `ACTIVE` so seeded users are unchanged), `last_login_at`, `mfa_enabled` (migration `e7a3c1d9b5f4`; MFA enforcement is step C).

## Onboarding (phase p24, step B; neon mode)
A verified identity with no account calls `POST /onboarding`. The server creates, in one transaction, a Party (`kyb_status=PENDING`), the owner User (`status=PENDING`, role from `account_type`: BUYER or SUPPLIER only, never ADMIN/JUDGE), a `party_members` OWNER row, the bank account (`PENDING_CHANGE`) and an `onboarding_reviews` row with automatic checks from `app/domain/onboarding_kyb.py` (pure code, no LLM: sanctions screen of legal and holder names, holder-vs-legal name match, account type, country allow-list, tax-id format). Result: score and `AUTO_CLEAR | NEEDS_REVIEW | BLOCK`.
- Until approved the user gets 403 `ACCOUNT_PENDING` on everything except `GET /onboarding/status`, `/auth/session` and `/auth/logout`: no deals, approvals or analysis before KYB. A rejected user is `SUSPENDED` (403 `ACCOUNT_SUSPENDED`), party `kyb_status=FAILED`.
- Admin queue (ADMIN only; judges get 403): `GET /admin/onboarding?status=`, `GET /admin/onboarding/{id}`, `POST .../approve`, `POST .../reject {reason >= 10 chars}`. Approve activates the user, marks the party VERIFIED and the bank account ACTIVE. A decision is final (409 `ONBOARDING_DECIDED`); an admin cannot decide their own review (403 `SELF_DECISION`). Audit: `onboarding.submitted|approved|rejected|blocked` (ids only, no names or account numbers).
- Auto-approval: `ONBOARDING_AUTO_APPROVE=true` approves a clean `AUTO_CLEAR` submission at once (actor `system`). A sanctions hit (`BLOCK`) never auto-approves; the applicant is not told why (the sanctions check is hidden from `GET /onboarding/status`).
- Settings: `ONBOARDING_COUNTRIES` (default `BD,CN`), `ONBOARDING_AUTO_APPROVE` (default `false`).
- Members: `GET|POST /parties/{id}/members`, `DELETE /parties/{id}/members/{user_id}` for the party's OWNER and ADMIN. An invite pre-creates an ACTIVE account (no auth subject) that links on the invitee's first verified sign-in. Party roles: OWNER, FINANCE, VIEWER; a VIEWER is refused (403 `VIEWER_READ_ONLY`) on writes. A user with a party and no member row is treated as OWNER (seeded demo users). The last OWNER cannot be removed; a removed member is suspended and detached from the party.
- In neon mode a deal cannot use a supplier whose `kyb_status` is PENDING or FAILED (400 `SUPPLIER_NOT_VERIFIED`). Demo mode is unchanged.
- First admin: `python -m app.admin_cli create-admin --email X --name Y` (refuses when `AUTH_MODE=demo` unless `--force`).

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
Agent: `AUTH_MODE`, `NEON_AUTH_BASE_URL`. Web: `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (see `docs/deploy-prod.md`).

## Tests
`backend/tests/auth/` (token verification with a fake Neon key pair: tampering, algorithm confusion, rotation, outage; session/linking/status/audit through the real app on Postgres).
