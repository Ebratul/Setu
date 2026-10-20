# P30 API shapes (backend as implemented)

Mirror of the FastAPI models in `backend/app/schemas/onboarding.py` (source of truth: `make types`).
All JSON, `extra="forbid"` on every request. Errors are RFC 7807 problem JSON:
`{type, title, status, detail, code?, errors?}`; `errors` only on 422 `VALIDATION_FAILED`:
`[{field: "address.district", code: "required|too_short|invalid_format|not_allowed|invalid_choice|invalid_date|<CUSTOM>", message}]`.

Custom field codes: `INVALID_BD_MOBILE`, `INVALID_TRADE_LICENSE`, `INVALID_IRC`, `INVALID_TIN`, `LICENSE_EXPIRED`,
`INVALID_USCC_LENGTH`, `INVALID_USCC_CHECKSUM`, `NEEDS_CHINESE_NAME`, `INVALID_SWIFT`, `INVALID_ACCOUNT_NO`.
Field names are the request keys, nested with dots (`bank.swift`, `address.city`). Unknown keys -> `not_allowed`.
Other 422 codes: `STEP_INCOMPLETE` (errors lists missing step keys: contact|business|documents|security),
`MFA_REQUIRED` (admin submit), `ROLE_MISMATCH` (business body of the other role).

## Auth

| Route | Notes |
|---|---|
| `GET /auth/config` | `{mode: "demo"|"neon", demo_enabled: bool, google_enabled: bool}`. `demo_enabled` = the demo login exists (AUTH_MODE=demo + DEMO_MODE, or neon + DEMO_MODE + DEMO_COOKIE_IN_NEON): show the "Demo accounts" list only then. `OnboardingState.demo_mode` is separate (DEMO_MODE: `demo_code` echo and the auto-approve button) |
| `GET /auth/me`, demo login/users | now also carry `account_status` and `mfa_enabled` (`DemoUserOut`) |
| `POST /auth/session` | after Neon sign-in; PENDING_* accounts are admitted (200). 403 `ACCOUNT_NOT_ONBOARDED` (no account yet -> go to `/onboarding`), `ACCOUNT_REJECTED`, `ACCOUNT_SUSPENDED` |
| `POST /auth/session/revoked` | body `{scope: "one"|"others"|"all"}` -> 204; records `auth.session_revoked` after the browser revoked Neon sessions |
| `POST /auth/mfa/totp/setup` | -> `{otpauth_uri, secret}` (secret shown once) |
| `POST /auth/mfa/totp/enable` | `{code}` (6 digits) -> `{recovery_codes: string[10], mfa_enabled: true}` (shown once). 400 `MFA_INVALID_CODE`, `MFA_NOT_STARTED`; 409 `MFA_ALREADY_ENABLED` |
| `POST /auth/mfa/totp/disable` | `{code}` TOTP or recovery code -> `{mfa_enabled: false}`; 403 `MFA_REQUIRED` for ADMIN |
| `POST /auth/mfa/totp/recovery-codes/regenerate` | `{code}` TOTP or recovery code -> `{recovery_codes, mfa_enabled: true}` |
| `POST /auth/stepup/verify` | `{code}` now also takes a TOTP code or a recovery code (`ABCDE-FGHJK`) once TOTP is on |

Stricter than the design: with `AUTH_MODE=neon` the demo login routes, the demo cookie and the MFA-exempt seeded demo admin do not exist
(even with `DEMO_MODE=true`) unless the staging-only flag `DEMO_COOKIE_IN_NEON=true` is set (refused in prod); a demo admin is never MFA-exempt in neon mode.
An ADMIN who is not ACTIVE with TOTP on gets `403 MFA_REQUIRED` on every route except `/auth/*`, `/account`, `/onboarding/*`.
Admin decisions (`approve|request-changes|reject|suspend|auto-approve`) need `X-Stepup` from a TOTP or recovery code: a token from the emailed code gives `403 STEPUP_TOTP_REQUIRED`.
`mfa_enabled` everywhere means "flag set AND secret stored" (legacy flags from the old email step-up were reset by the migration).

Every TOTP route is neon-mode only (404 for demo users); 429 `RATE_LIMITED` after 10 tries / 10 min.

## Onboarding (caller = Neon bearer, server picks role and status)

