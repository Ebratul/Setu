"""PDF rendering with reportlab (BSD). Output has a real, extractable text layer.

Layout is fixed per document type (labelled `Label: value` lines, so pdfplumber extraction is
reliable) with small seeded variations: font, date format, and the order of fields/sections.
`invariant=1` makes the bytes depend only on the input, which the determinism test relies on.
"""

import io
import random
from datetime import date
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from synthetic.catalog import FOOTER
from synthetic.models import (
    BillOfEntryDoc,
    BillOfLadingDoc,
    CertOfOriginDoc,
    DocBase,
    HiddenText,
    InvoiceDoc,
    Pack,
    PackingListDoc,
    Party,
    RenderStyle,
)

Section = tuple[str, list[tuple[str, str]]]

PAGE_W, PAGE_H = A4
MARGIN = 42.0
CJK_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))

FONT_ORDER = ("helvetica", "times", "courier")
FONTS = {
    "helvetica": ("Helvetica", "Helvetica-Bold"),
    "times": ("Times-Roman", "Times-Bold"),
    "courier": ("Courier", "Courier-Bold"),
}


def fmt_date(d: date, pattern: str) -> str:
    return d.strftime(pattern)


def fmt_num(value: Decimal) -> str:
    return format(value, ",f")


def fmt_money(value: Decimal, currency: str = "USD") -> str:
    return f"{currency} {fmt_num(value)}"


def _party(p: Party) -> str:
    return f"{p.name}, {p.address}"


