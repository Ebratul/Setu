# Production auth and onboarding plan (phase p24)

Decisions: **Neon Auth** for identity, **demo money now / real money later** (everything stays "Simulated" until a payment partner exists), **email OTP** for Tier 3 approvals.

Swap point: `backend/app/auth/deps.py::current_user`. Routers and services depend only on `CurrentUser`, so they stay unchanged.

## Phase A: Identity (Neon Auth)
1. Provision Neon Auth on the production Neon project (separate project/branch from demo).
2. Alembic migration on `users`: add `auth_subject` (unique, nullable for demo users), `status` (PENDING / ACTIVE / SUSPENDED), `last_login_at`, `mfa_enabled`. Keep `is_demo`.
3. `current_user`: verify the Neon Auth JWT (signature via JWKS, `exp`, `aud`, `iss`), map `sub` to `users.auth_subject`, reject PENDING/SUSPENDED with 403. Demo cookie path stays only when `DEMO_MODE=true`.
4. Mount `/auth/demo-login` and `/auth/demo-users` only when `DEMO_MODE=true`; absent in prod.
5. Frontend: `/login`, `/register`, email verification, password reset, real logout; `MeContext.tsx` reads the Neon Auth session. HttpOnly + Secure + SameSite cookies, CSRF check on mutating calls.
6. Login rate limit and lockout; audit-log every login, failure and logout.

## Phase B: Registration and onboarding
1. BUYER and SUPPLIER self-register. ADMIN is created only by invite or CLI. JUDGE is disabled in prod. The server decides `role`; the client never sends it.
2. Onboarding form: company name, trade licence, TIN/BIN, country, bank account (feeds `app/domain/kyb.py`).
3. KYB gate: new party is PENDING until KYB plus sanctions check pass, then ACTIVE. Borderline cases go to an admin review queue. No deal, financing or approval while not ACTIVE.
4. Many users per Party with party-level roles (owner / finance / viewer); replace the single `party_id` assumption in `services/scope.py`.
5. SUPPLIER flow: accept an invite, accept a deal, submit milestone evidence.

## Phase C: Approvals and money safety
1. Email OTP for Tier 3: provider (Resend or similar), only a hash stored, short expiry, attempt limit, resend throttle, delivered to the approver's verified address.
2. `otp_secret_seed` required in prod (no dev fallback). Cooling-off fixed at 600 s when `APP_ENV=prod`, not configurable below that.
3. Four-eyes: approver must differ from requester, enforced in `services/approvals.py`.
4. MFA for ADMIN and anyone approving Tier 2/3.
5. UI keeps the "Simulated" label until a real payment partner and regulatory approval exist. Real money is a separate future phase; this plan only makes it possible.

## Phase D: Config and secrets guard
1. `create_app` refuses to start with `APP_ENV=prod` unless set: auth keys/JWKS URL, `OTP_SECRET`, `DOCUMENT_URL_SECRET`, `CRON_SECRET`, `ALLOWED_ORIGINS` (exact HTTPS list).
2. Prod values: `DEMO_MODE=false`, `DEMO_REPLAY=false`, `SANDBOXES_ENABLED=false`, `DEMO_COOKIE_SECURE=true`. Add a startup check that fails if any is wrong.
3. Secrets live in Vercel/Neon env only; document rotation in `docs/deploy-prod.md`.

## Phase E: Data and tenancy
1. Separate prod and demo databases; never run the demo seed against prod.
2. Re-verify party/role scoping on every query; add cross-tenant leak tests.
3. Least-privilege DB roles (only the migration role changes schema).
4. Backups/PITR, retention and deletion policy, PII masked or encrypted.
5. Uploads: size/type limits, malware scan, private storage, signed URLs.

## Phase F: Observability and compliance
1. Alerts: failed-login spikes, Tier 3 cancellations, LLM failures and cost. Structured logs, error tracking.
2. WAF/BotID and rate limits on all public endpoints.
3. Privacy policy, terms, consent; review Bangladesh data-protection and fintech rules before real money.
4. Re-run injection and PII evals under prod settings (`make eval`).

## Phase G: Tests and release
1. New tests: auth bypass, role escalation, forged/expired token, cross-party read/write, deal before KYB, OTP replay/expiry/attempt limit, requester = approver.
2. Run `security-reviewer` on diffs in `app/auth`, `app/security`, approvals, escrow.
3. Staging first, then production with a rolling release. Update `docs/deploy-prod.md` and `docs/PROGRESS.md`.

## Order
A, then B, then C, then D (D can run in parallel with B), then E, F, G. Branch: `phase/p24-prod-auth`.

## Open items
- Email provider choice (Resend, Postmark, SES).
- Whether judges still get a demo deployment next to prod (recommended: yes, a separate deployment with `DEMO_MODE=true`).
- Neon Auth feature check: MFA support and JWKS format must be confirmed against current Neon docs before step A3.
