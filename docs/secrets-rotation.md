# Secrets: what each one protects and how to rotate it

Names only; values live in the host's environment (Vercel dashboard, VPS `.env.prod`) or a password manager, never in git. In production the
agent refuses to start without the secrets marked **prod-required** (`check_prod_settings`, `backend/app/main.py`) and none of them has a
fallback value when `APP_ENV=prod`. Generate with `openssl rand -base64 48`. After any rotation: redeploy, then `GET /health` and one
sign-in plus one approval.

| Secret | Protects | What breaks when it changes | How to rotate |
|---|---|---|---|
| `DEMO_SESSION_SECRET` (prod-required, >= 32) | the signed demo "login as" cookie and sandbox cookies | demo and sandbox sessions end (judges get a new sandbox). In `AUTH_MODE=neon` real sign-ins are unaffected | set new value, redeploy |
| `OTP_SECRET_SEED` (prod-required, >= 32) | HMAC key of the Tier 3 approval codes, the step-up codes and the `X-Stepup` tokens | every code not yet used and every step-up token stops working; pending Tier 3 approvals need "resend code"; people are asked to confirm again | set new value, redeploy, tell approvers to request a new code. No data migration: only hashes of short-lived codes depend on it |
| `DOCUMENT_URL_SECRET` (prod-required, >= 32) | signed, 5-minute document download links | links already shown in open browser tabs fail until the page is reloaded | set new value, redeploy |
| `CRON_SECRET` (prod-required, >= 32) | Bearer token of the scheduler call `POST /demo/cleanup` | the scheduler gets 403 until it is updated | change in the host and in the scheduler (Vercel Cron) at the same time |
| `NEON_AUTH_COOKIE_SECRET` (web, >= 32) | session-cache cookie of the web app's `/neon-auth/*` proxy | everyone is signed out and signs in again; no data is lost | set new value on the web service, redeploy |
| `MAIL_RESEND_API_KEY` | sending the approval and step-up codes by email | codes cannot be sent: Tier 3 approvals and step-up fail with 503 "could not send the code" until fixed (existing approvals stay usable via resend) | create a new key in Resend, set it, redeploy, send a test code (resend on a pending approval), then revoke the old key |
| `AUDIT_SIGNING_KEY` | Ed25519 signature of every audit row | **do not rotate casually.** Rows signed under the old key only verify with the old public key (each row carries a `key_id`); a new key without keeping the old public key makes the chain unverifiable for the old rows | keep the old PEM with the archived export; follow `docs/deploy-prod.md` section 7 item 4. For a production chain, plan a rotation event in the audit log, never a silent swap |
| Neon Auth (the project's Auth configuration, JWKS) | identity: who is signed in | Neon rotates signing keys itself; the agent re-fetches the JWKS on an unknown `kid`. Changing the Auth URL or branch invalidates all sessions | rotate in the Neon Console (Auth), update `NEON_AUTH_BASE_URL` on agent and web together, redeploy; people sign in again |
| `DATABASE_URL` (password) | the database | the agent loses the DB (`/health` not ready) | reset in Neon, update everywhere, redeploy |
| LLM provider keys | model calls | AI answers fall back to replay or mock | create new, set, redeploy, revoke old |

## If a secret may have leaked
Rotate it first, then look for how it leaked (`git log -p`, platform logs). `.env*` is git-ignored and blocked from the coding agent by hooks. A
leaked `OTP_SECRET_SEED` lets an attacker forge step-up tokens and compute valid codes for approvals they can see the id of: rotate it at once and
review `auth.stepup` and `APPROVAL_*` audit entries since the suspected date. A leaked `MAIL_RESEND_API_KEY` allows sending mail as Setu (phishing risk): revoke at Resend.
