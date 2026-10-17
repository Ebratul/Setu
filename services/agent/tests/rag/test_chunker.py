"""KB parsing and chunking (pure, no DB)."""

import pytest

from app.config import AGENT_DIR
from app.rag.chunker import SourceError, chunk_source, parse_source, tokens
from app.rag.ingest import load_chunks
from app.security.injection import detect_instructions

SOURCES = AGENT_DIR / "kb" / "sources"
DOC = """---
id: demo-doc
title: Demo doc
source_type: glossary
original_reference: "Our own summary"
language: en
last_reviewed: 2026-10-17
disclaimer: "Demo."
---
# Demo doc

Intro paragraph about the doc.

## First
Alpha section text that is long enough to stand on its own as a chunk of the document, \
with several more words so that it passes the minimum size for a chunk in this test.

### Detail
Detail text under first, also long enough to be a chunk of its own in the document for this \
test, with more words added so the section is above the minimum token threshold.

## Second
Beta section text.
"""


def test_parse_front_matter() -> None:
    src = parse_source(DOC, "demo.md")
    assert (src.id, src.source_type, src.language, src.last_reviewed) == (
        "demo-doc",
        "glossary",
        "en",
        "2026-10-17",
    )
    assert src.meta()["original_reference"] == "Our own summary"


@pytest.mark.parametrize(
    "bad",
    [
        "# no front matter",
        DOC.replace("source_type: glossary", "source_type: blog"),
        DOC.replace("id: demo-doc", "id: Bad ID!"),
        DOC.replace('original_reference: "Our own summary"\n', ""),
        DOC.replace("language: en", "language: fr"),
        "---\n- just\n- a list\n---\n# x\n",
    ],
)
def test_parse_rejects_bad_sources(bad: str) -> None:
    with pytest.raises(SourceError):
        parse_source(bad, "bad.md")


def test_chunks_keep_heading_paths() -> None:
    chunks = chunk_source(parse_source(DOC))
    paths = [c.heading_path for c in chunks]
    assert "Demo doc > First" in paths
    assert "Demo doc > First > Detail" in paths
    assert [c.seq for c in chunks] == list(range(len(chunks)))
    assert all(c.title == "Demo doc" and c.language == "en" for c in chunks)
    detail = next(c for c in chunks if c.heading_path.endswith("Detail"))
    assert detail.content.startswith("Detail\n")


def test_long_sections_split_with_overlap() -> None:
    para = " ".join(f"word{i}" for i in range(120))
    long_doc = DOC.replace("Beta section text.", "\n\n".join([para] * 6))
    chunks = [c for c in chunk_source(parse_source(long_doc)) if c.heading_path.endswith("Second")]
    assert len(chunks) >= 2
    assert all(tokens(c.content) <= 450 + 60 for c in chunks)
    tail = chunks[0].content.split()[-5:]
    assert " ".join(tail) in chunks[1].content  # overlap carries the previous tail


def test_hash_changes_with_model_or_text() -> None:
    [a, *_] = chunk_source(parse_source(DOC))
    assert a.content_hash("m1") != a.content_hash("m2")
    b = chunk_source(parse_source(DOC.replace("Intro paragraph", "Changed intro")))[0]
    assert a.content_hash("m1") != b.content_hash("m1")


def test_real_kb_loads_with_expected_sources() -> None:
    chunks = load_chunks(SOURCES)
    ids = {c.source_id for c in chunks}
    assert {
        "bb-advance-payment",
        "incoterms-basics",
        "trade-document-fields",
        "setu-how-it-works",
        "financing-glossary",
        "faq-bn",
    } <= ids
    assert all(
        40 <= tokens(c.content) <= 520 or c.source_id == "financing-catalogue" for c in chunks
    )
    assert {c.language for c in chunks if c.source_id == "faq-bn"} == {"bn"}


def test_kb_content_never_looks_like_an_instruction() -> None:
    """Our own sources must pass the injection detector, so a bad edit is caught in CI."""
    flagged = [
        (
            c.source_id,
            c.heading_path,
            [f.code for f in detect_instructions(c.heading_path + "\n" + c.content)],
        )
        for c in load_chunks(SOURCES)
        if detect_instructions(c.heading_path + "\n" + c.content)
    ]
    assert flagged == []


def test_symlinks_and_duplicate_ids_are_refused(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "a.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "b.md").write_text(DOC, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_chunks(tmp_path)
    (tmp_path / "b.md").unlink()
    outside = tmp_path.parent / "outside.md"
    outside.write_text(DOC.replace("demo-doc", "other-doc"), encoding="utf-8")
    (tmp_path / "link.md").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        load_chunks(tmp_path)
