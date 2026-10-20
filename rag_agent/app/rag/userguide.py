"""Convert the in-app user guide (frontend/content/docs/<lang>/<section>/<name>.mdx) into KB
markdown sources (kb/sources/generated/user-guide/<lang>-<section>-<name>.md).

Deterministic and pure apart from file reads/writes: same MDX -> same bytes. EN and BN only (the
chat answers in en/bn). Heading anchors (`\\{#id}`) are kept as `{#id}` so the chunker can record
them and a citation can deep-link to `#id`.
"""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

LANGS = ("en", "bn")
OUT_DIRNAME = "user-guide"
SOURCE_TYPE = "user_guide"
DOCS_URL_PREFIX = "/docs"

_COMMENT = re.compile(r"\{/\*.*?\*/\}", re.S)
_ATTR = re.compile(r'(\w+)=(?:"([^"]*)"|\{([^}]*)\})')
_STEPS = re.compile(r"<Steps>(.*?)</Steps>", re.S)
_STEP = re.compile(r"<Step\b([^>]*)>(.*?)</Step>", re.S)
_CALLOUT = re.compile(r"<Callout\b([^>]*)>(.*?)</Callout>", re.S)
_FAQITEM = re.compile(r"<FAQItem\b([^>]*)>(.*?)</FAQItem>", re.S)
_SCREENSHOT = re.compile(r"<Screenshot\b([^>]*?)/>", re.S)
_ROLEBADGE = re.compile(r"<RoleBadge\b([^>]*?)/>")
_TIERBADGE = re.compile(r"<TierBadge\b([^>]*?)/>")
_TRYIT = re.compile(r"<TryItButton\b([^>]*?)/>", re.S)
_VIDEO = re.compile(r"<Video\b[^>]*?/>", re.S)
_KBD = re.compile(r"<Kbd>(.*?)</Kbd>", re.S)
_WRAPPERS = re.compile(r"</?(?:FAQ|Steps)>")
_ESCAPED = re.compile(r"\\([{}<>])")
_BLANKS = re.compile(r"\n{3,}")
_HEADING_ANCHOR = re.compile(r"^(#{1,6}\s+.*?)\s*\\\{#([A-Za-z0-9_\-]+)\}\s*$", re.M)

CALLOUT_LABELS = {"info": "Note", "tip": "Tip", "warning": "Warning", "security": "Security"}


class GuideError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Page:
    lang: str
    section: str
    name: str
    meta: dict[str, Any]
    body: str

    @property
    def page_id(self) -> str:
        return f"{self.section}/{self.name}"

    @property
    def url(self) -> str:
        return f"{DOCS_URL_PREFIX}/{self.lang}/{self.section}/{self.name}"

    @property
    def source_id(self) -> str:
        raw = f"user-guide-{self.lang}-{self.section}-{self.name}".lower()
        return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")

    @property
    def filename(self) -> str:
        return f"{self.lang}-{self.section}-{self.name}.md"


def _attrs(raw: str) -> dict[str, str]:
    return {
        m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)).strip()
        for m in _ATTR.finditer(raw)
    }


def _indent(text: str, pad: str) -> str:
    return "\n".join(pad + ln if ln.strip() else ln for ln in text.strip().splitlines())


def _steps(m: re.Match[str]) -> str:
    out: list[str] = []
    for n, s in enumerate(_STEP.finditer(m.group(1)), start=1):
        title = _attrs(s.group(1)).get("title", "")
        body = re.sub(r"\n\s*\n", "\n", s.group(2).strip())
        out.append(f"{n}. {title}".rstrip() + (f"\n{_indent(body, '   ')}" if body else ""))
    return "\n\n" + "\n".join(out) + "\n\n"


def _callout(m: re.Match[str]) -> str:
    a = _attrs(m.group(1))
    label = CALLOUT_LABELS.get(a.get("type", "info"), "Note")
    title = f" ({a['title']})" if a.get("title") else ""
    return f"\n\n{label}{title}: {' '.join(m.group(2).split())}\n\n"


def _faq(m: re.Match[str]) -> str:
    return f"\n\nQ: {_attrs(m.group(1)).get('q', '')}\nA: {m.group(2).strip()}\n\n"


def _screenshot(m: re.Match[str]) -> str:
    a = _attrs(m.group(1))
    text = a.get("alt", "")
    if a.get("caption") and a["caption"] != text:
        text = f"{text} {a['caption']}".strip()
    return f"\n\nScreen: {text}\n\n" if text else ""


