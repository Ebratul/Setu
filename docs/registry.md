# Hash registry (FR-6.2, SR-6, TC-05)

One trade document must not back two things: escrow evidence on two deals, or collateral at two lenders.
Code: `services/agent/app/services/hash_registry.py` (rules), `registry.py` (API logic), `api/registry.py`,
`schemas/registry.py`, table `hash_registry` (migration `d5a3f0c8b7e1`). All money and lenders are simulated.

## Fingerprints
| | how | catches |
|---|---|---|
| exact | sha256 of the file bytes | the same file |
| semantic | sha256 of folded identity fields: invoices (PI, CI) seller + invoice no. + total (2 dp) + currency (`documents.canonical_hash`, `forensics/canonical.py`); bills of lading shipper + B/L no. + vessel. Scoped by document type | a re-saved or re-scanned copy with other bytes |

Deviation from the brief: the date is **not** in the key. A re-scan that misreads the date would escape detection
and the invoice number + amount already identify the document. Photos, packing lists, certificates and bills of
entry have exact matching only.

## Entry
`sha256`, `semantic_fingerprint`, `doc_type`, `purpose` (ESCROW_EVIDENCE | FINANCING_COLLATERAL), `deal_id`,
`lender_party_id` (null for evidence), `document_id`, `registered_by_user_id`, `registered_at` (first seen),
`last_seen_at`, `seen_count`, `status` (ACTIVE | RELEASED), `released_at`, `exact_hits`, `near_hits`,
`context_key` (purpose:lender:deal; unique with sha256). The brief said "Prisma migration"; the repo uses Alembic.

## Verdicts: `evaluate(subject, context)`
`NEW`, `SAME_CONTEXT`, `EXACT_DUPLICATE`, `NEAR_DUPLICATE`, against ACTIVE entries only.
- **Conflict** = an ACTIVE entry in another context: another deal, or the same deal pledged to a different lender.
  Same deal with another purpose (evidence, then collateral) is one context. Conflicts win over a same-context entry (fail closed).
- Without a deal (an outside lender asking) only FINANCING_COLLATERAL entries count; a lender asking about its own
  collateral gets SAME_CONTEXT.
- EXACT when a conflicting entry has the same sha256, else NEAR (same fingerprint and document type).
- The earliest financing-collateral entry is the one reported (purpose, lender label, date; nothing else).

## Integrations
| where | behaviour |
|---|---|
| Upload / pipeline (`documents/pipeline.py` -> `after_document_check`) | `hash_registry.check(db, doc)` feeds `DUPLICATE_HASH`. A duplicate is FAIL: document FAILED, FRAUD alert, `duplicate_hash` reaches the risk hook (Tier 3). A document that is not FAILED is registered as ESCROW_EVIDENCE of its deal (idempotent; `seen_count` +1 on the primary re-check). A document that later FAILS keeps its entry (fail closed). Invoice family: PI and CI match each other, the uploader picks the type. A global advisory lock serialises lookup + registration. |
| Upload API | Identical bytes on another deal are no longer refused with 409 `DUPLICATE_DOCUMENT`; they are stored (`documents` is unique per `(deal_id, sha256)`) and fail the registry check. The old stopgap `platform_duplicate` is gone: the registry is the single source. |
| Financing (`services/financing.py`) | Options of kind BANK_IMPORT_LOAN and ESCROW_BACKED_LOAN take the deal's uploaded invoices as collateral. `/financing/match`: a conflicting option gets `registry_block`, `eligible=false`, never recommended. `POST /financing/applications`: 409 `INVOICE_ALREADY_FINANCED`, hit counted, Tier 3 audit row, FRAUD alert on the deal. Otherwise the invoices are registered as FINANCING_COLLATERAL with the option's lender (`external_ref` = application reference). Ineligible options fail on eligibility first; with no uploaded invoice the application is refused (400 `INVOICE_REQUIRED`). The registry lock is held across gate and registration, and `simulate_approval` re-runs the gate. |
| Deal COMPLETED / CANCELLED | `release_for_deal`: entries become RELEASED (kept, no longer block). There is no loan-repayment flow yet; `release_for_deal(..., purposes=(FINANCING_COLLATERAL,))` is the hook for it. |
| Agent | `registry_status(document_id)` Tier 0 -> `registry` card; `check_documents` items carry `registry_state` / `registry_result` and flag `REGISTRY_DUPLICATE`. Neither writes. |
| Audit (`write_audit`) | `REGISTRY_REGISTERED` (tier 0), `REGISTRY_RELEASED` (tier 0), `REGISTRY_DUPLICATE_HIT` (tier 3; source UPLOAD, FINANCING or LENDER_CHECK). A hit also increments `exact_hits` / `near_hits` on the entry it hit; counters count attempts. |

