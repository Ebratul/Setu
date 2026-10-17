"""Build analysed packs in memory from the synthetic factory (no data/generated needed)."""

import io
import random
from collections.abc import Callable

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.forensics.analyze import analyze_pdf
from app.forensics.context import DealContext, DocView, Pack
from app.forensics.pack_loader import deal_context
from synthetic import tamper
from synthetic.factory import buyer_pool, clean_pack, supplier_pool
from synthetic.models import Pack as SynthPack
from synthetic.render_pdf import render_document

SEED = 11


def synth_pack(index: int = 0, mutate: Callable[[SynthPack], object] | None = None) -> SynthPack:
    pack = clean_pack(SEED, index, supplier_pool(SEED), buyer_pool(SEED))
    if mutate:
        mutate(pack)
    return pack


def tampered(fraud_type: str, index: int = 0, diff: str = "obvious") -> SynthPack:
    pack = synth_pack(index)
    tamper.apply(fraud_type, pack, random.Random(index), diff)  # type: ignore[arg-type]
    return pack


def analysed(pack: SynthPack) -> tuple[Pack, DealContext]:
    docs: dict[str, DocView] = {}
    for i, (_, doc) in enumerate(pack.pdf_docs()):
        data = render_document(doc, pack.style, i)
        view = analyze_pdf(data, doc.doc_type).view
        docs[doc.doc_type] = view
    ctx = deal_context(pack.deal.model_dump(mode="json"))
    return Pack(docs=docs), ctx


def make_pdf(
    lines: list[str],
    *,
    hidden: list[tuple[str, tuple[float, float, float], float]] | None = None,
    subject: str = "",
    keywords: str = "",
    title: str = "Test",
    cmyk_white: str | None = None,
    gray_white: str | None = None,
    offpage: str | None = None,
    on_dark: str | None = None,
    producer: str | None = None,
    pages: int = 1,
    page_lines: dict[int, list[str]] | None = None,
) -> bytes:
    """A one-page PDF: black text lines, plus the hidden variants a forger might use."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1, pageCompression=0)
    c.setTitle(title)
    c.setSubject(subject)
    c.setKeywords(keywords)
    if producer:
        c.setProducer(producer)
    y = 780
    c.setFont("Helvetica", 10)
    for line in lines:
        c.drawString(40, y, line)
        y -= 14
    for text, rgb, size in hidden or []:
        c.setFillColorRGB(*rgb)
        c.setFont("Helvetica", size)
        c.drawString(40, 60, text)
    if cmyk_white:
        c.setFillColorCMYK(0, 0, 0, 0)
        c.setFont("Helvetica", 9)
        c.drawString(40, 70, cmyk_white)
    if gray_white:
        c.setFillGray(1)
        c.setFont("Helvetica", 9)
        c.drawString(40, 80, gray_white)
    if offpage:
        c.setFillGray(0)
        c.setFont("Helvetica", 9)
        c.drawString(-200, 400, offpage)
    if on_dark:
        c.setFillColorRGB(0.1, 0.1, 0.4)
        c.rect(40, 200, 200, 20, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 10)
        c.drawString(44, 206, on_dark)
    c.showPage()
    for n in range(2, pages + 1):
        c.setFillGray(0)
        c.setFont("Helvetica", 10)
        y = 780
        for line in (page_lines or {}).get(n, [f"page {n}"]):
            c.drawString(40, y, line)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()
