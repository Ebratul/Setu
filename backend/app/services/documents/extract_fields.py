"""Step 2: fields. The deterministic label parser runs first; a model fills only the required
fields the parser could not read (never overwrites a parsed value), through app/llm/client.py
with the document text wrapped as untrusted data. Every value is validated in code; the result
is cached by (sha256, extractor version) so a file never costs two model calls. Mock mode and
`FORENSICS_LLM_EXTRACTION=false` skip the model."""

import hashlib
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from pydantic import ConfigDict, create_model
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import LlmCache
from app.forensics.analyze import Analysis, build_view
from app.forensics.fields import EXTRACTOR_VERSION, FIELD_MODELS, REQUIRED
from app.forensics.parse_fields import DateOrder, parse_document
from app.forensics.pdf_text import PdfText
from app.forensics.validate import sanitise
from app.llm import client as llm
from app.privacy.context import use_gateway
from app.privacy.gateway import PrivacyGateway
from app.privacy.records import new_gateway, persist_calls

log = structlog.get_logger("setu.forensics.extract")

PROMPT_PATH = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "forensics_extract.md"
PROMPT_ID = "forensics-extract@2"
MAX_PROMPT_CHARS = 20_000


@dataclass(slots=True)
class FieldExtraction:
    analysis: Analysis
    llm_fields: list[str] = field(default_factory=list)
    llm_used: bool = False
    cache_hit: bool = False


def cache_key(sha256: str, doc_type: str) -> str:
    return hashlib.sha256(
        f"{EXTRACTOR_VERSION}:{PROMPT_ID}:{doc_type}:{sha256}".encode()
    ).hexdigest()


def wrap_untrusted(text: str, doc_id: str, sha256: str) -> str:
    """The text as data: NFKC-folded, format characters removed, and every `<` and `>` escaped,
    so no tag (closing or look-alike) can appear inside the payload."""
    folded = unicodedata.normalize("NFKC", text[:MAX_PROMPT_CHARS])
    folded = "".join(ch for ch in folded if unicodedata.category(ch) != "Cf")
    safe = folded.replace("<", "&lt;").replace(">", "&gt;")
    return f'<untrusted_document id="{doc_id}" sha256="{sha256}">\n{safe}\n</untrusted_document>'


def _document_uuid(doc_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(doc_id)
    except ValueError:
        return None


def _persist(db: Session, gw: PrivacyGateway, doc_id: str) -> None:
    """Keep the masked payload and counters of this check (batch = one run) for the X-ray."""
    doc_uuid = _document_uuid(doc_id)
    if doc_uuid is not None:
        persist_calls(
            db, gw, source="document", user_id=None, document_id=doc_uuid, run_id=str(uuid.uuid4())
        )


def _record_prepared(db: Session, gw: PrivacyGateway, text: str, doc_id: str) -> None:
    """No model call this time (mock mode, nothing missing, instructions found): still record
    what WOULD have been sent, masked, flagged as not sent, so the X-ray can show it."""
    if not text.strip():
        return
    gw.protect_text(text, node="extract", model=None, sent=False)
    _persist(db, gw, doc_id)


def _system_prompt() -> str:
    body = PROMPT_PATH.read_text().split("\n", 2)[2].strip()
    return body


def _fill_schema(doc_type: str, names: list[str]) -> type[Any]:
    # Wire schema: every value is a string, so a masked value (⟦AMT_1⟧) can be returned and is
    # restored by code before `sanitise` parses it into dates and decimals.
    spec = {n: (str | None, None) for n in names}
    return create_model("FillFields", __config__=ConfigDict(extra="forbid"), **spec)  # type: ignore[call-overload]


def _llm_enabled() -> bool:
    s = get_settings()
    return s.forensics_llm_extraction and not s.use_mock_llm


def extract_fields(
    db: Session,
    pdf: PdfText,
    doc_type: str,
    sha256: str,
    *,
    date_order_hint: DateOrder | None = None,
    doc_id: str = "doc",
) -> FieldExtraction:
    parsed = parse_document(pdf.visible_text, doc_type, date_order_hint=date_order_hint)
    analysis = build_view(pdf, parsed, doc_type)
    missing = [f for f in REQUIRED[doc_type] if getattr(parsed.fields, f, None) is None]
    gw = new_gateway(db)
    text = gw.defang(wrap_untrusted(pdf.visible_text, doc_id, sha256))
    if not missing or not _llm_enabled() or not pdf.visible_text.strip():
        _record_prepared(db, gw, text, doc_id)
        return FieldExtraction(analysis)
    if analysis.view.instruction_codes:  # a document that carries instructions is not sent out
        analysis.warnings.append("LLM_SKIPPED_INSTRUCTIONS")
        _record_prepared(db, gw, text, doc_id)
        return FieldExtraction(analysis)
    key = cache_key(sha256, doc_type)
    cached = db.get(LlmCache, key)
    hit = cached is not None
    if cached is not None:
        values: dict[str, Any] = dict(cached.response.get("fields", {}))
    else:
        schema = _fill_schema(doc_type, missing)
        try:
            with use_gateway(gw):
                out = llm.structured_call(
                    schema,
                    system=_system_prompt(),
                    user=text,
                    tags=["forensics", "extract"],
                )
            _persist(db, gw, doc_id)
        except Exception as exc:
            log.warning("llm_extraction_failed", error=type(exc).__name__, sha256=sha256)
            analysis.warnings.append("LLM_EXTRACTION_FAILED")
            return FieldExtraction(analysis)
        values = out.model_dump(mode="json")
        db.add(
            LlmCache(
                key=key,
                model=get_settings().model_smart[:64],
                prompt_id=PROMPT_ID,
                response={"fields": values},
            )
        )
        db.flush()
    merged: dict[str, Any] = parsed.fields.model_dump()
    clean, warnings = sanitise(doc_type, {k: v for k, v in values.items() if k in missing})
    filled = [n for n in missing if getattr(clean, n, None) is not None]
    for n in filled:
        merged[n] = getattr(clean, n)
    analysis.warnings.extend(f"LLM_{w}" for w in warnings)
    if filled:
        parsed.fields = FIELD_MODELS[doc_type].model_validate(merged)  # type: ignore[assignment]
        parsed.missing = [f for f in REQUIRED[doc_type] if getattr(parsed.fields, f, None) is None]
        analysis = build_view(pdf, parsed, doc_type)
        analysis.warnings.extend(f"LLM_{w}" for w in warnings)
        analysis.view.llm_fields = list(filled)
    return FieldExtraction(analysis, llm_fields=filled, llm_used=True, cache_hit=hit)
