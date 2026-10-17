"""bytes -> DocView: text layer, hidden spans, metadata, instruction scan and field parsing for
PDFs; dominant colour for photos. Pure and deterministic; the optional LLM step and the DB live
in app/services/documents."""

import io
from dataclasses import dataclass, field

from PIL import Image

from app.forensics.checks import nearest_colour
from app.forensics.context import DocView
from app.forensics.instructions import scan_text
from app.forensics.parse_fields import (
    DateOrder,
    ParseResult,
    parse_document,
    title_doc_type,
)
from app.forensics.pdf_text import PdfText, read_pdf

MAX_PIXELS = 20_000_000


@dataclass(slots=True)
class Analysis:
    view: DocView
    pdf: PdfText | None = None
    parsed: ParseResult | None = None
    title_type: str | None = None
    warnings: list[str] = field(default_factory=list)


def instruction_codes_of(pdf: PdfText) -> dict[str, list[str]]:
    """Instruction-like text by source (visible text, hidden text, metadata): codes only."""
    codes: dict[str, list[str]] = {}
    meta_text = "\n".join(pdf.metadata.values())  # every key, Producer and Creator included
    for source, text in (
        ("visible_text", pdf.visible_text),
        ("hidden_text", "\n".join(s.text for s in pdf.hidden_spans)),
        ("metadata", meta_text),
    ):
        found = sorted({f.code for f in scan_text(text)})
        if found:
            codes[source] = found
    return codes


def build_view(pdf: PdfText, parsed: ParseResult, doc_type: str) -> Analysis:
    title = title_doc_type(pdf.visible_text)
    warnings = [*pdf.warnings, *parsed.warnings]
    if title and title != doc_type:
        warnings.append(f"DOC_TYPE_MISMATCH:{title}")
    view = DocView(
        doc_type=doc_type,
        fields=parsed.fields,
        hidden_spans=pdf.hidden_spans,
        instruction_codes=instruction_codes_of(pdf),
        metadata=pdf.metadata,
        created=pdf.created,
        modified=pdf.modified,
        is_pdf=True,
        missing=[
            *parsed.missing,
            *(["doc_type"] if title and title != doc_type else []),
            *(["complete_text"] if pdf.truncated else []),
        ],
        warnings=warnings,
    )
    return Analysis(view, pdf, parsed, title, warnings)


def analyze_pdf(
    data: bytes, doc_type: str, *, date_order_hint: DateOrder | None = None
) -> Analysis:
    pdf = read_pdf(data)
    return build_view(
        pdf, parse_document(pdf.visible_text, doc_type, date_order_hint=date_order_hint), doc_type
    )


def build_scan_view(pdf: PdfText, doc_type: str) -> Analysis:
    """Documents without a field schema (OTHER): hidden text, instructions and metadata only."""
    view = DocView(
        doc_type=doc_type,
        hidden_spans=pdf.hidden_spans,
        instruction_codes=instruction_codes_of(pdf),
        metadata=pdf.metadata,
        created=pdf.created,
        modified=pdf.modified,
        is_pdf=True,
        missing=["complete_text"] if pdf.truncated else [],
        warnings=list(pdf.warnings),
    )
    return Analysis(view, pdf, None, None, view.warnings)


def photo_colour(data: bytes) -> tuple[str, tuple[int, int, int], int]:
    """(nearest catalogue colour, mean RGB of the central area, distance to that colour)."""
    with Image.open(io.BytesIO(data)) as im:
        if im.width * im.height > MAX_PIXELS:
            raise ValueError("image too large")
        im.draft("RGB", (320, 240))
        rgb = im.convert("RGB")
        rgb.thumbnail((320, 240))
    w, h = rgb.size
    centre = rgb.crop((w // 4, h // 4, w * 3 // 4, h * 3 // 4)).resize((1, 1), Image.Resampling.BOX)
    mean = tuple(int(v) for v in centre.getpixel((0, 0)))  # type: ignore[arg-type]
    name, distance = nearest_colour(mean)  # type: ignore[arg-type]
    return name, mean, distance  # type: ignore[return-value]


def analyze_photo(data: bytes, sha256: str | None = None) -> Analysis:
    warnings: list[str] = []
    colour = None
    try:
        colour = photo_colour(data)
    except Exception:
        warnings.append("PHOTO_UNREADABLE")
    view = DocView(
        doc_type="PRODUCTION_PHOTO",
        is_pdf=False,
        sha256=sha256,
        photo_colour=colour,
        warnings=warnings,
    )
    return Analysis(view, warnings=warnings)
