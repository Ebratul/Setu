# Privacy Gateway (SR-4) — reference

Package `backend/app/privacy/`. No raw personal or sensitive financial identifier reaches the model provider or LangSmith; answers stay correct because code restores the values afterwards.

## Pieces
| File | Role |
|---|---|
| `detectors.py` | Normalises text (NFKC, Bangla/Chinese digits → ASCII, zero-width removed, spaced digits collapsed, with an index map back to the original) and finds NID, passport, phone (BD, CN), account, IBAN (mod-97), SWIFT (needs a SWIFT/BIC word), email, person names (known DB values + labelled "Account holder / Beneficiary" lines), amounts. Each hit: type, span, confidence, canonical value, `obfuscated`. Overlaps resolved by priority. |
| `vault.py` | Per-request value ↔ token (`⟦ACCT_1⟧`). In memory, `repr` shows a count, pickling raises. Same value → same token; numbering continues after tokens already present in earlier turns. |
| `gateway.py` | `mask_text / mask / mask_payload / unmask / protect / scan`, `StreamUnmasker`. `protect()` masks the messages of one LLM call, re-scans the outgoing payload (a slipped hit is counted as `leaked_count` and masked again) and keeps a `CallRecord` (masked payload + stats). |
| `records.py` | `load_known(db)` (account holders and stored account numbers), `persist_calls` → table `privacy_records`. |
| `views.py` | Segments for highlighting, the playground dry-run, X-ray helpers. |
| `eval.py` | `run_privacy_eval(split, db=None)` for P24; `uv run python -m app.privacy.eval dev`. |

## Where it is wired
- `app/agent/runner.py::start_turn` creates the gateway (in `AgentDeps.gateway`) and masks the graph input, so even the root LangSmith run holds tokens. `finish_turn` restores answer / why / notes / cards with the vault; the SSE path unmasks streamed tokens (`StreamUnmasker`).
- `app/agent/nodes.py`: `privacy_gateway` node (idempotent mask + token reservation), `router` / `agent` / `respond` call `gateway.protect(...)` before every model call, `tools` unmasks model-supplied tool arguments (tools work on real values) and masks results (`mask_payload`, money-keyed JSON values become `⟦AMT_n⟧`). Graph state and the checkpoint therefore hold only masked text; the real tool payloads live in `gateway.raw_results` for the UI cards.
- `app/llm/client.py::structured_call` (document extraction): uses the request gateway (ContextVar) and restores string values before validation. Extraction schema is now all-strings so a masked value can be returned; prompt `forensics-extract@2`.
- `app/services/documents/extract_fields.py`: records every document check. When no model call happens (mock mode, nothing missing, instructions found) the masked text that *would* be sent is stored with `sent=false`.

## Config
`PRIVACY_ENABLED` (default true), `PRIVACY_MASK_AMOUNTS` (default true; amounts in documents and money-keyed tool outputs). With amounts masked the model cannot compare or add them; the numbers it writes are tokens restored by code.

## Endpoints (`app/api/privacy.py`)
`POST /privacy/dry-run` (admin/judge, nothing stored, no model) · `GET /privacy/summary?thread_id=` · `GET /privacy/messages/{id}` · `GET /privacy/documents/{id}` (buyer/admin/judge) · `GET /privacy/admin/overview` (admin/judge: totals, by type, 14-day series, last 20 masked records, LangSmith run link).

## Storage rules
`privacy_records` stores the masked payload, masked output, counters (`masked_by_type` = tokens new in that call, so summing calls counts each protected value once), never the vault. Chat TOOL rows keep the deterministic tool output behind UI cards (history rebuilds cards from it); it is never sent to a model from there. The model-facing history is the masked checkpoint.

## Known gaps
- Tokens from earlier turns cannot be restored (the vault is gone by design): a follow-up that makes the model repeat an old token shows `[protected ACCT]`.
- Company names, addresses and goods descriptions are not treated as personal identifiers.
- No injection-classifier model call exists, so nothing to wrap there.
- Detectors are regex + validation; an unlabelled 16-digit number in free chat text is not masked (context words required for accounts/NID).