def _is_cjk(text: str) -> bool:
    """True when the standard Latin fonts cannot draw the text (CJK, Cyrillic homoglyphs, ...)."""
    return any(ord(ch) > 0xFF and ch not in "\u2013\u2014\u2019" for ch in text)


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Word wrap; CJK text has no spaces, so it wraps per character."""
    if not _is_cjk(text):
        return simpleSplit(text, font, size, width) or [""]
    lines, current = [], ""
    for ch in text:
        if stringWidth(current + ch, font, size) > width:
            lines.append(current)
            current = ch
        else:
            current += ch
    return [*lines, current]


# ---- sections per document type ---------------------------------------------------------------
def _invoice_sections(inv: InvoiceDoc, st: RenderStyle) -> tuple[str, str, list[Section]]:
    d = lambda x: fmt_date(x, st.date_fmt)  # noqa: E731
    title = "PROFORMA INVOICE" if inv.doc_type == "PROFORMA_INVOICE" else "COMMERCIAL INVOICE"
    sections: list[Section] = [
        ("Document", [("Invoice no.", inv.invoice_no), ("Invoice date", d(inv.date))]),
        (
            "Seller",
            [
                ("Seller", inv.seller.name),
                ("Seller address", inv.seller.address),
                ("Seller licence no.", inv.seller.license_no or "-"),
            ],
        ),
        (
            "Buyer",
            [
                ("Buyer", inv.buyer.name),
                ("Buyer address", inv.buyer.address),
                ("Buyer licence no.", inv.buyer.license_no or "-"),
            ],
        ),
        (
            "Goods",
            [
                ("Goods description", inv.goods_description),
                ("HS code", inv.hs_code),
                ("Quantity", f"{fmt_num(inv.quantity)} {inv.unit}"),
                ("Unit price", f"{fmt_money(inv.unit_price, inv.currency)} per {inv.unit}"),
                ("Total amount", fmt_money(inv.total, inv.currency)),
            ],
        ),
        (
            "Terms",
            [
                ("Incoterm", inv.incoterm),
                ("Payment terms", inv.payment_terms),
                ("Port of loading", inv.port_of_loading),
                ("Port of discharge", inv.port_of_discharge),
            ],
        ),
    ]
    if inv.schedule:
        s = inv.schedule
        sections.append(
            (
                "Shipment schedule",
                [
                    ("Booked vessel / voyage", f"{s.booked_vessel} / {s.booked_voyage}"),
                    ("Production completion", d(s.production_complete)),
                    ("Estimated shipment date", d(s.est_ship_date)),
                    ("Estimated arrival", d(s.eta)),
                ],
            )
        )
    b = inv.bank
    sections.append(
        (
            "Seller bank details",
            [
                ("Bank name", b.bank_name),
                ("Account holder", b.holder_name),
                ("Account no.", b.account_masked),
                ("SWIFT code", b.swift),
            ],
        )
    )
    return title, inv.seller.name, sections


def _pl_sections(pl: PackingListDoc, st: RenderStyle) -> tuple[str, str, list[Section]]:
    return (
        "PACKING LIST",
        pl.seller.name,
        [
            (
                "Document",
                [
                    ("Packing list no.", pl.pl_no),
                    ("Date", fmt_date(pl.date, st.date_fmt)),
                    ("Invoice no.", pl.invoice_no),
                ],
            ),
            ("Seller", [("Seller", pl.seller.name), ("Seller address", pl.seller.address)]),
            ("Buyer", [("Buyer", pl.buyer.name), ("Buyer address", pl.buyer.address)]),
            (
                "Goods",
                [
                    ("Goods description", pl.goods_description),
                    ("Packages", f"{pl.packages} {pl.package_type}"),
                    ("Quantity", f"{fmt_num(pl.quantity)} {pl.unit}"),
                    ("Net weight", f"{fmt_num(pl.net_weight_kg)} kg"),
                    ("Gross weight", f"{fmt_num(pl.gross_weight_kg)} kg"),
                    ("Shipping marks", pl.marks),
                ],
            ),
        ],
    )


def _bl_sections(bl: BillOfLadingDoc, st: RenderStyle) -> tuple[str, str, list[Section]]:
    return (
        "BILL OF LADING",
        bl.carrier,
        [
            ("Document", [("B/L no.", bl.bl_no), ("Carrier", bl.carrier)]),
            (
                "Parties",
                [
                    ("Shipper", _party(bl.shipper)),
                    ("Consignee", _party(bl.consignee)),
                    ("Notify party", _party(bl.notify_party)),
                ],
            ),
            (
                "Voyage",
                [
                    ("Vessel", bl.vessel),
                    ("Voyage no.", bl.voyage),
                    ("Port of loading", bl.port_of_loading),
                    ("Port of discharge", bl.port_of_discharge),
                    ("On board date", fmt_date(bl.on_board_date, st.date_fmt)),
                ],
            ),
            (
                "Cargo",
                [
                    ("Container no.", bl.container_no),
                    ("Description of goods", bl.description),
                    ("Packages", f"{bl.packages} {bl.package_type}"),
                    ("Quantity", f"{fmt_num(bl.quantity)} {bl.unit}"),
                    ("Gross weight", f"{fmt_num(bl.gross_weight_kg)} kg"),
                    ("Freight terms", bl.freight_terms),
                ],
            ),
        ],
    )


def _coo_sections(c: CertOfOriginDoc, st: RenderStyle) -> tuple[str, str, list[Section]]:
    return (
        "CERTIFICATE OF ORIGIN",
        c.issuing_body,
        [
            (
                "Document",
                [
                    ("Certificate no.", c.coo_no),
                    ("Date of issue", fmt_date(c.issue_date, st.date_fmt)),
                    ("Issued by", c.issuing_body),
                ],
            ),
            ("Exporter", [("Exporter", _party(c.exporter))]),
            ("Consignee", [("Consignee", _party(c.consignee))]),
            (
                "Goods",
                [
                    ("Country of origin", c.origin_country),
                    ("HS code", c.hs_code),
                    ("Description of goods", c.description),
                    ("Quantity", f"{fmt_num(c.quantity)} {c.unit}"),
                ],
            ),
        ],
    )


def _boe_sections(b: BillOfEntryDoc, st: RenderStyle) -> tuple[str, str, list[Section]]:
    return (
        "BILL OF ENTRY",
        "Customs House (simulated)",
        [
            (
                "Document",
                [
                    ("Bill of entry no.", b.boe_no),
                    ("Date", fmt_date(b.date, st.date_fmt)),
                    ("Port", b.port),
                    ("B/L no.", b.bl_no),
                ],
            ),
            ("Importer", [("Importer", _party(b.importer))]),
            (
                "Goods",
                [
                    ("HS code", b.hs_code),
                    ("Description of goods", b.description),
                    ("Quantity", f"{fmt_num(b.quantity)} {b.unit}"),
                ],
            ),
            (
                "Assessment",
                [
                    ("Assessed value", fmt_money(b.assessed_value_usd)),
                    ("Duty payable", fmt_money(b.duty_usd)),
                    ("Exchange rate", f"USD/BDT {b.fx_usd_bdt}"),
                    ("Assessed value (BDT)", fmt_money(b.assessed_value_bdt, "BDT")),
                    ("Duty payable (BDT)", fmt_money(b.duty_bdt, "BDT")),
                ],
            ),
        ],
    )


def sections_for(doc: DocBase, st: RenderStyle) -> tuple[str, str, list[Section]]:
    """(title, issuer, sections) for a document, including the visible notes section."""
    if isinstance(doc, InvoiceDoc):
        title, issuer, sections = _invoice_sections(doc, st)
    elif isinstance(doc, PackingListDoc):
        title, issuer, sections = _pl_sections(doc, st)
    elif isinstance(doc, BillOfLadingDoc):
        title, issuer, sections = _bl_sections(doc, st)
    elif isinstance(doc, CertOfOriginDoc):
        title, issuer, sections = _coo_sections(doc, st)
    elif isinstance(doc, BillOfEntryDoc):
        title, issuer, sections = _boe_sections(doc, st)
    else:  # pragma: no cover
        raise TypeError(type(doc))
    if doc.notes:
        sections.append(("Notes", [("Notes", doc.notes)]))
    return title, issuer, sections


def _vary(sections: list[Section], rng: random.Random) -> list[Section]:
    """Seeded layout variation: swap the two party blocks, and shuffle fields in some sections."""
    out = [(name, list(fields)) for name, fields in sections]
    if rng.random() < 0.3:
        names = [n for n, _ in out]
        if "Seller" in names and "Buyer" in names:
            i, j = names.index("Seller"), names.index("Buyer")
            out[i], out[j] = out[j], out[i]
    for name, fields in out:
        if name != "Notes" and len(fields) > 2 and rng.random() < 0.4:
            rng.shuffle(fields)
    return out


# ---- drawing --------------------------------------------------------------------------------
def _font_for(style: RenderStyle, doc_index: int) -> tuple[str, str]:
    return FONTS[FONT_ORDER[(FONT_ORDER.index(style.font) + doc_index) % 3]]


def _draw_value_lines(
    c: canvas.Canvas, label: str, value: str, y: float, fonts: tuple[str, str], size: float
) -> float:
    regular, bold = fonts
    prefix = f"{label}: "
    pw = stringWidth(prefix, bold, size)
    width = PAGE_W - 2 * MARGIN
    font = CJK_FONT if _is_cjk(value) else regular
    lines = wrap(value, font, size, width - pw)
    c.setFont(bold, size)
    c.drawString(MARGIN, y, prefix)
    for line in lines:
        c.setFont(font, size)
        c.drawString(MARGIN + pw, y, line)
        y -= size + 3
    return y


def _draw_goods_table(c: canvas.Canvas, inv: InvoiceDoc, y: float, fonts: tuple[str, str]) -> float:
    regular, bold = fonts
    cols = [("Item", 0), ("HS code", 215), ("Quantity", 285), ("Unit price", 365), ("Amount", 445)]
    c.setStrokeGray(0.55)
    c.setLineWidth(0.5)
    c.rect(MARGIN, y - 30, PAGE_W - 2 * MARGIN, 30)
    c.line(MARGIN, y - 15, PAGE_W - MARGIN, y - 15)
    item = inv.goods_description.split(",")[0]
    cells = [
        item,
        inv.hs_code,
        f"{fmt_num(inv.quantity)} {inv.unit}",
        fmt_num(inv.unit_price),
        fmt_num(inv.total),
    ]
    for (name, dx), cell in zip(cols, cells, strict=True):
        c.setFont(bold, 8)
        c.drawString(MARGIN + 4 + dx, y - 11, name)
        c.setFont(regular, 8)
        c.drawString(MARGIN + 4 + dx, y - 26, cell)
    return y - 44


def _draw_hidden(c: canvas.Canvas, h: HiddenText) -> None:
    c.setFillColorRGB(*h.color)
    font = CJK_FONT if _is_cjk(h.text) else "Helvetica"
    c.setFont(font, h.size)
    y = h.y
    for line in wrap(h.text, font, h.size, PAGE_W - h.x - MARGIN):
        c.drawString(h.x, y, line)
        y -= h.size + 1
    c.setFillGray(0)


def render_document(doc: DocBase, style: RenderStyle, doc_index: int = 0) -> bytes:
    """Render one document to PDF bytes. `doc_index` rotates the font so documents differ."""
    title, issuer, sections = sections_for(doc, style)
    rng = random.Random(f"layout:{style.order_seed}:{doc_index}")
    sections = _vary(sections, rng)
    fonts = _font_for(style, doc_index)
    regular, bold = fonts
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=0)
    c.setTitle(doc.meta_title or title.title())
    c.setAuthor(issuer)
    c.setSubject(doc.meta_subject or "")
    c.setKeywords(doc.meta_keywords or "")
    c.setCreator("Setu synthetic document generator")
    c.setProducer(style.producer)

    y = PAGE_H - MARGIN - 6
    c.setFont(bold, 14)
    c.drawString(MARGIN, y, issuer)
    y -= 26
    c.setFont(bold, 17)
    c.drawCentredString(PAGE_W / 2, y, title)
    c.setStrokeGray(0.3)
    c.line(MARGIN, y - 8, PAGE_W - MARGIN, y - 8)
    y -= 28
    table_done = not isinstance(doc, InvoiceDoc)
    for name, fields in sections:
        c.setFont(bold, 9)
        c.setFillGray(0.35)
        c.drawString(MARGIN, y, name.upper())
        c.setFillGray(0)
        y -= 13
        for label, value in fields:
            y = _draw_value_lines(c, label, value, y, fonts, 9.5)
        y -= 6
        if name == "Goods" and not table_done and isinstance(doc, InvoiceDoc):
            y = _draw_goods_table(c, doc, y, fonts)
            table_done = True
    c.setFont(regular, 9)
    c.drawString(MARGIN, 96, "Authorised signatory: ______________________")
    c.setStrokeGray(0.6)
    c.rect(PAGE_W - MARGIN - 110, 80, 110, 34)
    c.setFont(bold, 8)
    c.setFillGray(0.4)
    c.drawCentredString(PAGE_W - MARGIN - 55, 94, "SIMULATED STAMP")
    c.setFillGray(0.45)
    c.setFont(regular, 7)
    c.drawCentredString(PAGE_W / 2, 30, FOOTER)
    c.setFillGray(0)
    for hidden in doc.hidden:
        _draw_hidden(c, hidden)
    c.showPage()
    c.save()
    return buf.getvalue()


def render_pack_pdfs(pack: Pack) -> dict[str, bytes]:
    return {
        stem: render_document(doc, pack.style, i) for i, (stem, doc) in enumerate(pack.pdf_docs())
    }