`OnboardingState` (returned by almost every route):
```json
{
  "account_status": "PENDING_PROFILE|PENDING_VERIFICATION|ACTIVE|REJECTED|SUSPENDED|null",
  "role": "BUYER|SUPPLIER|ADMIN|JUDGE|null",
  "step": 0,
  "steps": [{"key": "role|contact|business|documents|security|review", "done": true}],
  "contact": {"full_name": "", "designation": "", "mobile_masked": "01*******78", "phone_verified": false, "language": "en|bn|zh"},
  "business": {"...masked fields, see below": null},
  "documents": [{"id": "uuid", "type": "TRADE_LICENSE", "original_name": "doc.pdf", "mime": "application/pdf", "size": 123, "status": "UPLOADED|VERIFIED|REJECTED", "reviewer_notes": null, "created_at": "iso"}],
  "consent": {"terms_version": "2026-10", "accepted_at": "iso"},
  "mfa": {"enabled": false, "required": false},
  "checks": [{"code": "PHONE_VERIFIED", "status": "PASS|WARN|FAIL", "detail": ""}],
  "submitted_at": "iso|null",
  "decision": "APPROVED|CHANGES_REQUESTED|REJECTED|SUSPENDED|null",
  "change_requests": [{"target": "tin|IRC|...", "note": ""}],
  "terms_version": "2026-10",
  "demo_mode": true
}
```
`step` = index of the first unfinished entry of `steps` (6 = all done). `contact/business/consent` are `null` until saved.
`checks` never contains `SANCTIONS_SCREEN`; `DUPLICATE_COMPANY` and `DOC_HASH_REUSE` show detail `"needs manual review"`.
`ADMIN`: contact is optional, `security` is done when consent is saved and TOTP is on; `JUDGE`: every step done.

Masked `business` echo (never full numbers):
- BUYER: `legal_name, trade_name, trade_license_no_masked, license_authority, license_expiry (YYYY-MM-DD), irc_no_masked, tin_masked, address{division,district,upazila,street}, business_type, main_import_goods, monthly_import_volume`
- SUPPLIER: `legal_name_en, legal_name_zh, uscc_masked, address{province,city,district,street|null}, business_scope, export_experience_years, wechat_id|null, contact_phone_masked|null, bank{bank_name, holder_name, account_masked, currency, swift}`

| Route | Body -> result |
|---|---|
| `GET /onboarding/me` | -> state (200, `account_status: null` before a role). Works for REJECTED/SUSPENDED so the status page can explain; 403 `ACCOUNT_SUSPENDED` only after a delete request |
| `POST /onboarding/role` | `{role: "BUYER"|"SUPPLIER"|"ADMIN"|"JUDGE", invite_code?: string}` -> state. 403 `ROLE_NOT_ALLOWED` (ADMIN, not allowlisted), 403 `INVALID_INVITE_CODE`, 409 `ROLE_LOCKED` (contact/business already saved, or submitted), 409 `EMAIL_IN_USE`, 429 `RATE_LIMITED` (10 / 10 min per IP and per identity, for JUDGE/ADMIN attempts). Allowlisted email is forced to ADMIN; JUDGE is ACTIVE at once |
| `PUT /onboarding/contact` | `{full_name 2-120, designation 2-80, mobile, language}` -> state. `mobile` accepts `01712345678`, `+8801712345678`, `8801712345678` (normalised, `^\+8801[3-9]\d{8}$`) |
| `POST /onboarding/phone/send` | -> `{sent: true, expires_in_seconds: 300, sends_left: 0-2, demo_code: string|null}`; `demo_code` non-null only when `demo_mode`. 429 `OTP_RATE_LIMIT`, 409 `MOBILE_REQUIRED`, 503 `SMS_UNAVAILABLE` |
| `POST /onboarding/phone/verify` | `{code: "6 digits"}` -> state. 400 `OTP_INVALID` ("n tries left") / `OTP_NOT_SENT`, 410 `OTP_EXPIRED`, 423 `OTP_LOCKED` (5th wrong code and after) |
| `PUT /onboarding/business` | BUYER body or SUPPLIER body (below) -> state |
| `POST /onboarding/documents` | multipart `type` (`TRADE_LICENSE|IRC|TIN_CERT|BUSINESS_LICENSE|BANK_PROOF|OTHER`), `file` (pdf/png/jpg, <= 4 MB) -> 201 `DocumentOut`. 415 `UNSUPPORTED_FILE_TYPE`, 413 `FILE_TOO_LARGE`, 403 `DOC_TYPE_NOT_ALLOWED` (buyer: TRADE_LICENSE/IRC/TIN_CERT/OTHER; supplier: BUSINESS_LICENSE/BANK_PROOF/OTHER), 409 `TOO_MANY_DOCUMENTS`; same bytes+type twice returns the existing document; 10/hour |
| `DELETE /onboarding/documents/{id}` | 204; 404 if not yours |
| `GET /onboarding/documents/{id}/url` | -> `{url: "/onboarding/documents/{id}/file?token=...", expires_at: epochSeconds}` (owner or admin; ~5 min). Open `url` with the same bearer header (attachment download) |
| `PUT /onboarding/consent` | `{terms_version, accept_terms: true, accept_privacy: true, consent_verification: true}` -> state. 409 `TERMS_VERSION_MISMATCH` |
| `POST /onboarding/submit` | no body -> state with `account_status: PENDING_VERIFICATION` (admin: ACTIVE). 422 `STEP_INCOMPLETE`; 5 / hour |

