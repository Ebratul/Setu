"""Helpers for the document tests."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import REPO_ROOT

DEMO = REPO_ROOT / "data" / "demo" / "SETU-2026-0001"
DEAL = "SETU-2026-0001"


def demo_bytes(name: str) -> bytes:
    return (DEMO / name).read_bytes()


def upload(
    client: TestClient,
    deal: str,
    doc_type: str,
    name: str,
    data: bytes | None = None,
    *,
    wait: bool = True,
    mime: str = "application/pdf",
) -> Any:
    payload = demo_bytes(name) if data is None else data
    return client.post(
        f"/deals/{deal}/documents",
        params={"wait": str(wait).lower()},
        data={"doc_type": doc_type},
        files={"file": (Path(name).name, payload, mime)},
    )


def invoice_lines(
    *,
    nonce: str,
    invoice_no: str | None = None,
    seller: str = "Shaoxing Huaxin Textile Co., Ltd.",
    quantity: str = "8,000 m",
    unit_price: str = "USD 1.20 per m",
    total: str = "USD 9,600.00",
    holder: str = "Shaoxing Huaxin Textile Co., Ltd.",
    account: str = "SIM-CN-6222-****-1188",
    bank: str = "Shaoxing Riverside Commercial Bank",
    extra: list[str] | None = None,
) -> list[str]:
    """Text lines of a plausible commercial invoice for a deal made with the usual test payload
    (Huaxin, 8,000 m at USD 1.20, HS 6006.22, FOB Ningbo to Chittagong)."""
    return [
        "COMMERCIAL INVOICE",
        f"Invoice no.: {invoice_no or 'HX-CI-' + nonce[:12]}",
        "Invoice date: 2026-10-11",
        f"Seller: {seller}",
        "Buyer: Rahima Knitwear",
        "Goods description: Dyed cotton jersey fabric, 180 gsm, width 160 cm, colour Navy Blue",
        "HS code: 6006.22",
        f"Quantity: {quantity}",
        f"Unit price: {unit_price}",
        f"Total amount: {total}",
        "Incoterm: FOB Ningbo",
        "Port of loading: Ningbo",
        "Port of discharge: Chittagong",
        f"Bank name: {bank}",
        f"Account holder: {holder}",
        f"Account no.: {account}",
        f"Reference: {nonce}",
        *(extra or []),
    ]
