"""User-guide KB: MDX conversion, chunk anchors, guide_url citations, how-to ranking."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.registry import ToolContext, default_registry
from app.auth.deps import to_current
from app.config import RAG_AGENT_DIR, get_settings
from app.db.models import User
from app.db.session import get_engine
from app.rag import ingest, userguide
from app.rag.chunker import SOURCE_TYPES, chunk_source, parse_source
from app.rag.embed import HashEmbedder
from app.rag.retrieve import search
from tests.api.conftest import seeded_db  # noqa: F401  (module-scoped fixture)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "userguide"
SOURCES = RAG_AGENT_DIR / "kb" / "sources"


def _rendered(lang: str = "en") -> str:
    pages = [p for p in userguide.discover(FIXTURES) if p.lang == lang]
    return userguide.render_page(pages[0])


def test_converter_output_is_clean_prose() -> None:
    md = _rendered()
    assert "## Step by step {#how-to}" in md
    assert "1. Open Deals\n   Choose **Deals**" in md
    assert "2. Fund the escrow\n   Press Fund to create a Tier 2 approval." in md
    assert "Screen: The deals list" in md
    assert "Security (Simulated): No real money moves." in md
    assert "Q: Can I undo a deposit?\nA: Ask for a refund" in md
    assert "Buyer only." in md
    for junk in ("<", "REVIEW", "{/*", "\\{", "Steps", "RoleBadge"):
        assert junk not in md


def test_converter_front_matter_is_accepted_by_chunker() -> None:
    src = parse_source(_rendered("bn"), "x.md")
    assert src.source_type == "user_guide" and "user_guide" in SOURCE_TYPES
    assert src.id == "user-guide-bn-buyer-fund-escrow"
    assert src.original_reference == "/docs/bn/buyer/fund-escrow"
    assert (src.language, src.last_reviewed) == ("bn", "2026-10-20")


def test_converter_is_deterministic_and_generate_cleans_stale(tmp_path: Path) -> None:
    out = tmp_path / "gen"
    assert userguide.generate(FIXTURES, out) == (2, 0)
    stale = out / "user-guide" / "zh-old-page.md"
    stale.write_text("x", encoding="utf-8")
    assert userguide.generate(FIXTURES, out) == (0, 1)
    assert sorted(f.name for f in (out / "user-guide").glob("*.md")) == [
        "bn-buyer-fund-escrow.md",
        "en-buyer-fund-escrow.md",
    ]


def test_chunks_carry_anchor_and_headings_are_clean() -> None:
    chunks = chunk_source(parse_source(_rendered(), "x.md"), min_tokens=1)
    how = next(c for c in chunks if c.heading_path.endswith("Step by step"))
    assert how.meta["anchor"] == "how-to" and "{#" not in how.content
    assert all("{#" not in c.heading_path for c in chunks)


def test_guide_url_only_for_user_guide() -> None:
    ref = "/docs/en/buyer/fund-escrow"
    assert userguide.guide_url("user_guide", ref, "how-to") == f"{ref}#how-to"
    assert userguide.guide_url("user_guide", ref) == ref
    assert userguide.guide_url("glossary", ref, "how-to") is None


@pytest.fixture
def db_with_guide(seeded_db: str, tmp_path: Path) -> Iterator[Session]:  # noqa: F811
    kb = tmp_path / "kb"
    shutil.copytree(SOURCES, kb, ignore=shutil.ignore_patterns("user-guide"))
    userguide.generate(FIXTURES, kb / "generated")
    with Session(get_engine()) as s:
        ingest.index(s, HashEmbedder(), kb)
        yield s
        ingest.index(s, HashEmbedder(), SOURCES)


@pytest.mark.db
def test_how_to_query_ranks_guide_and_citation_has_guide_url(
    db_with_guide: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KB_EMBEDDER", "hash")
    get_settings.cache_clear()
    res = search(db_with_guide, HashEmbedder(), "how do I fund the escrow", language="en")
    guide_hit = next(x for x in res.snippets if x.source_id == "user-guide-en-buyer-fund-escrow")
    assert guide_hit.meta["source_type"] == "user_guide" and guide_hit.meta["anchor"]
    undo = search(db_with_guide, HashEmbedder(), "can I undo a deposit refund", language="en")
    assert undo.snippets[0].source_id == "user-guide-en-buyer-fund-escrow"
    rahima = to_current(
        db_with_guide.scalars(select(User).where(User.email == "rahima@demo.setu")).one()
    )
    ctx = ToolContext(caller="llm", user=rahima, db=db_with_guide, thread_id="t")
    out = default_registry().guard(
        "search_knowledge", {"query": "how do I fund the escrow", "language": "en"}, ctx
    )
    assert out.ok
    snippets = out.data["data"]["snippets"]
    guide = [s for s in snippets if s["source_type"] == "user_guide"]
    assert guide and guide[0]["guide_url"].startswith("/docs/en/buyer/fund-escrow")
    assert all(s["guide_url"] is None for s in snippets if s["source_type"] != "user_guide")
    get_settings.cache_clear()
