"""Index KB sources into kb_chunks. Idempotent: a chunk is (re-)embedded only when its content hash
(text + heading path + embedding model) changes; chunks of deleted sources are removed."""

import unicodedata
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import KbChunk
from app.rag.chunker import Chunk, Source, chunk_source, read_source
from app.rag.embed import Embedder
from app.rag.retrieve import passage_text
from app.security.injection import detect_instructions
from app.security.injection.detector import scan


@dataclass(frozen=True, slots=True)
class IndexStats:
    sources: int
    chunks: int
    added: int
    unchanged: int
    removed: int


GUIDE_PARTS = ("generated", "user-guide")


def is_first_party_guide(src: Source, path: Path, root: Path) -> bool:
    """Decided from where the indexer found the file, not from what a document says of itself."""
    return (
        src.source_type == "user_guide"
        and src.id.startswith("user-guide-")
        and path.resolve().parent.relative_to(root).parts == GUIDE_PARTS
    )


def _invisible(text: str) -> bool:
    """Control, format (zero-width space, bidi, tag) and private-use characters.

    Newline, tab and ZWNJ/ZWJ are allowed: Bangla conjuncts need the joiners."""
    return any(
        unicodedata.category(ch) in {"Cc", "Cf", "Co"} and ch not in "\n\t\u200c\u200d"
        for ch in text
    )


def load_chunks(sources_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    seen: set[str] = set()
    root = sources_dir.resolve()
    for path in sorted(sources_dir.rglob("*.md")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"{path.name}: symlinks and files outside kb/sources are not indexed")
        src = read_source(path, sources_dir)
        if src.id in seen:
            raise ValueError(f"duplicate source id {src.id}")
        seen.add(src.id)
        guide = is_first_party_guide(src, path, root)
        for c in chunk_source(src):
            if guide:
                if _invisible(c.content) or _invisible(c.heading_path):
                    raise ValueError(f"{src.id}: chunk {c.seq} has invisible characters")
                # Our generated user guide (from reviewed repo files) legitimately describes actions
                # such as "release the payment"; the prompt still wraps it as untrusted data.
                chunks.append(replace(c, trusted=True))
                continue
            # Refuse to index our own sources if they look like instructions (fix the text instead).
            text = passage_text(c.title, c.heading_path, c.content, c.meta)
            if detect_instructions(text) or scan(text, "kb", use_llm=False).is_injection:
                raise ValueError(f"{src.id}: chunk {c.seq} contains instruction-like text")
            chunks.append(c)
    return chunks


def index(db: Session, embedder: Embedder, sources_dir: Path) -> IndexStats:
    chunks = load_chunks(sources_dir)
    wanted = {(c.source_id, c.seq): (c, c.content_hash(embedder.model_id)) for c in chunks}
    existing = {
        (r.source_id, r.seq): (r.id, r.content_hash)
        for r in db.execute(
            select(KbChunk.source_id, KbChunk.seq, KbChunk.id, KbChunk.content_hash)
        )
    }
    stale = [rid for key, (rid, h) in existing.items() if key not in wanted or wanted[key][1] != h]
    fresh = [(c, h) for key, (c, h) in wanted.items() if existing.get(key, (None, None))[1] != h]
    if stale:
        db.execute(delete(KbChunk).where(KbChunk.id.in_(stale)))
    if fresh:
        vectors = embedder.embed_passages([f"{c.heading_path}\n{c.content}" for c, _ in fresh])
        for (c, h), vec in zip(fresh, vectors, strict=True):
            db.add(
                KbChunk(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu-kb:{c.source_id}:{c.seq}:{h}"),
                    source_id=c.source_id,
                    seq=c.seq,
                    title=c.title,
                    heading_path=c.heading_path,
                    content=c.content,
                    language=c.language,
                    content_hash=h,
                    trusted=c.trusted,
                    embedding=vec,
                    meta=c.meta,
                )
            )
    db.commit()
    return IndexStats(
        sources=len({c.source_id for c in chunks}),
        chunks=len(chunks),
        added=len(fresh),
        unchanged=len(wanted) - len(fresh),
        removed=len([k for k in existing if k not in wanted]),
    )
