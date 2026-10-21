"""PDF text layer with per-character colour and size (pdfplumber).

Visible text and hidden spans are separated at the character level. Hidden spans are reported,
never used as content. PDF metadata is untrusted text: it is cleaned, capped and returned for
scanning, never as extraction content.
"""

import contextlib
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pdfplumber

NEAR_WHITE = 0.9  # every RGB channel at or above this counts as white
TINY_PT = 2.0  # font size at or below this is unreadable
MAX_PAGES = 100  # pages scanned for hidden text and instructions
MAX_CHARS = 200_000  # the page that crosses this is finished, then reading stops
MAX_STREAM = 5_000_000
LOW_CONTRAST = 1.5  # WCAG-style luminance ratio below which text is practically unreadable
HARD_REASONS = frozenset({"WHITE_TEXT", "TINY_TEXT", "OFF_PAGE", "INVISIBLE_RENDER"})
META_KEYS = ("Producer", "Creator", "Title", "Subject", "Keywords", "Author")
META_CHARS = 500
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

Colour = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class HiddenSpan:
    text: str
    page: int
    bbox: tuple[float, float, float, float]  # x0, top, x1, bottom (points)
    colour: Colour | None
    size: float
    reason: (
        str  # WHITE_TEXT | TINY_TEXT | OFF_PAGE | INVISIBLE_RENDER | COVERED_TEXT | LOW_CONTRAST
    )
    page_width: float = 0.0  # PDF points, so a viewer can scale the bbox
    page_height: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "bbox": [round(v, 2) for v in self.bbox],
            "colour": None if self.colour is None else [round(c, 3) for c in self.colour],
            "size": round(self.size, 2),
            "reason": self.reason,
            "page_width": round(self.page_width, 2),
            "page_height": round(self.page_height, 2),
        }


