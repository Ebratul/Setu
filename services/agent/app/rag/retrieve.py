"""Hybrid retrieval over kb_chunks: pgvector cosine similarity + Postgres full-text ('simple'
config, prefix terms), merged with reciprocal rank fusion (RRF), with an optional language boost.

Retrieved text is untrusted data: every candidate is run through the instruction detector and a
flagged chunk is withheld (its codes are reported so the turn can be flagged).
"""

import re
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import KbChunk
from app.rag.embed import TOKEN, Embedder
from app.security.injection import detect_instructions

log = structlog.get_logger("setu.rag")

TOP_K = 4
CANDIDATES = 20
RRF_K = 60
LANGUAGE_BOOST = 1.25
MIN_VECTOR_SIM = 0.30  # vector-only hits below this are dropped (full-text hits always count)
MIN_PREFIX_LEN = 3
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        "setu",
        "কি",
        "কী",
        "কত",
        "কোন",
        "কেন",
        "আমি",
        "আমার",
        "এর",
        "এই",
        "ও",
        "আর",
        "না",
        "হয়",
        "হবে",
        "করে",
        "করলে",
    ]
)


@dataclass(frozen=True, slots=True)
class Snippet:
    chunk_id: str
    source_id: str
    title: str
    heading_path: str
    content: str
    language: str
    meta: dict[str, Any]
    score: float
    vector_sim: float | None
    text_rank: int | None


@dataclass(slots=True)
class SearchResult:
    snippets: list[Snippet]
    withheld: list[dict[str, Any]] = field(default_factory=list)  # {source_id, heading_path, codes}
    used_vector: bool = True


def passage_text(title: str, heading_path: str, content: str, meta: dict[str, Any] | None) -> str:
    """Everything about a passage that can reach the model, the UI or a citation."""
    m = meta or {}
    extra = " ".join(str(m.get(k, "")) for k in ("original_reference", "disclaimer"))
    return f"{title}\n{heading_path}\n{content}\n{extra}"


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for tok in TOKEN.findall(query.lower()):
        tok = re.sub(r"[^\wঀ-৿一-鿿]", "", tok)  # tsquery-safe
        if len(tok) >= 2 and tok not in STOP and tok not in terms:
            terms.append(tok)
    return terms[:12]


def _tsquery(terms: list[str]) -> str:
    return " | ".join(f"{t}:*" if len(t) >= MIN_PREFIX_LEN else t for t in terms)


def search(
    db: Session,
    embedder: Embedder | None,
    query: str,
    *,
    language: str | None = None,
    k: int = TOP_K,
) -> SearchResult:
    ranks: dict[Any, dict[str, Any]] = {}
    used_vector = True
    try:
        if embedder is None:
            raise LookupError("no embedding model")
        qvec = embedder.embed_query(query)
        dist = KbChunk.embedding.cosine_distance(qvec)
        with db.begin_nested():  # a vector SQL error must not abort the full-text query
            rows = db.execute(
                select(KbChunk.id, dist.label("d")).order_by(dist).limit(CANDIDATES)
            ).all()
        for i, (cid, d) in enumerate(rows, start=1):
            sim = 1.0 - float(d)
            if sim >= MIN_VECTOR_SIM:
                ranks.setdefault(cid, {})["v"] = (i, sim)
    except Exception as exc:  # model missing / offline: full-text still works
        log.warning("kb_vector_search_failed", error=type(exc).__name__)
        used_vector = False
    terms = query_terms(query)
    if terms:
        rows = db.execute(
            text(
                "SELECT id, ts_rank_cd(tsv, q) AS r FROM kb_chunks, "
                "to_tsquery('simple', :q) AS q WHERE tsv @@ q ORDER BY r DESC LIMIT :n"
            ),
            {"q": _tsquery(terms), "n": CANDIDATES},
        ).all()
        for i, (cid, _r) in enumerate(rows, start=1):
            ranks.setdefault(cid, {})["t"] = i
    if not ranks:
        return SearchResult([], [], used_vector)

    chunks = {c.id: c for c in db.scalars(select(KbChunk).where(KbChunk.id.in_(list(ranks))))}
    scored: list[tuple[float, KbChunk, dict[str, Any]]] = []
    for cid, r in ranks.items():
        c = chunks.get(cid)
        if c is None:
            continue
        score = sum(1.0 / (RRF_K + rank) for rank in (r.get("v", (None,))[0], r.get("t")) if rank)
        if language and c.language == language:
            score *= LANGUAGE_BOOST
        scored.append((score, c, r))
    scored.sort(key=lambda x: (-x[0], x[1].source_id, x[1].seq))

    out: list[Snippet] = []
    withheld: list[dict[str, Any]] = []
    for score, c, r in scored:
        findings = detect_instructions(passage_text(c.title, c.heading_path, c.content, c.meta))
        if findings:
            # id and codes only: the withheld text is never shown, stored or sent anywhere
            withheld.append({"source_id": c.source_id, "codes": sorted({f.code for f in findings})})
            continue
        out.append(
            Snippet(
                chunk_id=str(c.id),
                source_id=c.source_id,
                title=c.title,
                heading_path=c.heading_path,
                content=c.content,
                language=c.language,
                meta=dict(c.meta or {}),
                score=round(score, 6),
                vector_sim=round(r["v"][1], 4) if "v" in r else None,
                text_rank=r.get("t"),
            )
        )
        if len(out) >= k:
            break
    return SearchResult(out, withheld, used_vector)
