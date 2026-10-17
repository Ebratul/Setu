"""Internal consistency validator: the ground truth for `expected_checks`.

It works on the structured models (not on PDFs), so it is independent of how a document is
rendered. P14's forensics must reach the same PASS/FAIL results from the PDFs alone.
"""

import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from synthetic import catalog as cat
from synthetic.models import CheckResult, DocBase, InvoiceDoc, Pack

CHECKS = (
    "QUANTITY_MATCH",
    "VALUE_MATCH",
    "VESSEL_DATE_MATCH",
    "NAME_MATCH",
    "DUPLICATE_INVOICE",
    "PRICE_IN_BAND",
    "BENEFICIARY_MATCH",
    "HIDDEN_TEXT_SCAN",
    "INSTRUCTION_SCAN",
    "PORT_MATCH",
    "HS_CODE_MATCH",
)

INSTRUCTION_RE = re.compile(
    r"\b(system|assistant|ignore (all |any )?(previous|prior)|release (the )?full payment|"
    r"approve (all|without)|skip (the )?(checks|verification)|documents verified)\b",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    return " ".join(text.casefold().split())


def canonical_key(inv: InvoiceDoc) -> str:
    """Identity of an invoice independent of the PDF bytes."""
    return f"{norm(inv.seller.name)}|{inv.invoice_no}|{inv.total}|{inv.currency}"


@dataclass(slots=True)
class Registry:
    """What lenders have already seen: file hashes and canonical invoice keys."""

    sha256: dict[str, str] = field(default_factory=dict)
    canonical: dict[str, str] = field(default_factory=dict)

    def seen(self, sha: str, key: str, pack_id: str) -> str | None:
        owner = self.sha256.get(sha) or self.canonical.get(key)
        return owner if owner and owner != pack_id else None

    def register(self, sha: str, key: str, pack_id: str) -> None:
        self.sha256.setdefault(sha, pack_id)
        self.canonical.setdefault(key, pack_id)


def _qty_match(p: Pack) -> bool:
    qtys = {
        p.proforma.quantity,
        p.invoice.quantity,
        p.packing_list.quantity,
        p.bill_of_lading.quantity,
        p.coo.quantity,
        p.boe.quantity,
    }
    units = {
        p.proforma.unit,
        p.invoice.unit,
        p.packing_list.unit,
        p.bill_of_lading.unit,
        p.coo.unit,
        p.boe.unit,
    }
    return (
        len(qtys) == 1
        and len(units) == 1
        and p.packing_list.gross_weight_kg == p.bill_of_lading.gross_weight_kg
        and p.packing_list.packages == p.bill_of_lading.packages
    )


def _value_match(p: Pack) -> bool:
    for inv in (p.proforma, p.invoice):
        if (inv.quantity * inv.unit_price).quantize(Decimal("0.01")) != inv.total:
            return False
    pi, ci = p.proforma, p.invoice
    return (pi.unit_price, pi.total, pi.currency) == (ci.unit_price, ci.total, ci.currency)


def _vessel_date_match(p: Pack) -> bool:
    bl, deal = p.bill_of_lading, p.deal
    sched = p.proforma.schedule
    assert sched is not None
    return (
        norm(bl.vessel) == norm(deal.booked_vessel) == norm(sched.booked_vessel)
        and norm(bl.voyage) == norm(deal.booked_voyage) == norm(sched.booked_voyage)
        and p.proforma.date <= deal.production_complete <= bl.on_board_date
        and p.invoice.date <= bl.on_board_date
        and bl.on_board_date + timedelta(days=cat.MIN_TRANSIT_DAYS) <= deal.eta
        and p.boe.date >= deal.eta
    )


def _name_match(p: Pack) -> bool:
    want = norm(p.deal.supplier_license_name)
    names = [
        p.proforma.seller.name,
        p.invoice.seller.name,
        p.packing_list.seller.name,
        p.bill_of_lading.shipper.name,
        p.coo.exporter.name,
    ]
    return all(norm(n) == want for n in names)


def _beneficiary_match(p: Pack) -> bool:
    want = p.deal.registered_bank
    return all(
        (norm(b.holder_name), b.account_masked, norm(b.bank_name))
        == (norm(want.holder_name), want.account_masked, norm(want.bank_name))
        for b in (p.proforma.bank, p.invoice.bank)
    )


def _port_match(p: Pack) -> bool:
    d, bl = p.deal, p.bill_of_lading
    ports_ok = (
        norm(bl.port_of_loading) == norm(d.port_of_loading)
        and norm(bl.port_of_discharge) == norm(d.port_of_discharge)
        and norm(p.boe.port) == norm(d.port_of_discharge)
    )
    for inv in (p.proforma, p.invoice):
        ports_ok &= norm(inv.port_of_loading) == norm(d.port_of_loading)
        ports_ok &= norm(inv.port_of_discharge) == norm(d.port_of_discharge)
        ports_ok &= norm(inv.incoterm) == norm(d.incoterm)
    return ports_ok


def _hs_match(p: Pack) -> bool:
    codes = {p.proforma.hs_code, p.invoice.hs_code, p.coo.hs_code, p.boe.hs_code, p.deal.hs_code}
    return len(codes) == 1


def _price_in_band(p: Pack) -> bool:
    lo, hi = p.deal.price_band
    return all(lo <= inv.unit_price <= hi for inv in (p.proforma, p.invoice))


def _all_texts(doc: DocBase) -> list[str]:
    texts = [h.text for h in doc.hidden]
    texts += [t for t in (doc.meta_title, doc.meta_subject, doc.meta_keywords) if t]
    return texts


def validate(p: Pack, invoice_sha256: str, registry: Registry) -> dict[str, CheckResult]:
    """Run every check; `invoice_sha256` is the hash of the rendered commercial invoice."""
    docs = [d for _, d in p.pdf_docs()]
    hidden = any(d.hidden for d in docs)
    texts = [t for d in docs for t in _all_texts(d)]
    dup = registry.seen(invoice_sha256, canonical_key(p.invoice), p.pack_id) is not None

    def res(ok: bool) -> CheckResult:
        return "PASS" if ok else "FAIL"

    return {
        "QUANTITY_MATCH": res(_qty_match(p)),
        "VALUE_MATCH": res(_value_match(p)),
        "VESSEL_DATE_MATCH": res(_vessel_date_match(p)),
        "NAME_MATCH": res(_name_match(p)),
        "DUPLICATE_INVOICE": res(not dup),
        "PRICE_IN_BAND": res(_price_in_band(p)),
        "BENEFICIARY_MATCH": res(_beneficiary_match(p)),
        "HIDDEN_TEXT_SCAN": res(not hidden),
        "INSTRUCTION_SCAN": res(not any(INSTRUCTION_RE.search(t) for t in texts)),
        "PORT_MATCH": res(_port_match(p)),
        "HS_CODE_MATCH": res(_hs_match(p)),
    }
