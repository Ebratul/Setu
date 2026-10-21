"""Pydantic models for synthetic trade-document packs and their ground-truth manifest.

A `Pack` is one consistent shipment. Tamper functions mutate the models; the renderers turn the
models into PDFs/JPEGs. Money is `Decimal`, dates are `date`. All data is fictional.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HiddenText(_M):
    """Text drawn into the PDF that a reader does not see (white, or 1 pt)."""

    text: str
    mode: Literal["white", "tiny"]
    size: float
    color: tuple[float, float, float]
    x: float = 40
    y: float = 60


class Party(_M):
    name: str
    address: str
    license_no: str | None = None


class BankDetails(_M):
    bank_name: str
    holder_name: str
    account_masked: str
    swift: str
    country: str
    account_type: Literal["CORPORATE", "PERSONAL"] = "CORPORATE"


class DocBase(_M):
    """Fields every PDF document carries: hidden texts and optional PDF metadata."""

    hidden: list[HiddenText] = Field(default_factory=list)
    meta_title: str | None = None
    meta_subject: str | None = None
    meta_keywords: str | None = None
    notes: str | None = None  # visible "Notes" section (used by the injection attack set)


class Schedule(_M):
    """Shipment schedule printed on the proforma invoice."""

    booked_vessel: str
    booked_voyage: str
    production_complete: date
    est_ship_date: date
    eta: date


class InvoiceDoc(DocBase):
    doc_type: Literal["PROFORMA_INVOICE", "COMMERCIAL_INVOICE"]
    invoice_no: str
    date: date
    seller: Party
    buyer: Party
    goods_description: str
    hs_code: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    total: Decimal
    currency: str = "USD"
    incoterm: str
    payment_terms: str
    bank: BankDetails
    port_of_loading: str
    port_of_discharge: str
    schedule: Schedule | None = None  # proforma only


class PackingListDoc(DocBase):
    doc_type: Literal["PACKING_LIST"] = "PACKING_LIST"
    pl_no: str
    date: date
    invoice_no: str
    seller: Party
    buyer: Party
    goods_description: str
    packages: int
    package_type: str
    quantity: Decimal
    unit: str
    net_weight_kg: Decimal
    gross_weight_kg: Decimal
    marks: str


class BillOfLadingDoc(DocBase):
    doc_type: Literal["BILL_OF_LADING"] = "BILL_OF_LADING"
    bl_no: str
    carrier: str
    shipper: Party
    consignee: Party
    notify_party: Party
    vessel: str
    voyage: str
    port_of_loading: str
    port_of_discharge: str
    on_board_date: date
    container_no: str
    description: str
    packages: int
    package_type: str
    quantity: Decimal
    unit: str
    gross_weight_kg: Decimal
    freight_terms: str


class CertOfOriginDoc(DocBase):
    doc_type: Literal["CERTIFICATE_OF_ORIGIN"] = "CERTIFICATE_OF_ORIGIN"
    coo_no: str
    exporter: Party
    consignee: Party
    origin_country: str
    hs_code: str
    description: str
    quantity: Decimal
    unit: str
    issue_date: date
    issuing_body: str


class BillOfEntryDoc(DocBase):
    doc_type: Literal["BILL_OF_ENTRY"] = "BILL_OF_ENTRY"
    boe_no: str
    date: date
    importer: Party
    port: str
    bl_no: str
    hs_code: str
    description: str
    quantity: Decimal
    unit: str
    assessed_value_usd: Decimal
    duty_usd: Decimal
    fx_usd_bdt: Decimal
    assessed_value_bdt: Decimal
    duty_bdt: Decimal


class PhotoDoc(_M):
    doc_type: Literal["PRODUCTION_PHOTO"] = "PRODUCTION_PHOTO"
    file_name: str
    color_name: str
    rgb: tuple[int, int, int]
    width_cm: int | None
    capture_date: date
    caption: str
    seed: int


class DealTerms(_M):
    """What the platform already knows about the order; the documents are checked against it."""

    order_ref: str
    supplier_license_name: str
    supplier_license_no: str
    registered_bank: BankDetails
    buyer: Party
    hs_code: str
    unit: str
    price_band: tuple[Decimal, Decimal]
    port_of_loading: str
    port_of_discharge: str
    incoterm: str
    booked_vessel: str
    booked_voyage: str
    production_complete: date
    eta: date
    currency: str = "USD"


class RenderStyle(_M):
    """Small layout variations so a checker cannot overfit to one template."""

    font: Literal["helvetica", "times", "courier"]
    date_fmt: str
    order_seed: int
    producer: str = "Setu Synthetic Renderer"


class Pack(_M):
    pack_id: str
    seed: int
    index: int
    deal: DealTerms
    style: RenderStyle
    proforma: InvoiceDoc
    invoice: InvoiceDoc
    packing_list: PackingListDoc
    bill_of_lading: BillOfLadingDoc
    coo: CertOfOriginDoc
    boe: BillOfEntryDoc
    photos: list[PhotoDoc]
    duplicate_of: str | None = None

    def pdf_docs(self) -> list[tuple[str, DocBase]]:
        """(file stem, document) in a fixed order."""
        return [
            ("proforma_invoice", self.proforma),
            ("commercial_invoice", self.invoice),
            ("packing_list", self.packing_list),
            ("bill_of_lading", self.bill_of_lading),
            ("certificate_of_origin", self.coo),
            ("bill_of_entry", self.boe),
        ]


CheckResult = Literal["PASS", "FAIL"]


class ManifestDoc(_M):
    type: str
    path: str
    sha256: str


class ManifestEntry(_M):
    pack_id: str
    split: Literal["dev", "test"]
    is_tampered: bool
    fraud_types: list[str]
    difficulty: Literal["obvious", "subtle"] | None
    documents: list[ManifestDoc]
    deal_path: str
    expected_checks: dict[str, CheckResult]
    duplicate_of: str | None = None
    seed: int
    notes: str = ""
