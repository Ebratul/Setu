"""Step 1 of the pipeline: text layer, hidden spans and metadata (images have no text layer).
PDFs are parsed in a resource-limited child process (RLIMIT_AS, CPU, wall-clock timeout)."""

from app.config import get_settings
from app.forensics.pdf_text import PdfText
from app.forensics.sandbox import parse_pdf


def extract_text(data: bytes, mime_type: str) -> PdfText | None:
    """Visible text, hidden spans and cleaned metadata for a PDF; None for images.
    Raises `PdfReadError` when the file cannot be parsed within the limits."""
    if mime_type != "application/pdf":
        return None
    s = get_settings()
    return parse_pdf(
        data,
        sandbox=s.forensics_sandbox,
        timeout=s.forensics_parse_timeout_seconds,
        memory_mb=s.forensics_parse_memory_mb,
    )
