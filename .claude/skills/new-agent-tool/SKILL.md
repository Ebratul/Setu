---
name: new-agent-tool
description: Step-by-step procedure to add a LangChain tool to Setu's agent with tier enforcement, pydantic schemas, audit logging, LangSmith tracing and tests. Use whenever a new capability must be callable by the LangGraph agent.
---

# Add a new agent tool

1. **Decide the tier** using `.claude/rules/security.md`. If the action is Tier 2/3 it is NOT a tool: implement it as a
   service function + `/approvals` action type, and let the LLM call only `request_approval`. Stop here for that part.
2. **Domain logic first** (if it computes anything): pure function in `app/domain/<area>.py` returning a pydantic result
   with `explanation_facts: list[str]`. Decimal money. Unit-test it (golden example + boundary).
3. **Schemas** in `app/tools/<area>.py`: `<Name>In` / `<Name>Out` pydantic models with `extra="forbid"`; ids are strings,
   amounts are Decimal; no free-text fields that could carry instructions back to the model unless wrapped as untrusted.
4. **Tool** with the decorator:
   ```python
   @setu_tool(name="snake_case_name", tier=Tier.T0, args_schema=NameIn)
   def snake_case_name(args: NameIn, ctx: ToolContext) -> NameOut:
       """What it returns (≤2 lines). No imperative instructions."""
   ```
   The decorator handles tier refusal for `ctx.caller=="llm"`, audit append, LangSmith metadata, validation.
5. **Register** it in `app/tools/registry.py` and add it to the allow-list of the graph node(s) that need it
   (`app/graph/allowlists.py`). Do not add it to the forensics node unless it is read-only.
6. **Explainer support**: if output has new fact types, add a template line in `app/llm/prompts/explainer.md` and bump the prompt version.
7. **Tests** (`tests/tools/test_<name>.py`): valid call returns schema; invalid args rejected; LLM caller blocked if tier ≥ 2;
   audit entry written; graph test with `FakeChatModel` choosing the tool end-to-end.
8. Run `uv run --directory backend pytest -q -m "not llm"` and `ruff check`. If the tool touches security paths,
   delegate a review to the `security-reviewer` subagent and fix findings.
