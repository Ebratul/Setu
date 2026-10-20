"""Inputs of the pure cross-checks: what the platform knows about the deal, and one view per
document. Built from DB rows by app/services/documents, or from a synthetic pack's `deal.json`
by app/forensics/pack_loader.py (dev-split evaluation)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from app.forensics.fields import DocFields
from app.forensics.pdf_text import HiddenSpan


@dataclass(frozen=True, slots=True)
class RegisteredAccount:
    bank_name: str
    holder_name: str
    account: str  # full or masked ("SIM-CN-6222-****-1188")


@dataclass(frozen=True, slots=True)
class Tolerances:
    quantity_pct: Decimal = Decimal("0")
    money: Decimal = Decimal("0.01")
    min_transit_days: int = 7


@dataclass(frozen=True, slots=True)
class DealContext:
    """Facts about the order. Any unknown fact is None and the checks that need it are skipped
    or fall back to the proforma invoice."""

    reference: str
    supplier_license_name: str | None = None
    registered_account: RegisteredAccount | None = None
    hs_code: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    goods_value: Decimal | None = None
    currency: str | None = None
    incoterm: str | None = None  # "FOB" or "FOB Ningbo"
    port_of_loading: str | None = None
    port_of_discharge: str | None = None
    booked_vessel: str | None = None
    booked_voyage: str | None = None
    production_complete: date | None = None
    eta: date | None = None
    price_band: tuple[Decimal, Decimal] | None = None


@dataclass(slots=True)
class DocView:
    """One uploaded document as the checks see it."""

    doc_type: str
    fields: DocFields | None = None
    hidden_spans: list[HiddenSpan] = field(default_factory=list)
    instruction_codes: dict[str, list[str]] = field(default_factory=dict)  # source -> codes
    metadata: dict[str, str] = field(default_factory=dict)
    created: datetime | None = None
    modified: datetime | None = None
    sha256: str | None = None
    is_pdf: bool = True
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    photo_colour: tuple[str, tuple[int, int, int], int] | None = None  # name, mean rgb, distance
    llm_fields: list[str] = field(default_factory=list)  # required fields a model had to fill


@dataclass(slots=True)
class Pack:
    """The documents of one deal by type (latest per type; photos as a list)."""

    docs: dict[str, DocView] = field(default_factory=dict)
    photos: list[DocView] = field(default_factory=list)
    # The pinned proforma invoice (first PASSED or buyer-accepted); later ones never replace it.
    reference: DocView | None = None

    def get(self, doc_type: str) -> DocView | None:
        return self.docs.get(doc_type)

    def fields(self, doc_type: str) -> DocFields | None:
        d = self.docs.get(doc_type)
        return d.fields if d else None
