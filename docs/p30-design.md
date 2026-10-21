# P30 design: Google sign-in, role-based onboarding, verification gate

Branch `phase/p30-google-onboarding`. Decision (user, this session): **extend Neon Auth (P24)**. The brief's
Auth.js / Prisma / `apps/web` / `services/agent` map to Neon Auth + SQLAlchemy/Alembic + `frontend/` + `backend/`.
Deviations from the brief are listed at the end and must be repeated in `docs/PROGRESS.md`.

## 1. Identity and token trust (already in place, extended)
- Google is a social provider **inside Neon Auth** (Better Auth). The browser calls
  `getAuthClient().signIn.social({ provider: "google", callbackURL })`. The Google client id/secret live in the Neon
  console, not in our env. Neon rotates sessions, handles state/PKCE/CSRF and cookies (first-party via the
  `/neon-auth` proxy).
- The API trusts only the Neon access JWT (`app/auth/neon.py`: EdDSA, JWKS, iss, aud, exp, sub). A client-sent user
  id is never read. `emailVerified != true` -> 403 `EMAIL_NOT_VERIFIED` (already so).
- One identity <-> one User: `users.auth_subject` unique. No silent merge by email: `local_user` links a *pre-created,
  non-demo, subject-less* row only (admin invite). A second Neon subject with an existing email gets 409
  `EMAIL_IN_USE`. Neon console must keep "account linking" off for unverified providers (manual step).
- `google_sub` from the brief is **not stored**: the Neon JWT carries Neon's user id, not Google's `sub`;
  `auth_subject` is the unique anchor.
- DEMO_MODE: demo login (`/auth/demo-login`, `/auth/demo-users`, the signed demo cookie) exists **only when
  `DEMO_MODE=true`**. Works next to `AUTH_MODE=neon` (bearer wins; cookie only believed when DEMO_MODE=true and no
  bearer). `APP_ENV=prod` already refuses DEMO_MODE=true; keep that. `GET /auth/config` returns
  `{mode, demo_enabled, google_enabled}`; `google_enabled` from env `GOOGLE_SIGNIN_ENABLED` (default true in neon mode).

## 2. Statuses and roles
`UserStatus` (varchar/enum, Alembic migration, existing `PENDING` -> `PENDING_VERIFICATION`):
`PENDING_PROFILE | PENDING_VERIFICATION | ACTIVE | REJECTED | SUSPENDED`. `Role` unchanged.
- `current_user` now **admits** PENDING_PROFILE and PENDING_VERIFICATION (they may read their own workspace and sample
  data). REJECTED and SUSPENDED stay 403 (`ACCOUNT_REJECTED`, `ACCOUNT_SUSPENDED`). `CurrentUser.account_status` added.
- `require_verified` (status ACTIVE, else 403 **`ACCOUNT_NOT_VERIFIED`**) is enforced on every money action, at the
  router dependency **and** in the service layer: create real deal/order, milestone propose/confirm, escrow fund,
  release, refund, FX lock, beneficiary change, financing apply/simulate-approval, approval approve/resend, member
  invite/remove, document upload on a deal. Reads stay open. Demo users are ACTIVE so nothing changes for them.
- Admin: email in `ADMIN_EMAIL_ALLOWLIST` (case-insensitive, comma list) -> role ADMIN auto-assigned, status
  PENDING_PROFILE until TOTP is enabled, then ACTIVE. No allowlist match -> `ADMIN` can never be chosen (403
  `ROLE_NOT_ALLOWED`). Admin routes need role ADMIN **and** `mfa_enabled`; destructive admin decisions additionally
  need a fresh TOTP step-up (`X-Stepup`; the existing email-code step-up also accepts a TOTP code when
  `mfa_enabled`). Judge tokens never reach admin-destructive endpoints (already `require_admin`).
- Judge: `JUDGE_INVITE_CODES` (comma list, constant-time compare, per-IP rate limit) -> role JUDGE, ACTIVE, no party,
  no money actions (existing guards). Wrong code -> 403 `INVALID_INVITE_CODE`.

