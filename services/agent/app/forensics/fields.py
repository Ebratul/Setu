"""Strict field schemas per document type. Names mirror synthetic/models.py; party blocks are
flattened (`seller`, `seller_address`). Every field is optional: a field the extractor could not
read or that failed validation is None and listed in the extraction warnings."""

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

EXTRACTOR_VERSION = "fields@1"


class _F(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvoiceFields(_F):
    doc_type: Literal["PROFORMA_INVOICE", "COMMERCIAL_INVOICE"]
    invoice_no: str | None = None
    date: dt.date | None = None
    seller: str | None = None
    seller_address: str | None = None
    seller_license_no: str | None = None
    buyer: str | None = None
    buyer_address: str | None = None
    buyer_license_no: str | None = None
    goods_description: str | None = None
    hs_code: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    incoterm: str | None = None
    payment_terms: str | None = None
    port_of_loading: str | None = None
    port_of_discharge: str | None = None
    bank_name: str | None = None
    bank_holder: str | None = None
    bank_account: str | None = None
    bank_swift: str | None = None
    booked_vessel: str | None = None
    booked_voyage: str | None = None
    production_complete: dt.date | None = None
    est_ship_date: dt.date | None = None
    eta: dt.date | None = None
    notes: str | None = None


class PackingListFields(_F):
    doc_type: Literal["PACKING_LIST"] = "PACKING_LIST"
    pl_no: str | None = None
    date: dt.date | None = None
    invoice_no: str | None = None
    seller: str | None = None
    seller_address: str | None = None
    buyer: str | None = None
    buyer_address: str | None = None
    goods_description: str | None = None
    packages: int | None = None
    package_type: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    net_weight_kg: Decimal | None = None
    gross_weight_kg: Decimal | None = None
    marks: str | None = None
    notes: str | None = None


class BillOfLadingFields(_F):
    doc_type: Literal["BILL_OF_LADING"] = "BILL_OF_LADING"
    bl_no: str | None = None
    carrier: str | None = None
    shipper: str | None = None
    shipper_address: str | None = None
    consignee: str | None = None
    consignee_address: str | None = None
    notify_party: str | None = None
    vessel: str | None = None
    voyage: str | None = None
    port_of_loading: str | None = None
    port_of_discharge: str | None = None
    on_board_date: dt.date | None = None
    container_no: str | None = None
    description: str | None = None
    packages: int | None = None
    package_type: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    gross_weight_kg: Decimal | None = None
    freight_terms: str | None = None
    notes: str | None = None


class CertOfOriginFields(_F):
    doc_type: Literal["CERTIFICATE_OF_ORIGIN"] = "CERTIFICATE_OF_ORIGIN"
    coo_no: str | None = None
    exporter: str | None = None
    exporter_address: str | None = None
    consignee: str | None = None
    consignee_address: str | None = None
    origin_country: str | None = None
    hs_code: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    issue_date: dt.date | None = None
    issuing_body: str | None = None
    notes: str | None = None


class BillOfEntryFields(_F):
    doc_type: Literal["BILL_OF_ENTRY"] = "BILL_OF_ENTRY"
    boe_no: str | None = None
    date: dt.date | None = None
    importer: str | None = None
    importer_address: str | None = None
    port: str | None = None
    bl_no: str | None = None
    hs_code: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    assessed_value_usd: Decimal | None = None
    duty_usd: Decimal | None = None
    fx_usd_bdt: Decimal | None = None
    assessed_value_bdt: Decimal | None = None
    duty_bdt: Decimal | None = None
    notes: str | None = None


DocFields = (
    InvoiceFields | PackingListFields | BillOfLadingFields | CertOfOriginFields | BillOfEntryFields
)
FIELD_MODELS: dict[str, type[_F]] = {
    "PROFORMA_INVOICE": InvoiceFields,
    "COMMERCIAL_INVOICE": InvoiceFields,
    "PACKING_LIST": PackingListFields,
    "BILL_OF_LADING": BillOfLadingFields,
    "CERTIFICATE_OF_ORIGIN": CertOfOriginFields,
    "BILL_OF_ENTRY": BillOfEntryFields,
}
# Fields without which the document cannot be checked (EXTRACTION_COMPLETE).
REQUIRED: dict[str, tuple[str, ...]] = {
    "PROFORMA_INVOICE": (
        "invoice_no",
        "date",
        "seller",
        "hs_code",
        "quantity",
        "unit_price",
        "total",
    ),
    "COMMERCIAL_INVOICE": (
        "invoice_no",
        "date",
        "seller",
        "hs_code",
        "quantity",
        "unit_price",
        "total",
    ),
    "PACKING_LIST": ("pl_no", "seller", "quantity", "gross_weight_kg", "packages"),
    "BILL_OF_LADING": ("bl_no", "shipper", "vessel", "voyage", "on_board_date", "quantity"),
    "CERTIFICATE_OF_ORIGIN": ("coo_no", "exporter", "hs_code", "quantity", "issue_date"),
    "BILL_OF_ENTRY": ("boe_no", "date", "hs_code", "quantity", "port"),
}
# The name that identifies the issuing party, per document type.
PARTY_FIELD: dict[str, str] = {
    "PROFORMA_INVOICE": "seller",
    "COMMERCIAL_INVOICE": "seller",
    "PACKING_LIST": "seller",
    "BILL_OF_LADING": "shipper",
    "CERTIFICATE_OF_ORIGIN": "exporter",
}