@dataclass(slots=True)
class PdfText:
    visible_text: str
    hidden_spans: list[HiddenSpan]
    metadata: dict[str, str]
    created: datetime | None
    modified: datetime | None
    pages: int
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def to_rgb(value: Any) -> Colour | None:
    """Gray, RGB or CMYK fill colour as RGB in 0..1; None when unknown (pattern, missing)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        value = (float(value),)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return None
    try:
        nums = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if len(nums) == 1:
        g = nums[0]
        return (g, g, g)
    if len(nums) == 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 4:
        c, m, y, k = nums
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def is_near_white(colour: Colour | None) -> bool:
    return colour is not None and all(ch >= NEAR_WHITE for ch in colour)


def _filled_rects(page: Any) -> list[tuple[float, float, float, float]]:
    """Rectangles filled with a clearly non-white colour (white text on them is readable)."""
    out = []
    for r in page.rects:
        if not r.get("fill"):
            continue
        rgb = to_rgb(r.get("non_stroking_color"))
        if rgb is not None and not is_near_white(rgb):
            out.append((r["x0"], r["top"], r["x1"], r["bottom"]))
    return out


def _on_dark_fill(ch: dict[str, Any], rects: list[tuple[float, float, float, float]]) -> bool:
    cx, cy = (ch["x0"] + ch["x1"]) / 2, (ch["top"] + ch["bottom"]) / 2
    return any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in rects)


def hidden_reason(
    ch: dict[str, Any], page_w: float, page_h: float, rects: list[tuple[float, float, float, float]]
) -> str | None:
    if ch["x1"] < 0 or ch["x0"] > page_w or ch["bottom"] < 0 or ch["top"] > page_h:
        return "OFF_PAGE"
    if float(ch.get("size") or 0) <= TINY_PT:
        return "TINY_TEXT"
    rgb = to_rgb(ch.get("non_stroking_color"))
    if is_near_white(rgb) and not _on_dark_fill(ch, rects):
        return "WHITE_TEXT"
    return None


def _spans(
    chars: list[dict[str, Any]], page_no: int, page_w: float = 0.0, page_h: float = 0.0
) -> list[HiddenSpan]:
    """Group hidden characters into lines of text with a bounding box."""
    spans: list[HiddenSpan] = []
    ordered = sorted(chars, key=lambda c: (round(c["top"] / 3), c["x0"]))
    cur: list[dict[str, Any]] = []

    def flush() -> None:
        if not cur:
            return
        text = "".join(c["text"] for c in cur)
        if text.strip():
            first = cur[0]
            spans.append(
                HiddenSpan(
                    text=text.strip(),
                    page=page_no,
                    bbox=(
                        min(c["x0"] for c in cur),
                        min(c["top"] for c in cur),
                        max(c["x1"] for c in cur),
                        max(c["bottom"] for c in cur),
                    ),
                    colour=to_rgb(first.get("non_stroking_color")),
                    size=float(first.get("size") or 0),
                    reason=cast_reason(first),
                    page_width=page_w,
                    page_height=page_h,
                )
            )
        cur.clear()

    for c in ordered:
        if cur:
            prev = cur[-1]
            same_line = abs(c["top"] - prev["top"]) <= max(2.0, prev["size"] * 0.5)
            gap = c["x0"] - prev["x1"]
            if (
                not same_line
                or gap > max(12.0, prev["size"] * 4)
                or c["_reason"] != prev["_reason"]
            ):
                flush()
            elif gap > prev["size"] * 0.25 and not prev["text"].isspace():
                cur.append({**c, "text": " " + c["text"]} if not c["text"].isspace() else c)
                continue
        cur.append(c)
    flush()
    return spans


def cast_reason(ch: dict[str, Any]) -> str:
    return str(ch["_reason"])


def _clean_meta(value: Any) -> str:
    text = _CONTROL.sub(" ", str(value))
    return " ".join(text.split())[:META_CHARS]


def _pdf_date(value: Any) -> datetime | None:
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", str(value or ""))
    if not m:
        return None
    parts = [int(g) if g else d for g, d in zip(m.groups(), (0, 1, 1, 0, 0, 0), strict=True)]
    try:
        return datetime(*parts, tzinfo=UTC)
    except ValueError:
        return None


def _luminance(rgb: Colour) -> float:
    def lin(c: float) -> float:
        c = min(max(c, 0.0), 1.0)
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Colour, b: Colour) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _flatten(objs: Any) -> list[Any]:
    out: list[Any] = []
    for o in objs:
        children = getattr(o, "_objs", None)
        if children is not None and o.__class__.__name__ not in ("LTChar", "LTAnno"):
            out.extend(_flatten(children))
        else:
            out.append(o)
    return out


def _char_key(x0: float, top: float, text: str) -> tuple[float, float, str]:
    return (round(x0, 1), round(top, 1), text)


def layout_findings(page: Any, page_h: float) -> list[dict[str, Any]]:
    """Characters that are drawn but unreadable because of what is painted around them, in paint
    order: covered by a LATER filled rectangle or image (COVERED_TEXT), or with almost no contrast
    against the filled box underneath or the white page (LOW_CONTRAST)."""
    items = _flatten(page.layout._objs)
    found: list[dict[str, Any]] = []
    painted: list[tuple[int, Any]] = [
        (i, o)
        for i, o in enumerate(items)
        if o.__class__.__name__ in ("LTRect", "LTImage", "LTFigure")
        and (o.__class__.__name__ != "LTRect" or getattr(o, "fill", False))
    ]
    for i, o in enumerate(items):
        if o.__class__.__name__ != "LTChar" or not o.get_text().strip():
            continue
        area = max((o.x1 - o.x0) * (o.y1 - o.y0), 1e-6)
        colour = to_rgb(getattr(o.graphicstate, "ncolor", None)) or (0.0, 0.0, 0.0)
        reason = None
        under: Colour = (1.0, 1.0, 1.0)
        for j, r in painted:
            ow = min(o.x1, r.x1) - max(o.x0, r.x0)
            oh = min(o.y1, r.y1) - max(o.y0, r.y0)
            if ow <= 0 or oh <= 0 or ow * oh < 0.9 * area:
                continue
            if j > i:
                reason = "COVERED_TEXT"
                break
            fill = to_rgb(getattr(r, "non_stroking_color", None))
            if fill is not None:
                under = fill
        if reason is None and contrast(colour, under) < LOW_CONTRAST and not is_near_white(colour):
            reason = "LOW_CONTRAST"
        if reason:
            found.append(
                {
                    "x0": o.x0,
                    "x1": o.x1,
                    "top": page_h - o.y1,
                    "bottom": page_h - o.y0,
                    "size": o.size,
                    "text": o.get_text(),
                    "non_stroking_color": getattr(o.graphicstate, "ncolor", None),
                    "_reason": reason,
                }
            )
    return found


_TOKEN = re.compile(
    rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]()<>]*|[-+]?\d*\.?\d+"
    rb"|[A-Za-z'\"*]+|%[^\n]*",
    re.S,
)
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _pdf_string(token: bytes) -> str:
    if token.startswith(b"<"):
        hexed = re.sub(rb"\s", b"", token[1:-1])
        raw = bytes.fromhex(hexed.decode() + ("0" if len(hexed) % 2 else ""))
        text = (
            raw.decode("utf-16-be", "ignore") if raw[:2] == b"\xfe\xff" else raw.decode("latin-1")
        )
    else:
        body = token[1:-1]
        out = bytearray()
        i = 0
        while i < len(body):
            c = body[i : i + 1]
            if c == b"\\" and i + 1 < len(body):
                nxt = body[i + 1 : i + 2]
                if nxt.isdigit():
                    m = re.match(rb"[0-7]{1,3}", body[i + 1 :])
                    out.append(int(m.group(0), 8) & 0xFF if m else 0)  # type: ignore[union-attr]
                    i += 1 + (len(m.group(0)) if m else 1)
                    continue
                out += _ESC.get(nxt, nxt)
                i += 2
                continue
            out += c
            i += 1
        text = bytes(out).decode("latin-1")
    printable = sum(ch.isprintable() or ch.isspace() for ch in text)
    return text if text and printable / len(text) > 0.8 else ""


def invisible_strings(stream: bytes) -> list[str]:
    """Strings shown while the text render mode is 3 (neither filled nor stroked)."""
    mode, stack, operands = 0, [], []
    found: list[str] = []
    for m in _TOKEN.finditer(stream):
        tok = m.group(0)
        if tok.startswith(b"%"):
            continue
        if tok[:1] in (b"(", b"<", b"[", b"]", b"/") or re.match(rb"[-+]?\d*\.?\d+$", tok):
            operands.append(tok)
            continue
        op = tok
        if op == b"Tr" and operands:
            with contextlib.suppress(ValueError):
                mode = int(float(operands[-1]))
        elif op == b"q":
            stack.append(mode)
        elif op == b"Q" and stack:
            mode = stack.pop()
        elif op in (b"Tj", b"'", b'"', b"TJ") and mode == 3:
            start = max((k for k, t in enumerate(operands) if t == b"["), default=-1)
            shown = operands[start + 1 :] if op == b"TJ" and start >= 0 else operands[-1:]
            text = "".join(_pdf_string(t) for t in shown if t[:1] in (b"(", b"<") and t != b"<")
            if text.strip():
                found.append(text.strip())
        operands = []
    return found


def _invisible_text(page: Any) -> list[str]:
    from pdfminer.pdftypes import resolve1

    contents = resolve1(page.page_obj.contents)
    streams = contents if isinstance(contents, list) else [contents]
    out: list[str] = []
    for ref in streams:
        data = resolve1(ref).get_data()
        if len(data) <= MAX_STREAM:
            out.extend(invisible_strings(data))
    return out


def read_pdf(data: bytes) -> PdfText:
    """Visible text (hidden characters removed), hidden spans and cleaned metadata. Every page up
    to MAX_PAGES is scanned; the page that crosses MAX_CHARS is finished, then reading stops and
    the result is marked truncated (EXTRACTION_COMPLETE warns)."""
    visible: list[str] = []
    hidden: list[HiddenSpan] = []
    warnings: list[str] = []
    total_chars = 0
    truncated = False
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        raw_meta = pdf.metadata or {}
        meta = {k: _clean_meta(raw_meta[k]) for k in META_KEYS if raw_meta.get(k)}
        created, modified = (
            _pdf_date(raw_meta.get("CreationDate")),
            _pdf_date(raw_meta.get("ModDate")),
        )
        pages = len(pdf.pages)
        for number, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            w, h = float(page.width), float(page.height)
            rects = _filled_rects(page)
            hidden_chars: list[dict[str, Any]] = []
            keys: set[tuple[float, float, str]] = set()
            chars = page.chars
            total_chars += len(chars)
            for ch in chars:
                reason = hidden_reason(ch, w, h, rects)
                if reason:
                    hidden_chars.append({**ch, "_reason": reason})
                    keys.add(_char_key(ch["x0"], ch["top"], ch["text"]))
            try:
                for item in layout_findings(page, h):
                    key = _char_key(item["x0"], item["top"], item["text"])
                    if key not in keys:
                        hidden_chars.append(item)
                        if item["_reason"] == "COVERED_TEXT":
                            keys.add(key)
            except Exception:  # layout analysis is best effort; the colour/size rules still ran
                warnings.append("LAYOUT_ANALYSIS_FAILED")
            hidden.extend(_spans(hidden_chars, number, w, h))
            kept = page.filter(
                lambda o, keys=keys: (
                    o.get("object_type") != "char"
                    or _char_key(o["x0"], o["top"], o["text"]) not in keys
                )
            )
            page_text = kept.extract_text() or ""
            try:
                for text in _invisible_text(page):
                    hidden.append(
                        HiddenSpan(text, number, (0, 0, 0, 0), None, 0.0, "INVISIBLE_RENDER", w, h)
                    )
                    page_text = page_text.replace(text, "", 1)
            except Exception:
                warnings.append("CONTENT_STREAM_UNREADABLE")
            visible.append(page_text)
            if total_chars > MAX_CHARS and number < min(pages, MAX_PAGES):
                truncated = True
                warnings.append("TEXT_TRUNCATED")
                break
    if pages > MAX_PAGES:
        truncated = True
        warnings.append("PAGES_TRUNCATED")
    return PdfText(
        visible_text="\n".join(visible),
        hidden_spans=hidden,
        metadata=meta,
        created=created,
        modified=modified,
        pages=pages,
        truncated=truncated,
        warnings=warnings,
    )


def to_dict(t: PdfText) -> dict[str, Any]:
    return {
        "visible_text": t.visible_text,
        "hidden_spans": [s.as_dict() for s in t.hidden_spans],
        "metadata": t.metadata,
        "created": t.created.isoformat() if t.created else None,
        "modified": t.modified.isoformat() if t.modified else None,
        "pages": t.pages,
        "truncated": t.truncated,
        "warnings": t.warnings,
    }


def from_dict(d: dict[str, Any]) -> PdfText:
    return PdfText(
        visible_text=d["visible_text"],
        hidden_spans=[
            HiddenSpan(
                s["text"],
                s["page"],
                tuple(s["bbox"]),  # type: ignore[arg-type]
                tuple(s["colour"]) if s["colour"] else None,
                s["size"],
                s["reason"],
                s.get("page_width", 0.0),
                s.get("page_height", 0.0),
            )
            for s in d["hidden_spans"]
        ],
        metadata=d["metadata"],
        created=datetime.fromisoformat(d["created"]) if d["created"] else None,
        modified=datetime.fromisoformat(d["modified"]) if d["modified"] else None,
        pages=d["pages"],
        truncated=d["truncated"],
        warnings=d["warnings"],
    )
