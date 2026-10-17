"""Embedding backends (384-d, matching kb_chunks.embedding).

- FastEmbedder: local `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` via fastembed
  (Apache-2.0, 50+ languages incl. Bengali). Downloaded once into KB_MODEL_CACHE_DIR; no paid API.
- HashEmbedder: deterministic hashed bag-of-words, for tests and offline runs without the model.
Embeddings are L2-normalised, so cosine distance works with the HNSW index.
"""

import hashlib
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import structlog

from app.config import get_settings
from app.db.models.app_state import EMBEDDING_DIM

log = structlog.get_logger("setu.rag")

TOKEN = re.compile(r"[^\s.,;:!?()\[\]{}\"'“”‘’।/\\|&<>*+=~`^%$#@\-—–]+")


class Embedder(Protocol):
    model_id: str

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class HashEmbedder:
    model_id = "hash-bow-384"

    def _one(self, text: str) -> list[float]:
        v = [0.0] * EMBEDDING_DIM
        for tok in TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.sha1(tok.encode("utf-8")).digest()[:4], "big")
            v[h % EMBEDDING_DIM] += 1.0
        return _normalise(v)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._one(text)


class FastEmbedder:
    def __init__(self, model_id: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        self.model_id = model_id
        self._model = TextEmbedding(model_id, cache_dir=cache_dir)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [_normalise([float(x) for x in v]) for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_passages([text])[0]


def model_cached(model_id: str, cache_dir: Path) -> bool:
    """True when fastembed already has the model files locally (no download needed)."""
    short = model_id.split("/")[-1]
    return cache_dir.is_dir() and any(
        short in d.name and (d / "files_metadata.json").exists() for d in cache_dir.iterdir()
    )


@lru_cache
def _cached(kind: str, model_id: str, cache_dir: str, allow_download: bool) -> Embedder | None:
    if kind == "hash":
        return HashEmbedder()
    if not allow_download and not model_cached(model_id, Path(cache_dir)):
        log.warning("kb_model_not_cached", model=model_id)  # full-text search only
        return None
    try:
        return FastEmbedder(model_id, cache_dir)
    except Exception as exc:  # cached as None: no retry storm on every request
        log.warning("kb_model_load_failed", error=type(exc).__name__)
        return None


def get_embedder(*, allow_download: bool = False) -> Embedder | None:
    """Request path: never downloads (None → full-text search). `kb:index` passes
    allow_download=True to fetch the model once."""
    s = get_settings()
    return _cached(s.kb_embedder, s.kb_embedding_model, str(s.kb_model_cache_dir), allow_download)
