"""Deterministic cross-checks over extracted fields and a deal context (no DB, no LLM).

`run_checks(target, pack, ctx)` returns one Outcome per applicable check for the target document;
a check that needs a document or fact that is not there yet is SKIPPED (never WARN), so checks can
run as soon as the first document arrives and again when a sibling is uploaded. Pack-level
comparisons are attached to the document that deviates from the reference (deal, else proforma
invoice), and mismatches between two non-reference documents (packing list vs B/L weights, CI date
vs B/L date) are attached to both.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from app.domain.kyb import match_names
from app.forensics.context import DealContext, DocView, Pack, Tolerances
from app.forensics.pdf_text import HARD_REASONS, HiddenSpan

Status = Literal["PASS", "WARN", "FAIL", "SKIPPED"]
INVOICES = ("PROFORMA_INVOICE", "COMMERCIAL_INVOICE")
PDF_TYPES = (
    "PROFORMA_INVOICE",
    "COMMERCIAL_INVOICE",
    "PACKING_LIST",
    "BILL_OF_LADING",
    "CERTIFICATE_OF_ORIGIN",
    "BILL_OF_ENTRY",
)
PRICE_BANDS_PATH = Path(__file__).with_name("price_bands.json")
CENT = Decimal("0.01")
EDITOR_PRODUCERS = re.compile(
    r"photoshop|illustrator|gimp|inkscape|pdfescape|sejda|smallpdf|ilovepdf|foxit phantom|"
    r"nitro|pdf-?xchange editor|canva",
    re.I,
)
PORT_ALIASES = {"chattogram": "chittagong", "chittagong port": "chittagong"}
UNIT_ALIASES = {
    "meter": "m", "meters": "m", "metre": "m", "metres": "m", "mtr": "m", "mtrs": "m", "yd": "yd",
    "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "pc": "pcs", "piece": "pcs", "pieces": "pcs",
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Outcome:
    code: str
    status: Status
    detail: dict[str, Any] = field(default_factory=dict)


def load_price_bands() -> dict[str, tuple[Decimal, Decimal, str]]:
    raw = json.loads(PRICE_BANDS_PATH.read_text())["bands"]
    return {hs: (Decimal(b["min"]), Decimal(b["max"]), b["currency"]) for hs, b in raw.items()}


PRICE_BANDS = load_price_bands()


# --- helpers ----------------------------------------------------------------------------------


def squash(value: str | None) -> str:
    """Case and spacing only: the strict comparison used for names, vessels and ports."""
    return " ".join(unicodedata.normalize("NFKC", value or "").casefold().split())


def port_key(value: str | None) -> str:
    s = squash(value)
    return PORT_ALIASES.get(s, s)


def unit_key(value: str | None) -> str:
    s = squash(value).rstrip(".")
    return UNIT_ALIASES.get(s, s)


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def g(view: DocView | None, name: str) -> Any:
    return getattr(view.fields, name, None) if view and view.fields else None


def _num(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def _skip(code: str, reason: str) -> Outcome:
    return Outcome(code, "SKIPPED", {"reason": reason})


def _worst(*statuses: Status) -> Status:
    for s in ("FAIL", "WARN", "PASS"):
        if s in statuses:
            return s  # type: ignore[return-value]
    return "SKIPPED"


def money_eq(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) <= tol


def _ref_view(pack: Pack, target: DocView) -> DocView | None:
    pi = pack.get("PROFORMA_INVOICE")
    return pi if pi is not None and pi is not target else None


# --- individual checks ------------------------------------------------------------------------


def quantity_match(t: DocView, pack: Pack, ctx: DealContext, tol: Tolerances) -> Outcome:
    code = "QUANTITY_MATCH"
    qty, unit = g(t, "quantity"), g(t, "unit")
    if qty is None:
        return _skip(code, "quantity not read")
    ref_qty, ref_unit, source = ctx.quantity, ctx.unit, "deal"
    pi = _ref_view(pack, t)
    if ref_qty is None and pi is not None:
        ref_qty, ref_unit, source = g(pi, "quantity"), g(pi, "unit"), "PROFORMA_INVOICE"
    conflicts: list[dict[str, Any]] = []
    if ref_qty is None:
        if t.doc_type != "PROFORMA_INVOICE":
            # reference-less pairs: invoice reference for this pack is the commercial invoice
            ci = pack.get("COMMERCIAL_INVOICE")
            if ci is not None and ci is not t and g(ci, "quantity") is not None:
                ref_qty, ref_unit, source = g(ci, "quantity"), g(ci, "unit"), "COMMERCIAL_INVOICE"
        if ref_qty is None:
            conflicts_only = _weights(t, pack)
            if conflicts_only:
                return Outcome(code, "FAIL", {"conflicts": conflicts_only})
            return _skip(code, "no reference quantity yet")
    diff = abs(qty - ref_qty)
    pct = (diff / ref_qty * 100) if ref_qty else Decimal(0)
    if pct > tol.quantity_pct:
        conflicts.append(
            {
                "field": "quantity",
                "found": _num(qty),
                "expected": _num(ref_qty),
                "against": source,
                "diff_pct": str(pct.quantize(CENT, ROUND_HALF_UP)),
            }
        )
    if unit and ref_unit and unit_key(unit) != unit_key(ref_unit):
        conflicts.append({"field": "unit", "found": unit, "expected": ref_unit, "against": source})
    conflicts.extend(_weights(t, pack))
    if conflicts:
        return Outcome(code, "FAIL", {"conflicts": conflicts})
    return Outcome(code, "PASS", {"quantity": _num(qty), "against": source})


def _weights(t: DocView, pack: Pack) -> list[dict[str, Any]]:
    """Packing list and B/L must agree on packages and gross weight."""
    if t.doc_type not in ("PACKING_LIST", "BILL_OF_LADING"):
        return []
    other = pack.get("BILL_OF_LADING" if t.doc_type == "PACKING_LIST" else "PACKING_LIST")
    if other is None:
        return []
    out: list[dict[str, Any]] = []
    for name in ("gross_weight_kg", "packages"):
        a, b = g(t, name), g(other, name)
        if a is not None and b is not None and a != b:
            out.append(
                {
                    "field": name,
                    "found": _num(a) if isinstance(a, Decimal) else a,
                    "expected": _num(b) if isinstance(b, Decimal) else b,
                    "against": other.doc_type,
                }
            )
    return out


def value_math(t: DocView, tol: Tolerances) -> Outcome | None:
    if t.doc_type not in INVOICES:
        return None
    q, p, total = g(t, "quantity"), g(t, "unit_price"), g(t, "total")
    if q is None or p is None or total is None:
        return _skip("VALUE_MATH", "quantity, unit price or total not read")
    calc = (q * p).quantize(CENT, ROUND_HALF_UP)
    if money_eq(calc, total, tol.money):
        return Outcome("VALUE_MATH", "PASS", {"computed": str(calc), "total": str(total)})
    return Outcome(
        "VALUE_MATH",
        "FAIL",
        {
            "computed": str(calc),
            "total": str(total),
            "diff": str((total - calc).quantize(CENT)),
            "quantity": _num(q),
            "unit_price": _num(p),
        },
    )


def value_match(t: DocView, pack: Pack, ctx: DealContext, tol: Tolerances) -> Outcome | None:
    if t.doc_type not in INVOICES:
        return None
    price, total, cur = g(t, "unit_price"), g(t, "total"), g(t, "currency")
    if price is None and total is None:
        return _skip("VALUE_MATCH", "price and total not read")
    refs: list[tuple[str, Decimal | None, Decimal | None, str | None]] = []
    if ctx.unit_price is not None or ctx.goods_value is not None:
        refs.append(("deal", ctx.unit_price, ctx.goods_value, ctx.currency))
    pi = _ref_view(pack, t)
    if pi is not None and t.doc_type == "COMMERCIAL_INVOICE":
        refs.append(("PROFORMA_INVOICE", g(pi, "unit_price"), g(pi, "total"), g(pi, "currency")))
    if not refs:
        return _skip("VALUE_MATCH", "no reference price yet")
    conflicts: list[dict[str, Any]] = []
    for source, r_price, r_total, r_cur in refs:
        if price is not None and r_price is not None and price != r_price:
            conflicts.append(
                {"field": "unit_price", "found": _num(price), "expected": _num(r_price),
                 "against": source}
            )  # fmt: skip
        if total is not None and r_total is not None and not money_eq(total, r_total, tol.money):
            conflicts.append(
                {"field": "total", "found": _num(total), "expected": _num(r_total),
                 "against": source}
            )  # fmt: skip
        if cur and r_cur and cur.upper() != r_cur.upper():
            conflicts.append(
                {"field": "currency", "found": cur, "expected": r_cur, "against": source}
            )
    if conflicts:
        return Outcome("VALUE_MATCH", "FAIL", {"conflicts": conflicts})
    return Outcome("VALUE_MATCH", "PASS", {"against": [r[0] for r in refs]})


def _party_name(t: DocView) -> str | None:
    from app.forensics.fields import PARTY_FIELD

    field_name = PARTY_FIELD.get(t.doc_type)
    return g(t, field_name) if field_name else None


def name_match(t: DocView, ctx: DealContext, match: float, partial: float) -> Outcome | None:
    if t.doc_type not in ("PROFORMA_INVOICE", "COMMERCIAL_INVOICE", "PACKING_LIST",
                          "BILL_OF_LADING", "CERTIFICATE_OF_ORIGIN"):  # fmt: skip
        return None
    name = _party_name(t)
    if name is None:
        return _skip("NAME_MATCH", "party name not read")
    if not ctx.supplier_license_name:
        return _skip("NAME_MATCH", "no licence name on file")
    if squash(name) == squash(ctx.supplier_license_name):
        return Outcome("NAME_MATCH", "PASS", {"score": "100.00"})
    m = match_names(name, ctx.supplier_license_name, match=match, partial=partial)
    detail = {"found": name, "expected": ctx.supplier_license_name, "score": str(m.score),
              "band": m.band}  # fmt: skip
    # Anything that is not identical (case and spacing aside) is at least a review item; a name
    # that is clearly another company is a failure.
    return Outcome("NAME_MATCH", "WARN" if m.band == "match" else "FAIL", detail)


def _mask_re(value: str) -> re.Pattern[str]:
    return re.compile("".join(r"[\w]+?" if ch == "*" else re.escape(ch) for ch in value) + r"$")


def account_equal(a: str, b: str) -> bool:
    """Account numbers where either side may be masked with `*` (one `*` = unknown characters)."""
    a, b = a.strip().upper(), b.strip().upper()
    if a == b:
        return True
    if "*" in a and "*" not in b:
        return bool(_mask_re(a).match(b)) and len(a) <= len(b)
    if "*" in b and "*" not in a:
        return bool(_mask_re(b).match(a)) and len(b) <= len(a)
    if "*" in a and "*" in b:
        return len(a) == len(b) and all(x == y or "*" in (x, y) for x, y in zip(a, b, strict=True))
    return False


def beneficiary_match(t: DocView, ctx: DealContext) -> Outcome | None:
    if t.doc_type not in INVOICES:
        return None
    reg = ctx.registered_account
    if reg is None:
        return _skip("BENEFICIARY_MATCH", "no registered receiving account")
    holder, bank, acct = g(t, "bank_holder"), g(t, "bank_name"), g(t, "bank_account")
    if holder is None and bank is None and acct is None:
        return Outcome("BENEFICIARY_MATCH", "WARN", {"reason": "no bank details on the document"})
    bad: list[str] = []
    detail: dict[str, Any] = {}
    if holder is not None and squash(holder) != squash(reg.holder_name):
        bad.append("holder")
        detail["holder"] = {"found": holder, "expected": reg.holder_name}
    if bank is not None and squash(bank) != squash(reg.bank_name):
        bad.append("bank")
        detail["bank"] = {"found": bank, "expected": reg.bank_name}
    if acct is not None and not account_equal(acct, reg.account):
        bad.append("account")
        detail["account"] = {"found": acct, "expected": _mask(reg.account)}
    if bad:
        return Outcome("BENEFICIARY_MATCH", "FAIL", {"mismatched": bad, **detail})
    missing = [n for n, v in (("holder", holder), ("bank", bank), ("account", acct)) if v is None]
    if missing:
        return Outcome("BENEFICIARY_MATCH", "WARN", {"reason": "incomplete", "missing": missing})
    return Outcome("BENEFICIARY_MATCH", "PASS", {})


def _mask(account: str) -> str:
    return account if "*" in account or len(account) <= 8 else account[:4] + "****" + account[-4:]


def _booking(pack: Pack, ctx: DealContext) -> tuple[str | None, str | None, str]:
    if ctx.booked_vessel or ctx.booked_voyage:
        return ctx.booked_vessel, ctx.booked_voyage, "deal"
    pi = pack.get("PROFORMA_INVOICE")
    return g(pi, "booked_vessel"), g(pi, "booked_voyage"), "PROFORMA_INVOICE"


def vessel_voyage_match(t: DocView, pack: Pack, ctx: DealContext) -> Outcome | None:
    code = "VESSEL_VOYAGE_MATCH"
    if t.doc_type == "BILL_OF_LADING":
        vessel, voyage = g(t, "vessel"), g(t, "voyage")
        b_vessel, b_voyage, source = _booking(pack, ctx)
    elif t.doc_type == "PROFORMA_INVOICE" and (ctx.booked_vessel or ctx.booked_voyage):
        vessel, voyage = g(t, "booked_vessel"), g(t, "booked_voyage")
        b_vessel, b_voyage, source = ctx.booked_vessel, ctx.booked_voyage, "deal"
    else:
        return None
    if b_vessel is None and b_voyage is None:
        return _skip(code, "no booking to compare with (upload the proforma invoice)")
    conflicts = []
    if vessel and b_vessel and squash(vessel) != squash(b_vessel):
        conflicts.append({"field": "vessel", "found": vessel, "expected": b_vessel,
                          "against": source})  # fmt: skip
    if voyage and b_voyage and squash(voyage) != squash(b_voyage):
        conflicts.append({"field": "voyage", "found": voyage, "expected": b_voyage,
                          "against": source})  # fmt: skip
    if conflicts:
        return Outcome(code, "FAIL", {"conflicts": conflicts})
    if not vessel and not voyage:
        return _skip(code, "vessel and voyage not read")
    return Outcome(code, "PASS", {"against": source})


def date_logic(t: DocView, pack: Pack, ctx: DealContext, tol: Tolerances) -> Outcome | None:
    code = "DATE_LOGIC"
    if t.doc_type not in (*INVOICES, "BILL_OF_LADING", "BILL_OF_ENTRY", "CERTIFICATE_OF_ORIGIN"):
        return None
    pi, ci = pack.get("PROFORMA_INVOICE"), pack.get("COMMERCIAL_INVOICE")
    bl, boe = pack.get("BILL_OF_LADING"), pack.get("BILL_OF_ENTRY")
    produced = ctx.production_complete or g(pi, "production_complete")
    eta = ctx.eta or g(pi, "eta")
    on_board: date | None = g(bl, "on_board_date")
    broken: list[dict[str, Any]] = []
    warn: list[dict[str, Any]] = []
    checked = 0

    def order(name: str, earlier: date | None, later: date | None, a: str, b: str,
              gap: int = 0) -> None:  # fmt: skip
        nonlocal checked
        if earlier is None or later is None:
            return
        checked += 1
        if earlier + timedelta(days=gap) > later:
            broken.append({"rule": name, "earlier": f"{a}={earlier}", "later": f"{b}={later}",
                           "min_gap_days": gap})  # fmt: skip

    if t.doc_type == "PROFORMA_INVOICE":
        order("PI_BEFORE_PRODUCTION_DONE", g(t, "date"), produced, "PI date", "production complete")
        order("PRODUCTION_BEFORE_ETA", produced, eta, "production complete", "ETA")
    elif t.doc_type == "COMMERCIAL_INVOICE":
        order("CI_BEFORE_ON_BOARD", g(t, "date"), on_board, "CI date", "on board")
    elif t.doc_type == "BILL_OF_LADING":
        order("ON_BOARD_AFTER_PRODUCTION", produced, on_board, "production complete", "on board")
        order("ON_BOARD_AFTER_PI", g(pi, "date"), on_board, "PI date", "on board")
        order("CI_BEFORE_ON_BOARD", g(ci, "date"), on_board, "CI date", "on board")
        order("TRANSIT_BEFORE_ETA", on_board, eta, "on board", "ETA", tol.min_transit_days)
    elif t.doc_type == "BILL_OF_ENTRY":
        order("ENTRY_AFTER_ETA", eta, g(t, "date"), "ETA", "bill of entry date")
        order("ENTRY_AFTER_ON_BOARD", on_board, g(t, "date"), "on board", "bill of entry date")
    elif t.doc_type == "CERTIFICATE_OF_ORIGIN":
        issued = g(t, "issue_date")
        for rule, e, lt, a, b in (
            ("COO_AFTER_PI", g(pi, "date"), issued, "PI date", "CoO date"),
            ("COO_BEFORE_ENTRY", issued, g(boe, "date"), "CoO date", "bill of entry date"),
        ):
            if e is not None and lt is not None:
                checked += 1
                if e > lt:
                    warn.append({"rule": rule, "earlier": f"{a}={e}", "later": f"{b}={lt}"})
        if issued is not None and on_board is not None:
            checked += 1
            if issued > on_board + timedelta(days=30):
                warn.append(
                    {"rule": "COO_ISSUED_LONG_AFTER_SHIPMENT", "later": f"CoO date={issued}"}
                )
    if broken:
        return Outcome(code, "FAIL", {"broken": broken})
    if warn:
        return Outcome(code, "WARN", {"broken": warn})
    if checked == 0:
        return _skip(code, "not enough dates yet")
    return Outcome(code, "PASS", {"rules_checked": checked})


def port_match(t: DocView, ctx: DealContext) -> Outcome | None:
    code = "PORT_MATCH"
    if t.doc_type not in (*INVOICES, "BILL_OF_LADING", "BILL_OF_ENTRY"):
        return None
    conflicts: list[dict[str, Any]] = []
    compared = 0

    def cmp(name: str, found: str | None, expected: str | None) -> None:
        nonlocal compared
        if found and expected:
            compared += 1
            if port_key(found) != port_key(expected):
                conflicts.append({"field": name, "found": found, "expected": expected,
                                  "against": "deal"})  # fmt: skip

    if t.doc_type == "BILL_OF_ENTRY":
        cmp("port", g(t, "port"), ctx.port_of_discharge)
    else:
        cmp("port_of_loading", g(t, "port_of_loading"), ctx.port_of_loading)
        cmp("port_of_discharge", g(t, "port_of_discharge"), ctx.port_of_discharge)
    if t.doc_type in INVOICES and g(t, "incoterm") and ctx.incoterm:
        compared += 1
        found_term, _, found_place = squash(g(t, "incoterm")).partition(" ")
        want_term, _, want_place = squash(ctx.incoterm).partition(" ")
        places = {port_key(ctx.port_of_loading), port_key(ctx.port_of_discharge)}
        bad = found_term != want_term
        if want_place:
            bad = bad or port_key(found_place) != port_key(want_place)
        elif found_place:
            bad = bad or port_key(found_place) not in places
        if bad:
            conflicts.append({"field": "incoterm", "found": g(t, "incoterm"),
                              "expected": ctx.incoterm, "against": "deal"})  # fmt: skip
    if conflicts:
        return Outcome(code, "FAIL", {"conflicts": conflicts})
    if compared == 0:
        return _skip(code, "no ports to compare")
    return Outcome(code, "PASS", {})


def hs_code_match(t: DocView, pack: Pack, ctx: DealContext) -> Outcome | None:
    code = "HS_CODE_MATCH"
    if t.doc_type not in (*INVOICES, "CERTIFICATE_OF_ORIGIN", "BILL_OF_ENTRY"):
        return None
    found = g(t, "hs_code")
    if not found:
        return _skip(code, "HS code not read")
    expected, source = ctx.hs_code, "deal"
    pi = _ref_view(pack, t)
    if not expected and pi is not None:
        expected, source = g(pi, "hs_code"), "PROFORMA_INVOICE"
    if not expected:
        return _skip(code, "no reference HS code yet")
    a, b = digits(found), digits(expected)
    n = min(len(a), len(b))
    if n >= 6 and a[:n] == b[:n]:
        return Outcome(code, "PASS", {"against": source})
    return Outcome(
        code,
        "FAIL",
        {"conflicts": [{"field": "hs_code", "found": found, "expected": expected,
                        "against": source}]},
    )  # fmt: skip


def price_band(t: DocView, ctx: DealContext) -> Outcome | None:
    code = "PRICE_BAND"
    if t.doc_type not in INVOICES:
        return None
    price, cur = g(t, "unit_price"), (g(t, "currency") or ctx.currency or "USD")
    if price is None:
        return _skip(code, "unit price not read")
    band = ctx.price_band
    band_cur = "USD"
    if band is None:
        hs = ctx.hs_code or g(t, "hs_code") or ""
        ref = PRICE_BANDS.get(hs.strip())
        if ref is None:
            return _skip(code, "no price band for this HS code")
        band, band_cur = (ref[0], ref[1]), ref[2]
    if cur.upper() != band_cur:
        return _skip(code, f"band is in {band_cur}")
    lo, hi = band
    if lo <= price <= hi:
        return Outcome(code, "PASS", {"unit_price": _num(price), "band": [_num(lo), _num(hi)]})
    ratio = price / (hi if price > hi else lo)
    return Outcome(
        code,
        "FAIL",
        {
            "unit_price": _num(price),
            "band": [_num(lo), _num(hi)],
            "currency": band_cur,
            "vs_edge": str(ratio.quantize(CENT, ROUND_HALF_UP)),
        },
    )


def hidden_text(t: DocView) -> Outcome | None:
    if not t.is_pdf:
        return None
    spans: list[HiddenSpan] = t.hidden_spans
    if not spans:
        return Outcome("HIDDEN_TEXT", "PASS", {})
    reasons: dict[str, int] = {}
    for s in spans:
        reasons[s.reason] = reasons.get(s.reason, 0) + 1
    hard = any(s.reason in HARD_REASONS for s in spans)
    return Outcome(
        "HIDDEN_TEXT",
        "FAIL" if hard else "WARN",  # covered or very low-contrast text: review, not proof
        {
            "spans": len(spans),
            "reasons": reasons,
            "pages": sorted({s.page for s in spans}),
            "chars": sum(len(s.text) for s in spans),
        },
    )


def instruction_scan(t: DocView) -> Outcome | None:
    if not t.is_pdf:
        return None
    sources = {s: c for s, c in t.instruction_codes.items() if c}
    if not sources:
        return Outcome("INSTRUCTION_SCAN", "PASS", {})
    return Outcome(
        "INSTRUCTION_SCAN",
        "FAIL",
        {
            "instruction_from_document": True,
            "sources": sorted(sources),
            "codes": sorted({c for codes in sources.values() for c in codes}),
        },
    )


def metadata_anomaly(t: DocView, pack: Pack) -> Outcome | None:
    if not t.is_pdf:
        return None
    notes: list[str] = []
    if t.created and t.modified and t.modified - t.created > timedelta(hours=1):
        notes.append("MODIFIED_AFTER_CREATION")
    producer = t.metadata.get("Producer", "") + " " + t.metadata.get("Creator", "")
    if EDITOR_PRODUCERS.search(producer):
        notes.append("EDITING_TOOL")
    others = [
        d.metadata.get("Producer")
        for d in pack.docs.values()
        if d is not t and d.is_pdf and d.metadata.get("Producer")
    ]
    mine = t.metadata.get("Producer")
    if mine and len(others) >= 2 and all(o == others[0] for o in others) and mine != others[0]:
        notes.append("PRODUCER_DIFFERS_FROM_PACK")
    if notes:
        return Outcome("METADATA_ANOMALY", "WARN", {"notes": notes})
    return Outcome("METADATA_ANOMALY", "PASS", {})


def duplicate_hash(registry_status: str | None, detail: dict[str, Any] | None) -> Outcome:
    if registry_status in (None, "NEW"):
        return Outcome("DUPLICATE_HASH", "PASS", detail or {})
    return Outcome("DUPLICATE_HASH", "FAIL", {"registry_status": registry_status, **(detail or {})})


_REF_FIELDS = ("seller", "bank_name", "bank_holder", "bank_account", "unit_price", "total",
                "quantity", "hs_code")  # fmt: skip
_REF_PI_ONLY = ("invoice_no", "booked_vessel", "booked_voyage", "production_complete", "eta")


def reference_changed(t: DocView, pack: Pack) -> Outcome | None:
    """A later invoice that differs from the pinned proforma invoice (identity, booking, bank
    details, price or totals) needs buyer review; it never becomes the new baseline."""
    if t.doc_type not in INVOICES:
        return None
    ref = pack.reference or pack.docs.get("PROFORMA_INVOICE")
    if ref is None or ref is t or ref.fields is None or t.fields is None:
        return _skip("REFERENCE_CHANGED", "no pinned proforma invoice to compare with")
    names = _REF_FIELDS + (_REF_PI_ONLY if t.doc_type == "PROFORMA_INVOICE" else ())
    changed = [
        n for n in names if g(t, n) is not None and g(ref, n) is not None and g(t, n) != g(ref, n)
    ]
    if changed:
        return Outcome("REFERENCE_CHANGED", "WARN", {"changed": sorted(changed)})
    return Outcome("REFERENCE_CHANGED", "PASS", {})


def extraction_complete(t: DocView) -> Outcome | None:
    if not t.is_pdf:
        return None
    if t.missing or t.llm_fields:
        detail: dict[str, Any] = {"missing": sorted(t.missing)}
        if t.llm_fields:  # a model read these: the verdict can never be a clean PASSED
            detail["model_filled"] = sorted(t.llm_fields)
        return Outcome("EXTRACTION_COMPLETE", "WARN", detail)
    return Outcome("EXTRACTION_COMPLETE", "PASS", {})


COLOUR_NAMES: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("Navy Blue", (24, 43, 87)),
    ("Maroon", (110, 25, 38)),
    ("Forest Green", (34, 85, 52)),
    ("Charcoal Grey", (66, 69, 73)),
    ("Royal Blue", (36, 70, 160)),
    ("Black", (22, 22, 24)),
    ("Off White", (232, 228, 214)),
    ("Olive", (106, 112, 52)),
    ("Mustard", (200, 154, 36)),
    ("Teal", (30, 120, 124)),
    ("Burgundy", (96, 20, 48)),
    ("Sky Blue", (126, 176, 218)),
)
PHOTO_PASS_DISTANCE = 60
PHOTO_WARN_DISTANCE = 100


def colour_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return round(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5)


def nearest_colour(rgb: tuple[int, int, int]) -> tuple[str, int]:
    name, ref = min(COLOUR_NAMES, key=lambda c: colour_distance(rgb, c[1]))
    return name, colour_distance(rgb, ref)


def spec_colour(text: str | None) -> str | None:
    """A catalogue colour named in a goods description ("... colour Navy Blue")."""
    s = squash(text)
    best = [n for n, _ in COLOUR_NAMES if squash(n) in s]
    return max(best, key=len) if best else None


def photo_match(t: DocView, pack: Pack) -> Outcome | None:
    if t.doc_type != "PRODUCTION_PHOTO":
        return None
    code = "PHOTO_MATCH"
    spec_text = None
    for dt in ("PROFORMA_INVOICE", "COMMERCIAL_INVOICE"):
        spec_text = g(pack.get(dt), "goods_description")
        if spec_text:
            break
    wanted = spec_colour(spec_text)
    if wanted is None:
        return _skip(code, "no ordered colour in the goods description")
    if t.photo_colour is None:
        return _skip(code, "photo could not be analysed")
    _, mean_rgb, _ = t.photo_colour
    seen_name, _ = nearest_colour(mean_rgb)
    want_rgb = dict(COLOUR_NAMES)[wanted]
    dist = colour_distance(mean_rgb, want_rgb)
    detail = {"ordered_colour": wanted, "looks_like": seen_name, "distance": dist,
              "width_label": "not checked (needs OCR or the vision model)"}  # fmt: skip
    if seen_name == wanted and dist <= PHOTO_PASS_DISTANCE:
        return Outcome(code, "PASS", detail)
    if seen_name == wanted and dist <= PHOTO_WARN_DISTANCE:
        return Outcome(code, "WARN", detail)
    return Outcome(code, "FAIL", detail)


# --- entry point ------------------------------------------------------------------------------


def run_checks(
    target: DocView,
    pack: Pack,
    ctx: DealContext,
    *,
    tol: Tolerances = Tolerances(),  # noqa: B008
    name_match_threshold: float = 92.0,
    name_partial_threshold: float = 80.0,
    registry_status: str | None = None,
    registry_detail: dict[str, Any] | None = None,
) -> list[Outcome]:
    """All checks that apply to `target`, in a stable order. The target stands for its own type in
    the pack, so an older upload of the same type is checked against the pack as it would be."""
    if target.doc_type != "PRODUCTION_PHOTO":
        pinned = target.doc_type == "PROFORMA_INVOICE" and pack.reference not in (None, target)
        if not pinned and target.doc_type != "OTHER":
            pack = Pack(
                docs={**pack.docs, target.doc_type: target},
                photos=pack.photos,
                reference=pack.reference,
            )
    if target.doc_type == "PRODUCTION_PHOTO":
        outs = [photo_match(target, pack), duplicate_hash(registry_status, registry_detail)]
        return [o for o in outs if o is not None]
    outs = [
        extraction_complete(target),
        reference_changed(target, pack),
        quantity_match(target, pack, ctx, tol) if target.doc_type in (*PDF_TYPES,) else None,
        value_math(target, tol),
        value_match(target, pack, ctx, tol),
        name_match(target, ctx, name_match_threshold, name_partial_threshold),
        beneficiary_match(target, ctx),
        vessel_voyage_match(target, pack, ctx),
        date_logic(target, pack, ctx, tol),
        port_match(target, ctx),
        hs_code_match(target, pack, ctx),
        price_band(target, ctx),
        hidden_text(target),
        instruction_scan(target),
        metadata_anomaly(target, pack),
        duplicate_hash(registry_status, registry_detail),
    ]
    return [o for o in outs if o is not None]