## 3. Data model (SQLAlchemy models + one Alembic migration; Prisma not used: CLAUDE.md rule 8)
`users` add: `email_verified_at`, `mfa_secret_encrypted` (bytea), `terms_accepted_at`, `privacy_accepted_at`,
`terms_version`, `deleted_at`, `auth_provider` (nullable str, informational). (`mfa_enabled`, `last_login_at`,
`auth_subject` exist.)
- `onboarding_profiles`: id, user_id (unique), role, step (smallint, furthest completed), `data` jsonb (**non-sensitive
  and masked values only**), `secure` bytea (Fernet-encrypted JSON of the sensitive values), submitted_at,
  reviewed_by, reviewed_at, review_notes, decision (`APPROVED|CHANGES_REQUESTED|REJECTED|SUSPENDED|null`),
  `change_requests` jsonb `[{target, note}]`, `revision` int.
- `verification_documents`: id, user_id, profile_id, type (`TRADE_LICENSE|IRC|TIN_CERT|BUSINESS_LICENSE|BANK_PROOF|OTHER`),
  storage_key (private), original_name (sanitised), mime, size, sha256 (indexed), status (`UPLOADED|VERIFIED|REJECTED`),
  reviewer_notes, created_at.
- `phone_verifications`: id, user_id, phone_masked, phone_hash (HMAC), code_hash (HMAC, single-use), expires_at (5 min),
  attempts, send_count window, verified_at, created_at.
- `parties` add: `dedupe_key` (HMAC-SHA256 of the normalised trade licence no. for buyers / USCC for suppliers),
  with a **partial unique index** `(kind, dedupe_key) WHERE dedupe_key IS NOT NULL`. A collision never auto-merges:
  the second submission is accepted into review with a FAIL/WARN `DUPLICATE_COMPANY` check naming the earlier party id
  only to admins; the applicant sees "needs manual review". (So the DB constraint applies to *approved* parties:
  `dedupe_key` is set on the party when ACTIVE; before that it lives on the profile in `data.dedupe_key_hmac`.)
- `onboarding_reviews` (P24) kept: extra checks go into its `checks` JSON.
- Encryption: `app/security/crypto.py`, Fernet via `FIELD_ENCRYPTION_KEY` (comma list = MultiFernet rotation).
  Missing key: dev derives a key from `DEMO_SESSION_SECRET` with a warning; `APP_ENV=prod` refuses to start. API
  responses carry masked values only (`01*******89`, `****1234`). `reveal` (admin) returns one field once, requires a
  reason (>=10 chars), writes an audit entry (field name + reason, never the value).
- Privacy Gateway: add detectors/masks for BD mobile, trade licence/IRC/TIN, USCC so they never reach the LLM; add to
  the gateway tests. No PII in logs/traces.