## Mock lenders
Parties of kind LENDER in the seed: **Lender A** = Meghna Commercial Bank (`meghna-commercial-bank`, holds the main
deal's PI under loan `MCB-IMPLOAN-2026-0412`), **Lender B** = Setu Partner Finance (`setu-partner-finance`), and
Shitalakshya Capital Finance PLC (NBFI). The brief called Meghna "Lender B"; the existing seed, demo README and financing
catalogue use Meghna as Lender A, so that is kept. The seed also registers the main deal's PASSED uploads as ESCROW_EVIDENCE.

## Endpoints
| | |
|---|---|
| `GET /registry?status=&result=EXACT_DUPLICATE\|NEAR_DUPLICATE&purpose=&limit=&offset=` | admin + judge. Hash prefixes (12 chars) and minimal metadata |
| `GET /registry/stats` | admin + judge. entries, active, released, by_purpose, duplicates_blocked (exact / near) |
| `POST /registry/lender-check` | admin + judge (any input); a buyer only with `document_id` of a document they can see; suppliers refused. Every query is audited (`REGISTRY_LENDER_CHECK`, hits `REGISTRY_DUPLICATE_HIT`) |
| `POST /registry/lender-check/file` | multipart `lender_id`, `file` (PDF, 10 MB, same body-limit middleware) |
| `GET /documents/{id}/registry` | buyer / admin / judge of the deal; suppliers refused |

### Lender-check contract
Request (JSON): `{lender_id, sha256}` or `{lender_id, document_id}` or `{lender_id, fields: {doc_type, seller, number, total?, currency?, vessel?}}`.
`lender_id` is a party code or id of a LENDER party (else 404). Exactly one of the three, else 400 `BAD_QUERY`.
The file variant hashes the bytes and, for a PDF titled as a PI, CI or B/L, parses it with the deterministic parser (sandboxed, no LLM).
Response: `{simulated: true, result, already_registered_for, registered_on, held_by}`. `already_registered_for` is the
purpose of the conflicting entry, `held_by` the pseudonymous lender label ("Lender A") for collateral only. Never a buyer,
price, deal reference or document text. A query never registers anything. With `document_id` of a Setu deal and a
duplicate result, a FRAUD alert is raised on that deal so the buyer and admin see the attempt.

## Privacy
Only hashes and minimal metadata are stored. `semantic_fingerprint` is a hash of folded identity fields, not the fields.
Lender-facing answers carry result, purpose, date and a pseudonymous holder label. `GET /registry` shows 12-char prefixes
and the deal reference to admin and judge only. The existence oracle (is this hash registered?) is the product; it is
limited to admin/judge (buyers: own documents), audited when it hits, and a production deployment would add per-lender
authentication, rate limits and unlinkable (salted per-lender) hashing.

## Catch rate on the synthetic DUPLICATE_INVOICE packs (dev split)
`uv run python -m app.forensics.eval_registry` registers each duplicate's source at Lender A and checks the copy as Lender B
(scratch transaction, nothing committed). Dev split, 5 packs: byte-identical 3/3 EXACT, re-saved 2/2 NEAR, 5/5 caught.
Synthetic ceiling, not real-world accuracy; test-split numbers are P24's.

## On-chain anchoring
Not built. `app/services/registry_anchor.py` holds the pure daily Merkle root and the `Anchorer` protocol (no network code,
no flag wired). Build an anchorer only if the organiser confirms the on-chain bonus applies to Topic E.

## Known gaps
Release on COMPLETED follows the brief (RELEASED entries no longer block) but means a completed deal's invoice or B/L can be reused; the security review (High) asked to keep evidence entries forever and release collateral only when the application is repaid. Left as specified until a repayment flow exists; decide in P16. The migration backfills evidence rows for existing UPLOADED, non-FAILED documents. A judge's document-based check writes counters and alerts (demo helper). No rate limit on the file endpoint. The downgrade drops evidence/null-lender rows.
No loan-repayment flow to release collateral; seeded evidence rows reset on re-seed; hit counters count attempts, not
distinct documents; lender identity in lender-check is the signed-in demo user, not a lender credential; registry rows are
hidden from suppliers entirely.
