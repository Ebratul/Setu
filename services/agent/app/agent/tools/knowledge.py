"""Tier 0 knowledge-base search (P10). Returns cited passages from Setu's own short summaries
(kb/sources). Passages are untrusted data; ones with instruction-like text are withheld and their
codes flag the turn (security_flags)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.registry import ToolContext, ToolError
from app.agent.tools.readonly import REGISTRY
from app.rag.embed import get_embedder
from app.rag.retrieve import search
from app.schemas.cards import CitationsCard, CitationsData, CitationSnippet, Withheld
from app.security.tiers import Tier


class SearchKnowledgeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Annotated[str, Field(min_length=2, max_length=300)]
    language: Literal["en", "bn"] | None = Field(
        None, description="Preferred passage language (the user's language)."
    )


@REGISTRY.tool(
    name="search_knowledge",
    tier=Tier.T0,
    args_schema=SearchKnowledgeIn,
    output_schema=CitationsCard,
    tags=("rag",),
)
def search_knowledge(args: SearchKnowledgeIn, ctx: ToolContext) -> CitationsCard:
    """Search Setu's knowledge base (Bangladesh Bank import rules summary, Incoterms basics, trade
    document fields, how Setu works, financing glossary and catalogue, Bangla FAQ). Returns up to 4
    passages with cite ids S1..S4 for rule, definition and process questions."""
    if ctx.db is None:
        raise ToolError("unavailable", "database is not available")
    res = search(ctx.db, get_embedder(), args.query, language=args.language)
    snippets = [
        CitationSnippet(
            cite_id=f"S{i}",
            source_id=s.source_id,
            title=s.title,
            heading_path=s.heading_path,
            content=s.content,
            language=s.language,
            source_type=str(s.meta.get("source_type", "")),
            original_reference=str(s.meta.get("original_reference", "")),
            last_reviewed=str(s.meta.get("last_reviewed", "")),
            disclaimer=str(s.meta.get("disclaimer", "")),
            score=s.score,
        )
        for i, s in enumerate(res.snippets, start=1)
    ]
    flags = sorted({c for w in res.withheld for c in w["codes"]})
    n = len(snippets)
    return CitationsCard(
        data=CitationsData(
            snippets=snippets,
            withheld=[Withheld(**w) for w in res.withheld],
            security_flags=flags,
        ),
        explanation_codes=["KB_PASSAGES" if n else "KB_NO_MATCH"],
        explanation_en=(
            f"Based on {n} passages from Setu's knowledge base (simplified summaries; verify with "
            "the official sources listed)."
            if n
            else "Setu's knowledge base has nothing on this."
        ),
        explanation_bn=(
            f"Setu-র knowledge base-এর {n}টি অংশ থেকে (সহজ করা সারসংক্ষেপ; তালিকার সরকারি উৎসে যাচাই করুন)।"
            if n
            else "Setu-র knowledge base-এ এ বিষয়ে কিছু নেই।"
        ),
    )
