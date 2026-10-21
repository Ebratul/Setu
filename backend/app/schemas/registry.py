"""Hash registry API models. Lender-facing responses carry the minimum (result, purpose, date,
pseudonymous holder label): no buyer, price, deal reference or document content."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Result = Literal["NEW", "SAME_CONTEXT", "EXACT_DUPLICATE", "NEAR_DUPLICATE"]
Purpose = Literal["ESCROW_EVIDENCE", "FINANCING_COLLATERAL"]
EntryStatus = Literal["ACTIVE", "RELEASED"]
DocKind = Literal[
    "PROFORMA_INVOICE", "COMMERCIAL_INVOICE", "BILL_OF_LADING"
]  # types with identity fields
Sha = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SemanticFields(BaseModel):
    """The identity fields of an invoice or bill of lading (what a lender reads off the paper)."""

    model_config = ConfigDict(extra="forbid")

    doc_type: DocKind
    seller: Annotated[str, Field(min_length=1, max_length=200)]
    number: Annotated[str, Field(min_length=1, max_length=64)]
    total: Annotated[str, Field(pattern=r"^\d{1,16}(\.\d{1,4})?$")] | None = None
    currency: Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")] | None = None
    vessel: Annotated[str, Field(max_length=120)] | None = None


class LenderCheckIn(BaseModel):
    """Exactly one of `sha256`, `document_id` or `fields`. A file goes to `/lender-check/file`."""

    model_config = ConfigDict(extra="forbid")

    lender_id: Annotated[str, Field(min_length=1, max_length=64)]
    sha256: Sha | None = None
    document_id: uuid.UUID | None = None
    fields: SemanticFields | None = None


class LenderCheckOut(Out):
    simulated: Literal[True] = True
    result: Result
    already_registered_for: Purpose | None = None
    registered_on: date | None = None
    held_by: str | None = None


class DocumentRegistryOut(Out):
    document_id: uuid.UUID
    state: Literal["REGISTERED", "DUPLICATE", "NOT_REGISTERED"]
    result: Result
    purpose: Purpose | None = None
    registered_on: date | None = None
    lender_name: str | None = None
    seen_count: int | None = None


class RegistryEntryOut(Out):
    id: uuid.UUID
    sha256_prefix: str
    semantic_prefix: str | None
    doc_type: str
    purpose: Purpose
    lender_name: str | None
    deal_ref: str | None
    registered_on: date
    last_seen_at: datetime | None
    seen_count: int
    exact_hits: int
    near_hits: int
    status: EntryStatus


class RegistryList(Out):
    items: list[RegistryEntryOut]
    total: int


class RegistryStatsOut(Out):
    entries: int
    active: int
    released: int
    by_purpose: dict[str, int]
    duplicates_blocked: int
    exact_blocked: int
    near_blocked: int


class RegistryBlockOut(Out):
    """Why a financing option is blocked on invoice collateral."""

    code: Literal["INVOICE_ALREADY_FINANCED"] = "INVOICE_ALREADY_FINANCED"
    result: Result
    purpose: Purpose
    holder: str | None
    registered_on: date
    reason_en: str
    reason_bn: str