## 4. API contract (all JSON; identity-only unless noted; every route rate-limited and audited)
Onboarding (`/onboarding`, caller = Neon identity or PENDING user; **the server picks role/status**):
| Route | Body -> Result |
|---|---|
| `GET /onboarding/me` | -> `OnboardingState` (below). 200 with `account_status: null` if no local user yet. |
| `POST /onboarding/role` | `{role: BUYER\|SUPPLIER\|ADMIN\|JUDGE, invite_code?}` -> state. Creates the user (PENDING_PROFILE). Allowlisted email: role forced ADMIN. Idempotent for the same role; changing role after step 1 = 409. |
| `PUT /onboarding/contact` | `{full_name, designation, mobile, language}` -> state (mobile stored encrypted, phone unverified) |
| `POST /onboarding/phone/send` | -> `{sent, expires_in_seconds, sends_left, demo_code?}`; `demo_code` **only if DEMO_MODE=true**. 3 sends/10 min -> 429 `OTP_RATE_LIMIT` |
| `POST /onboarding/phone/verify` | `{code}` -> state. 5 wrong -> 423 `OTP_LOCKED`; expired -> 410 `OTP_EXPIRED`; single use |
| `PUT /onboarding/business` | role-specific body (below) -> state |
| `POST /onboarding/documents` | multipart `type`, `file` -> `DocumentOut` (P14 upload security; 4 MB; pdf/png/jpg) |
| `DELETE /onboarding/documents/{id}` | only while PENDING_PROFILE or CHANGES_REQUESTED |
| `GET /onboarding/documents/{id}/url` | signed, short-lived, owner or admin |
| `PUT /onboarding/consent` | `{terms_version, accept_terms, accept_privacy, consent_verification}` all true -> state |
| `POST /onboarding/submit` | requires steps 1-4 complete (phone verified, required docs, consent; admin: TOTP) -> state with `account_status=PENDING_VERIFICATION`; runs automated checks |
| `POST /onboarding/sample-data` | ACTIVE buyer only; loads sample deals into their own party (stretch: defer + report if not cheap) |
TOTP (`/auth/mfa/totp`): `POST /setup` -> `{otpauth_uri, secret_masked?, secret}` (secret shown once), `POST /enable {code}` -> recovery codes (10, shown once,
stored hashed), `POST /disable {code}` (not allowed for ADMIN), `POST /recovery-codes/regenerate {code}`.
Admin review (keep `/admin/onboarding`, new actions): list (filter status/role), detail (masked), `POST /{id}/reveal {field, reason}`,
`/approve`, `/request-changes {items:[{target, note}]}` (target = field key or document type), `/reject {reason}`,
`/suspend {reason}`, `/auto-approve` (404 unless DEMO_MODE=true). Decisions write signed audit + an in-app notification;
mail via the existing `app/services/mail.py` provider (optional). A reviewer cannot decide their own account.
Account: `GET /account` (profile, masked, linked provider, language, mfa, terms version), `PATCH /account {language, full_name}`,
`GET /account/export` (JSON of the caller's own data, masked), `POST /account/delete-request` (soft delete: `deleted_at`, status SUSPENDED, audit).
Sessions list/revoke use the Neon SDK in the browser; the API records `auth.session_revoked`.

`OnboardingState`: `{account_status, role, step, steps:[{key, done}], contact:{full_name, designation, mobile_masked, phone_verified, language},
business:{...masked}, documents:[DocumentOut], consent:{terms_version, accepted_at}, mfa:{enabled, required}, checks:[PublicCheck],
submitted_at, decision, change_requests:[{target, note}], terms_version, demo_mode}`.

Role-specific business bodies (server-validated with pydantic, `extra="forbid"`, friendly error `code`s per field):
- BUYER: `legal_name, trade_name?, trade_license_no, license_authority, license_expiry (future date), irc_no, tin, address{division,district,upazila,street}, business_type (MANUFACTURER|TRADER), main_import_goods, monthly_import_volume (range enum)`.
  Patterns configurable by env regex: `BD_TRADE_LICENSE_REGEX`, `BD_IRC_REGEX`, `BD_TIN_REGEX` (sane defaults); mobile `^\+8801[3-9]\d{8}$`.
- SUPPLIER: `legal_name_en, legal_name_zh, uscc (18 chars, GB 32100-2015 checksum), address{province,city,district,street?}, business_scope, export_experience_years, wechat_id?, contact_phone?, bank{bank_name, holder_name, account_no, currency CNY|USD, swift}`.
  USCC: alphabet `0123456789ABCDEFGHJKLMNPQRTUWXY`, weights `1,3,9,27,19,26,16,17,20,29,25,13,8,24,10,30,28`, check = `(31 - sum(w*idx) % 31) % 31`.
Required docs: buyer TRADE_LICENSE + IRC (TIN_CERT optional); supplier BUSINESS_LICENSE + BANK_PROOF.

## 5. Automated checks (on submit, stored in `onboarding_reviews.checks`, PASS/WARN/FAIL)
`DUPLICATE_COMPANY` (flag, never merge), `SANCTIONS_SCREEN` (P12 mock list on company + contact names; hit -> FAIL, recommendation BLOCK, hidden from
applicant), supplier `KYB_HOLDER_NAME` (licence/legal name vs bank holder), `KYB_ACCOUNT_TYPE`, `KYB_COUNTRY`, `DOC_HASH_REUSE` (same sha256 on
another account -> FAIL), `DOC_PRESENT`, optional `DOC_TEXT_MATCH` (P14 extractor, WARN only), `PHONE_VERIFIED`, `LICENSE_EXPIRY`. Reuse
`app/domain/onboarding_kyb.py`. Production: a human always approves; `ONBOARDING_AUTO_APPROVE` stays off; "Auto-approve (demo)" only when DEMO_MODE=true.

## 6. Rate limits and audit
`app/api/ratelimit.py` buckets for: auth session/callback, role/invite code (per IP), phone send (3/10 min per user), phone verify (5 attempts per code),
document upload (10/hour), submit (5/hour), reveal. Audit actions (signed chain, via `write_audit`): `auth.login`, `auth.login_denied`, `auth.logout`,
`onboarding.role_selected`, `onboarding.phone_sent|phone_verified|phone_failed`, `onboarding.profile_saved`, `onboarding.document_uploaded`,
`onboarding.submitted`, `onboarding.decision` (approve/changes/reject/suspend), `onboarding.reveal`, `auth.mfa_enabled|mfa_disabled`, `auth.session_revoked`,
`account.export`, `account.delete_requested`. Params carry ids/field names only, never PII values.

## 7. Frontend (`frontend/`)
- `/login`: primary **Continue with Google** (official button look: white/dark button, multicolour "G", "Continue with Google"), email/password stays as
  secondary; "Demo accounts" list only when `/auth/config.demo_enabled`; links to the "Why we ask for business documents" explainer, Terms, Privacy.
- `/onboarding`: resumable 6-step wizard (0 role, 1 contact + OTP, 2 business, 3 documents, 4 security + consent + TOTP, 5 review + submit),
  state from `GET /onboarding/me`, autosave per step, zod-style client validation mirroring the server, server errors mapped to fields, EN/BN everywhere,
  ZH for supplier fields and the supplier path. Replaces the P24 single form.
- `/onboarding/status`: "Verification in progress" checklist; change-requests list with per-field / per-document fix links and resubmit; REJECTED/SUSPENDED text.
- App-wide **verification banner** until ACTIVE (what is locked and why); money buttons disabled with the reason; 403 `ACCOUNT_NOT_VERIFIED` handled.
- On ACTIVE first visit: welcome, guided first-order tour, "Load sample data".
- `/admin/verifications` (queue + detail, masked by default, reveal with reason dialog, documents viewer, check results, actions Approve / Request changes /
  Reject / Suspend with required reason, demo auto-approve switch). Replaces the P24 queue page; keep old route as redirect.
- `/app/settings/account` (and supplier equivalent): profile, linked Google account, language, 2FA management, active sessions with sign-out, download my data,
  request deletion.
- CSP (`next.config.ts`): allow only what Google sign-in needs (`accounts.google.com` for navigation/form-action, `lh3.googleusercontent.com` for the avatar if shown).
- All strings in `src/i18n/parts/*.{en,bn,zh}.json`; `pnpm i18n:check` must pass; `/docs` pages updated (see section 8).

## 8. Docs
Documentation Center pages (EN + BN, ZH for the supplier one) under `frontend/content/docs/<lang>/`: "Creating your account", "Buyer verification
requirements", "Supplier verification requirements (中文)", "Why Setu asks for these details", "Admin: reviewing verifications"; register them in the
route map so `pnpm docs:check` passes. README: Google OAuth set-up (consent screen, scopes openid/email/profile, redirect URIs for localhost and production,
publishing status) **via the Neon Auth console**; env names only.

## 9. Env names (names only in `.env.example`)
Backend: `DEMO_MODE`, `AUTH_MODE`, `NEON_AUTH_BASE_URL`, `ADMIN_EMAIL_ALLOWLIST`, `JUDGE_INVITE_CODES`, `FIELD_ENCRYPTION_KEY`, `TERMS_VERSION`,
`GOOGLE_SIGNIN_ENABLED`, `SMS_PROVIDER` (`console`), `BD_TRADE_LICENSE_REGEX`, `BD_IRC_REGEX`, `BD_TIN_REGEX`, `PHONE_HASH_SECRET` (falls back to `OTP_SECRET_SEED`).
Frontend: `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET` (existing). Brief names not used with Neon Auth: `AUTH_SECRET`, `AUTH_GOOGLE_ID`,
`AUTH_GOOGLE_SECRET`, `AUTH_URL` (Google id/secret are set in the Neon console; session lifetime is a Neon Auth setting).

## 10. Deviations from the brief (record in PROGRESS.md)
Neon Auth instead of Auth.js; no Prisma; no `google_sub` column; session lifetime/rotation/sign-out-everywhere are Neon Auth features, not our code; the
token the API verifies is Neon's JWT, not a web-minted one; Google OAuth credentials live in the Neon console.