def _role(m: re.Match[str]) -> str:
    return _attrs(m.group(1)).get("role", "").capitalize()


def _tier(m: re.Match[str]) -> str:
    return f"Tier {_attrs(m.group(1)).get('tier', '')}".strip()


def _tryit(m: re.Match[str]) -> str:
    a = _attrs(m.group(1))
    label = a.get("label", "Try it")
    return f"\n\n{label}: {a.get('href', '')}\n\n"


def mdx_to_markdown(body: str) -> str:
    """Strip MDX components/comments to plain markdown prose (heading anchors kept)."""
    t = _COMMENT.sub("", body)
    t = _HEADING_ANCHOR.sub(r"\1 {#\2}", t)
    t = _SCREENSHOT.sub(_screenshot, t)
    t = _CALLOUT.sub(_callout, t)
    t = _STEPS.sub(_steps, t)
    t = _FAQITEM.sub(_faq, t)
    t = _TRYIT.sub(_tryit, t)
    t = _VIDEO.sub("", t)
    t = _ROLEBADGE.sub(_role, t)
    t = _TIERBADGE.sub(_tier, t)
    t = _KBD.sub(r"\1", t)
    t = _WRAPPERS.sub("", t)
    t = _ESCAPED.sub(r"\1", t)
    t = "\n".join(ln.rstrip() for ln in t.splitlines())
    return _BLANKS.sub("\n\n", t).strip()


def parse_page(text: str, lang: str, section: str, name: str) -> Page:
    where = f"{lang}/{section}/{name}"
    if not text.startswith("---"):
        raise GuideError(f"{where}: missing front matter")
    try:
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise GuideError(f"{where}: bad front matter") from exc
    if not isinstance(meta, dict) or not meta.get("title") or not meta.get("updated"):
        raise GuideError(f"{where}: front matter needs title and updated")
    return Page(lang, section, name, meta, body)


def _scalar(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_page(page: Page) -> str:
    m = page.meta
    updated = m["updated"].isoformat() if isinstance(m["updated"], date) else str(m["updated"])
    head = [
        "---",
        f"id: {page.source_id}",
        f"title: {_scalar(str(m['title']))}",
        f"source_type: {SOURCE_TYPE}",
        f"original_reference: {_scalar(page.url)}",
        f"language: {page.lang}",
        f"last_reviewed: {updated}",
        "---",
    ]
    intro: list[str] = []
    if m.get("summary"):
        intro.append(str(m["summary"]).strip())
    roles = ", ".join(str(r) for r in m.get("roles") or [])
    routes = ", ".join(str(r) for r in m.get("routes") or [])
    if roles:
        intro.append(f"Roles: {roles}.")
    if routes:
        intro.append(f"App screens: {routes}.")
    body = mdx_to_markdown(page.body)
    parts = [*head, f"# {m['title']}", "", "\n".join(intro), "", body, ""]
    return "\n".join(parts).replace("\n\n\n", "\n\n")


def discover(docs_dir: Path, langs: tuple[str, ...] = LANGS) -> list[Page]:
    pages: list[Page] = []
    for lang in langs:
        for path in sorted((docs_dir / lang).glob("*/*.mdx")):
            pages.append(
                parse_page(path.read_text(encoding="utf-8"), lang, path.parent.name, path.stem)
            )
    return pages


def generate(docs_dir: Path, out_root: Path) -> tuple[int, int]:
    """Write sources under out_root/user-guide, drop stale ones. Returns (written, removed)."""
    out = out_root / OUT_DIRNAME
    out.mkdir(parents=True, exist_ok=True)
    wanted: dict[str, str] = {p.filename: render_page(p) for p in discover(docs_dir)}
    written = 0
    for fname, content in wanted.items():
        f = out / fname
        if not f.exists() or f.read_text(encoding="utf-8") != content:
            f.write_text(content, encoding="utf-8")
            written += 1
    removed = 0
    for f in out.glob("*.md"):
        if f.name not in wanted:
            f.unlink()
            removed += 1
    return written, removed


def guide_url(source_type: str, original_reference: str, anchor: str = "") -> str | None:
    """Public doc URL (+ #anchor) for user_guide sources; None for every other source type."""
    if source_type != SOURCE_TYPE or not original_reference:
        return None
    return f"{original_reference}#{anchor}" if anchor else original_reference
