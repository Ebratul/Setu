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