Everything that edits (contact, phone, business, documents, consent, submit) returns 409 `PROFILE_LOCKED` unless `account_status`
is `PENDING_PROFILE` (after "request changes" the account returns to `PENDING_PROFILE` with `decision: CHANGES_REQUESTED`
and `change_requests` filled; resubmit clears them).

Not implemented: `POST /onboarding/sample-data` (no sandbox seeding for a user's own party exists; see report).

### BUYER business body
```json
{"legal_name": "", "trade_name": null, "trade_license_no": "", "license_authority": "", "license_expiry": "YYYY-MM-DD",
 "irc_no": "", "tin": "", "address": {"division": "", "district": "", "upazila": "", "street": ""},
 "business_type": "MANUFACTURER|TRADER", "main_import_goods": "",
 "monthly_import_volume": "UNDER_500K_BDT|500K_2M_BDT|2M_10M_BDT|OVER_10M_BDT"}
```
Formats come from `BD_TRADE_LICENSE_REGEX`, `BD_IRC_REGEX`, `BD_TIN_REGEX` (defaults: licence/IRC 5-32 chars `A-Z0-9/-`, TIN 9-13 digits); licence must not be expired.

### SUPPLIER business body
```json
{"legal_name_en": "", "legal_name_zh": "(needs a Chinese character)", "uscc": "18 chars, GB 32100-2015 checksum",
 "address": {"province": "", "city": "", "district": "", "street": null}, "business_scope": "",
 "export_experience_years": 0, "wechat_id": null, "contact_phone": null,
 "bank": {"bank_name": "", "holder_name": "", "account_no": "6-34 alnum", "currency": "CNY|USD", "swift": "8 or 11 chars"}}
```

## Admin review (`/admin/onboarding`, ADMIN + TOTP on; decisions also need `X-Stepup`)

`ReviewOut` (list item and detail):
```json
{"id": "review uuid", "status": "PENDING|APPROVED|REJECTED|CHANGES_REQUESTED|SUSPENDED", "recommendation": "AUTO_CLEAR|NEEDS_REVIEW|BLOCK",
 "risk_summary": "PASS|WARN|FAIL", "score": 0, "role": "BUYER|SUPPLIER", "account_status": "...", "decision": "...|null", "revision": 1,
 "user_id": "uuid", "user_email": "", "user_display_name": "",
 "party": {"id": "", "kind": "BUYER|SUPPLIER|LENDER", "legal_name": "", "license_name": null, "license_no": "****1234", "tax_id": "****9012|null", "city": "", "country": "", "kyb_status": "..."},
 "bank_account": {"bank_name": "", "bank_country": "", "account_masked": "****7890", "holder_name": "", "account_type": "CORPORATE|PERSONAL", "currency": "", "status": "PENDING_CHANGE|ACTIVE|RETIRED"} ,
 "contact": "ContactOut|null", "business": "masked echo|null", "documents": ["DocumentOut"],
 "change_requests": [{"target": "", "note": ""}],
 "checks": [{"code": "", "status": "PASS|WARN|FAIL", "detail": ""}],
 "submitted_at": "iso", "decided_at": "iso|null", "decided_by": "uuid|null", "reason": "string|null"}
```
Check codes: `SANCTIONS_SCREEN, DUPLICATE_COMPANY, DOC_PRESENT, DOC_HASH_REUSE, PHONE_VERIFIED, LICENSE_EXPIRY` (buyer),
`KYB_HOLDER_NAME, KYB_ACCOUNT_TYPE, KYB_COUNTRY` (supplier). `DOC_TEXT_MATCH` (optional) is not implemented.

| Route | Body -> result |
|---|---|
| `GET /admin/onboarding?status=&role=` | -> `{items: ReviewOut[]}` (newest first, max 200) |
| `GET /admin/onboarding/{id}` | -> `ReviewOut` |
| `POST /admin/onboarding/{id}/reveal` | `{field: "mobile|trade_license_no|irc_no|tin|uscc|bank_account_no", reason (10-300 chars)}` -> `{field, value}`; audited (field + reason, never the value); 30 / hour |
| `POST .../approve` | no body -> `ReviewOut`. 409 `SANCTIONS_BLOCK`, 409 `DUPLICATE_COMPANY_APPROVED`, 409 `ONBOARDING_DECIDED` |
| `POST .../request-changes` | `{items: [{target (field key or document type, <= 64 chars), note (3-500)}]}` (1-20) -> `ReviewOut` |
| `POST .../reject` | `{reason (10-500)}` -> `ReviewOut` |
| `POST .../suspend` (terminal: review status becomes `SUSPENDED` and leaves the PENDING queue; later approve / request-changes / suspend -> 409; the user cannot resubmit) | `{reason (10-500)}` -> `ReviewOut` (business accounts only; 409 `ROLE_NOT_REVIEWABLE`) |
| `POST .../auto-approve` | no body; 404 unless `demo_mode` |

Errors: 403 `MFA_REQUIRED` (admin without TOTP), 403 `STEPUP_REQUIRED` (decisions), 403 `SELF_DECISION`, 403 for judges/buyers.
Decisions notify the applicant: `GET /notifications` item with `kind: "ONBOARDING"`, plus an email when mail is configured.

## Account

| Route | Body -> result |
|---|---|
| `GET /account` | -> `{id, email, display_name, role, language, account_status, auth_provider ("neon"), mfa_enabled, terms_version, terms_accepted_at, party_name, mobile_masked, created_at, last_login_at}` |
| `PATCH /account` | `{language?, full_name?}` -> `AccountOut`; 404 for seeded demo users (also `POST /account/delete-request`) |
| `GET /account/export` | -> `{exported_at, account, onboarding (OnboardingState), activity: {audit_actions: string[]}, note}`; 5 / hour |
| `POST /account/delete-request` | -> `{status: "SUSPENDED", deleted_at}`; soft delete, the session is refused afterwards (403 `ACCOUNT_SUSPENDED`) |

## Money gate

Every money action returns `403 {code: "ACCOUNT_NOT_VERIFIED"}` unless `account_status == "ACTIVE"`:
`POST /deals`, `/deals/{id}/milestones/propose|confirm`, `/deals/{id}/escrow/fund`, `/deals/{id}/fx-lock`, `/deals/{id}/beneficiary`,
`/deals/{id}/refund`, `/milestones/{id}/release|refund|evidence`, `/financing/applications`, `/financing/applications/{id}/simulate-approval`,
`/approvals/{id}/approve|resend-otp`, `POST|DELETE /parties/{id}/members`, `POST /deals/{id}/documents`, `POST /supplier/accounts/change-request`.
A suspended or rejected business is frozen as a whole: its other members become SUSPENDED, the party fails KYB, and `403 ACCOUNT_SUSPENDED` is returned for money actions even if a member row is still ACTIVE.
`POST /kyb/verify/{supplier}` now needs a verified caller and a supplier that is approved and ACTIVE (409 `SUPPLIER_NOT_APPROVED`).
Reads stay open for PENDING_PROFILE / PENDING_VERIFICATION accounts. REJECTED / SUSPENDED accounts get 403 `ACCOUNT_REJECTED` / `ACCOUNT_SUSPENDED` on every authenticated route except `GET /onboarding/me` (REJECTED/SUSPENDED).

## Audit actions written
`auth.login`, `auth.login_denied`, `auth.logout`, `auth.session_revoked`, `auth.mfa_enabled`, `auth.mfa_disabled`, `auth.mfa_recovery_regenerated`,
`onboarding.role_selected`, `onboarding.phone_sent|phone_verified|phone_failed`, `onboarding.profile_saved`, `onboarding.document_uploaded|document_deleted|document_viewed`,
`onboarding.submitted`, `onboarding.blocked`, `onboarding.decision` (APPROVED / CHANGES_REQUESTED / REJECTED / SUSPENDED), `onboarding.reveal`, `account.export`, `account.delete_requested`.
