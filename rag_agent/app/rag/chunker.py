"""Parse KB markdown sources (YAML front-matter + headings) and chunk them by heading.

Pure functions, no I/O beyond reading the file. Each chunk keeps the source title and its heading
path ("Title > Section > Subsection"); a section longer than `max_tokens` is split by paragraph
with a small overlap. Token counts are estimated (whitespace words × 1.3; good enough for sizing).
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

SourceType = Literal["regulation_summary", "glossary", "product_doc", "catalogue", "user_guide"]
SOURCE_TYPES = frozenset(
    {"regulation_summary", "glossary", "product_doc", "catalogue", "user_guide"}
)
LANGUAGES = frozenset({"en", "bn", "zh"})
REQUIRED = ("id", "title", "source_type", "original_reference", "language", "last_reviewed")
MAX_TOKENS = 450
MIN_TOKENS = 40
OVERLAP_TOKENS = 40
HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
ANCHOR = re.compile(r"\s*\{#([A-Za-z0-9_\-]+)\}\s*$")
SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{1,119}$")


class SourceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    title: str
    source_type: SourceType
    original_reference: str
    language: str
    last_reviewed: str
    disclaimer: str
    body: str
    path: str

    def meta(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "original_reference": self.original_reference,
            "last_reviewed": self.last_reviewed,
            "disclaimer": self.disclaimer,
            "path": self.path,
        }


@dataclass(frozen=True, slots=True)
class Chunk:
    source_id: str
    seq: int
    title: str
    heading_path: str
    content: str
    language: str
    meta: dict[str, Any] = field(default_factory=dict)
    # Set only by ingest.load_chunks for our generated user guide; never parsed from a source file.
    trusted: bool = False

    def content_hash(self, model_id: str) -> str:
        """Changes when the text, its place, the embedding model or the trust flag changes."""
        parts = (model_id, self.source_id, self.heading_path, self.content)
        raw = "\x1f".join((*parts, "trusted") if self.trusted else parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tokens(text: str) -> int:
    return int(len(text.split()) * 1.3)


def parse_source(text: str, path: str = "") -> Source:
    if not text.startswith("---"):
        raise SourceError(f"{path}: missing front-matter")
    try:
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    except (ValueError, yaml.YAMLError) as exc:
        raise SourceError(f"{path}: bad front-matter") from exc
    if not isinstance(meta, dict):
        raise SourceError(f"{path}: front-matter must be a mapping")
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise SourceError(f"{path}: missing {', '.join(missing)}")
    sid = str(meta["id"])
    if not SOURCE_ID.fullmatch(sid):
        raise SourceError(f"{path}: id must be lowercase letters, digits and dashes")
    if meta["language"] not in LANGUAGES:
        raise SourceError(f"{path}: language must be one of {sorted(LANGUAGES)}")
    if meta["source_type"] not in SOURCE_TYPES:
        raise SourceError(f"{path}: unknown source_type {meta['source_type']!r}")
    reviewed = meta["last_reviewed"]
    return Source(
        id=sid,
        title=str(meta["title"]),
        source_type=meta["source_type"],
        original_reference=str(meta["original_reference"]),
        language=str(meta["language"]),
        last_reviewed=reviewed.isoformat() if isinstance(reviewed, date) else str(reviewed),
        disclaimer=str(meta.get("disclaimer") or ""),
        body=body.strip("\n"),
        path=path,
    )


def read_source(path: Path, root: Path | None = None) -> Source:
    rel = str(path.relative_to(root)) if root else path.name
    return parse_source(path.read_text(encoding="utf-8"), rel)


@dataclass
class _Section:
    path: list[str]
    anchor: str = ""
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def _sections(src: Source) -> list[_Section]:
    out: list[_Section] = []
    stack: list[str] = []
    cur = _Section([src.title])
    for line in src.body.splitlines():
        m = HEADING.match(line)
        if not m:
            cur.lines.append(line)
            continue
        level, heading = len(m.group(1)), m.group(2).strip()
        anchor = ""
        am = ANCHOR.search(heading)
        if am:
            anchor, heading = am.group(1), heading[: am.start()].strip()
        if level == 1:
            continue  # the document title (same as front-matter title)
        if cur.text:
            out.append(cur)
        stack = [*stack[: level - 2], heading]
        cur = _Section([src.title, *stack], anchor)
    if cur.text:
        out.append(cur)
    return out


def _split(text: str, max_tokens: int, overlap: int) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    buf: list[str] = []
    for p in paras:
        if buf and tokens("\n\n".join([*buf, p])) > max_tokens:
            pieces.append("\n\n".join(buf))
            tail = " ".join(buf[-1].split()[-int(overlap / 1.3) :])
            buf = [tail] if tail else []
        buf.append(p)
    if buf:
        pieces.append("\n\n".join(buf))
    return pieces


def chunk_source(
    src: Source,
    max_tokens: int = MAX_TOKENS,
    min_tokens: int = MIN_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    merged: list[tuple[list[str], str, str]] = []
    for s in _sections(src):
        body = s.text
        heading = s.path[-1] if len(s.path) > 1 else ""
        text = f"{heading}\n{body}".strip() if heading else body
        prev_depth = len(merged[-1][0]) if merged else 0
        # fold a tiny section (or a tiny document intro) into the section that follows it
        if merged and tokens(merged[-1][1]) < min_tokens and prev_depth in (1, len(s.path)):
            _, prev, _ = merged.pop()
            merged.append((s.path, f"{prev}\n\n{text}", s.anchor))
        else:
            merged.append((s.path, text, s.anchor))
    chunks: list[Chunk] = []
    for path, text, anchor in merged:
        meta = {**src.meta(), "anchor": anchor} if anchor else src.meta()
        for piece in _split(text, max_tokens, overlap):
            chunks.append(
                Chunk(
                    source_id=src.id,
                    seq=len(chunks),
                    title=src.title,
                    heading_path=" > ".join(path),
                    content=piece,
                    language=src.language,
                    meta=meta,
                )
            )
    return chunks
