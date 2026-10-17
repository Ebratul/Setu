"""Canonical identity of an invoice, independent of the file bytes (a re-saved copy keeps it)."""

import hashlib
import unicodedata
from decimal import ROUND_HALF_UP, Decimal


def canonical_invoice_hash(
    seller: str, invoice_no: str, total: Decimal | str, currency: str
) -> str:
    """sha256 of "seller|invoice no|total (2 dp)|currency" with case and spacing folded."""
    name = " ".join(unicodedata.normalize("NFKC", seller).casefold().split())
    amount = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    raw = f"{name}|{invoice_no.strip().upper()}|{amount}|{currency.strip().upper()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def canonical_bl_hash(shipper: str, bl_no: str, vessel: str | None = None) -> str:
    """sha256 of "shipper|B/L no|vessel" with case and spacing folded (a re-scan keeps it)."""
    fold = lambda v: " ".join(unicodedata.normalize("NFKC", v).casefold().split())  # noqa: E731
    raw = f"{fold(shipper)}|{bl_no.strip().upper()}|{fold(vessel or '')}"
    return hashlib.sha256(raw.encode()).hexdigest()
