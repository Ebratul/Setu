---
paths:
  - "backend/**"
---

# Agent service rules (backend)

## Layout & layering
`app/api` (FastAPI routers, thin) → `app/services` (orchestration, DB) → `app/domain` (pure deterministic logic, no I/O, no LLM).
`app/tools` wrap services for the agent; `app/graph` composes tools into LangGraph; `app/llm/client.py` is the only model entry point.
`app/security` is imported by tools/services, never the other way round.

## Conventions
- Python 3.13, uv, Ruff (lint + format, line length 100). Full type hints; `from __future__ import annotations` not needed.
- Pydantic v2 models for every API request/response and every tool input/output (`model_config = ConfigDict(extra="forbid")`).
- Money fields are `Decimal` (serialised as strings) — see `money-logic.md`.
- Settings via `pydantic-settings` in `app/config.py`; never read `os.environ` elsewhere.
- DB: SQLAlchemy 2.0 typed ORM (`Mapped[...]`), sessions via FastAPI dependency; every schema change = Alembic migration
  (`uv run alembic revision --autogenerate -m "..."`), reviewed by hand.
- Async FastAPI endpoints; CPU-bound PDF work in `run_in_threadpool`.
- Errors: raise domain exceptions (`app/errors.py`: `DomainError`, `TierViolation`, `ApprovalRequired`, `NotFound`);
  one exception handler maps them to RFC 7807 problem JSON. Never leak stack traces or secrets in responses.
- Logging: `structlog` JSON; never log raw document text, PII or secrets — log ids and hashes.

## Tool signature pattern (LangChain)
```python
class LandedCostIn(BaseModel): order_id: str
class LandedCostOut(BaseModel): total_bdt: Decimal; breakdown: list[CostLine]; explanation_facts: list[str]

@setu_tool(name="compute_landed_cost", tier=Tier.T0, args_schema=LandedCostIn)
def compute_landed_cost(args: LandedCostIn, ctx: ToolContext) -> LandedCostOut:
    """One-line description the LLM sees. Say what it returns, not how to act."""
    return services.landed_cost.for_order(ctx.db, args.order_id)
```
- `@setu_tool` (in `app/tools/base.py`) does: tier check (refuses > T1 when caller is the LLM), audit-log append,
  LangSmith run metadata (`tier`, `tool`, `order_id`), pydantic validation of input and output.
- Tools return facts + numbers; the explainer node turns them into language. Tools never return instructions to the LLM.
- Tier 2/3 operations are *not* tools: they are service functions behind `/approvals/*` endpoints. The LLM may only call
  `request_approval(action, params)` which creates a `PendingApproval` (Tier 0 itself).

## LangGraph
- State is a pydantic model (`app/graph/state.py`); nodes are pure functions `(state) -> partial update`.
- Nodes: `router` (Haiku, intent + language) → `tool_executor` (allow-list per intent) → `explainer` (Haiku, cites tool
  facts + RAG chunk ids) → optional `forensics_reasoner` (Sonnet, document reasoning on masked data).
- Postgres checkpointer for conversation state. Max 6 tool steps per turn.
- Every LLM call: `llm.client.invoke(model=..., prompt_id=..., messages=..., schema=...)` → masks via Privacy Gateway,
  checks cache, traces to LangSmith (`LANGSMITH_TRACING=true`, project `setu`), unmasks output.
- Prompts live in `app/llm/prompts/*.md` with a version header; bump the version when editing (cache key includes it).

## RAG
- KB sources: `kb/*.md` (short, cited). Chunk ~500 tokens with heading path; embed with `fastembed` (bge-small-en-v1.5, 384-d) into `kb_chunk` (pgvector).
- Retrieval tool returns `[{chunk_id, title, text, score}]`; the explainer must cite `chunk_id`s it used.

## Commands
`uv run --directory backend fastapi dev app/main.py` · `uv run --directory backend pytest -q` ·
`uv run --directory backend ruff check . && uv run --directory backend ruff format --check .`
