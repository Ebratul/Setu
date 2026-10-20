"""KB commands: `python -m app.rag.cli sync` (export the financing catalogue) and
`python -m app.rag.cli userguide` (docs MDX -> KB sources, EN+BN) and
`python -m app.rag.cli index` (chunk + embed; idempotent).
Root scripts: npm run kb:sync / npm run kb:index."""

import argparse
import sys

from app.config import RAG_AGENT_DIR, REPO_ROOT
from app.db.session import batch_session
from app.rag import catalogue, ingest, userguide
from app.rag.embed import get_embedder
from app.services.scope import demo_today

SOURCES = RAG_AGENT_DIR / "kb" / "sources"
GENERATED = SOURCES / "generated"
DOCS = REPO_ROOT / "frontend" / "content" / "docs"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kb")
    p.add_argument("command", choices=["sync", "index", "userguide"])
    args = p.parse_args(argv)
    if args.command == "userguide":  # no DB: MDX -> kb/sources/generated/user-guide/*.md
        written, removed = userguide.generate(DOCS, GENERATED)
        print(f"user guide: {written} written, {removed} removed")
        return 0
    with batch_session() as db:
        if args.command == "sync":
            path, changed = catalogue.sync(db, GENERATED, demo_today(db).isoformat())
            print(f"{'wrote' if changed else 'unchanged'} {path.relative_to(RAG_AGENT_DIR)}")
        else:
            embedder = get_embedder(allow_download=True)
            if embedder is None:
                print("embedding model unavailable; cannot index", file=sys.stderr)
                return 1
            s = ingest.index(db, embedder, SOURCES)
            print(
                f"model {embedder.model_id}: {s.sources} sources, {s.chunks} chunks "
                f"(+{s.added} embedded, {s.unchanged} unchanged, -{s.removed} removed)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
