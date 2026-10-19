"""Document forensics API models (FR-6). A supplier gets a projection with status only: score,
findings, extracted fields and hidden text are buyer/admin/judge data."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

DocTypeOut = Literal[
    "PROFORMA_INVOICE",
    "COMMERCIAL_INVOICE",
    "PACKING_LIST",
    "BILL_OF_LADING",
    "CERTIFICATE_OF_ORIGIN",
    "BILL_OF_ENTRY",
    "PRODUCTION_PHOTO",
    "OTHER",
]
# Suppliers only ever see UPLOADED (unchecked) or IN_REVIEW; the verdict is buyer data.
DocStatusOut = Literal["UPLOADED", "PLACEHOLDER", "REJECTED", "IN_REVIEW"]
CheckStatusOut = Literal["NOT_RUN", "PENDING", "PASSED", "WARNING", "FAILED"]
FindingStatus = Literal["PASS", "WARN", "FAIL", "SKIPPED"]
SeverityOut = Literal["INFO", "WARNING", "CRITICAL"]
VerdictStatus = Literal["PASSED", "WARNING", "FAILED"]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindingOut(Out):
    check_code: str
    status: FindingStatus
    severity: SeverityOut
    label_en: str  # neutral title of the check (reads right beside any status)
    label_bn: str
    issue_en: str  # what is wrong; meaningful when the status is WARN or FAIL
    issue_bn: str
    ground_truth: str | None = None  # the synthetic-data check name this maps to, if any
    detail: dict[str, Any]  # conflicting values and the documents involved (no raw document text)
    checked_at: datetime


class HiddenSpanOut(Out):
    text: str  # untrusted: render as inert text, never as markup or instructions
    page: int
    bbox: list[float]
    colour: list[float] | None
    size: float
    page_width: float | None = None  # PDF points (null for spans stored before this field)
    page_height: float | None = None
    reason: Literal[
        "WHITE_TEXT", "TINY_TEXT", "OFF_PAGE", "INVISIBLE_RENDER", "COVERED_TEXT", "LOW_CONTRAST"
    ]


class VerdictOut(Out):
    status: VerdictStatus
    score: int
    reason_codes: list[str]
    forced_by: list[str]
    explanation_en: str
    explanation_bn: str
    checked_at: datetime | None = None


class TopReasonOut(Out):
    code: str
    status: Literal["WARN", "FAIL"]
    label_en: str  # neutral check title
    label_bn: str
    issue_en: str  # the problem in one line
    issue_bn: str


class DocumentOut(Out):
    id: uuid.UUID
    deal_id: uuid.UUID
    deal_reference: str
    milestone_id: uuid.UUID | None
    milestone_seq: int | None
    doc_type: DocTypeOut
    file_name: str
    mime_type: str
    size_bytes: int | None
    sha256: str | None
    status: DocStatusOut
    check_status: CheckStatusOut
    score: int | None  # null for suppliers and before the first check
    instruction_from_document: bool | None  # null for suppliers
    hidden_text_found: bool | None  # null for suppliers
    top_reason: TopReasonOut | None = None  # worst finding; null for suppliers or when clean
    reference_accepted: bool | None = None  # proforma invoice accepted as the reference
    uploaded_at: datetime | None


class DocumentDetail(DocumentOut):
    fields: dict[str, Any] | None
    findings: list[FindingOut]
    verdict: VerdictOut | None
    hidden_spans_count: int | None
    warnings: list[str]
    extractor_version: str | None
    file_url: str | None  # API-relative signed URL; expires at `file_url_expires_at`
    file_url_expires_at: datetime | None
    file_inline_url: str | None = None  # same token, `inline=1`: PDF/PNG/JPG preview
    viewer_role: Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"] | None = None
    simulated: Literal[True] = True


class DocumentList(Out):
    documents: list[DocumentOut]


class UploadResult(Out):
    document: DocumentOut
    reused: bool  # identical bytes were already on this deal: nothing new was stored
    checking: Literal["QUEUED", "DONE"]


class InjectionHighlight(Out):
    start: int
    end: int
    rule: str


class InjectionFindingOut(Out):
    """Layer 2 on one placement of the document (P19). `text` is untrusted: show it inert."""

    source: Literal["hidden_text", "visible_text", "metadata"]
    rules: list[str]
    score: int
    snippet: str
    text: str
    highlights: list[InjectionHighlight]


class HiddenTextOut(Out):
    document_id: uuid.UUID
    spans: list[HiddenSpanOut]
    instruction_codes: dict[str, list[str]]
    injection: list[InjectionFindingOut] = []
    notice: str
