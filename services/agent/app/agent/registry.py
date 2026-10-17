"""Tool registry with tier metadata and the guard every agent tool call goes through.

`guard()` refuses any tool above `MAX_LLM_TOOL_TIER` with a structured `requires_approval_flow`
error before anything runs (SR-1/SR-2), validates input and output with pydantic, traces the call
as a LangSmith tool run, scans string results for instruction-like text (SR-3) and records an
audit event.
"""

import json
import re
from collections.abc import Callable, Iterable
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.agent.state import Intent
from app.auth.deps import CurrentUser
from app.errors import DomainError, Forbidden, NotFound
from app.security.audit import record_event
from app.security.injection import Finding, detect_instructions
from app.security.tiers import MAX_LLM_TOOL_TIER, Tier

log = structlog.get_logger("setu.agent.tools")

ARG_VALUE_CHARS = 40
TOOL_NAME = re.compile(r"[A-Za-z0-9_]{1,64}")
INVALID_TOOL_NAME = "invalid_tool_name"


@dataclass(frozen=True, slots=True)
class ToolContext:
    caller: Literal["llm", "user", "system"]
    user: CurrentUser
    db: Session | None
    thread_id: str | None = None
    deal_ref: str | None = None  # deal the chat is scoped to ("About deal"), if any


class ToolError(Exception):
    """A structured, user-safe tool failure (returned to the model as data)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


ToolFn = Callable[[Any, ToolContext], BaseModel]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    args_schema: type[BaseModel]
    output_schema: type[BaseModel]
    max_tier: Tier
    fn: ToolFn
    tags: tuple[str, ...] = ()

    def definition(self) -> dict[str, Any]:
        """Anthropic tool format; also accepted by `bind_tools` on the mock model."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_schema.model_json_schema(),
        }


class ToolOutcome(BaseModel):
    name: str
    ok: bool
    args_summary: str
    data: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    injection: list[str] = []

    def payload(self) -> str:
        body = self.data if self.ok else {"error": self.error}
        return json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)

    def model_payload(self) -> str:
        """What the model sees: chart series are left out (the UI card still gets them)."""
        body = _strip(self.data) if self.ok else {"error": self.error}
        return json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)


MODEL_HIDDEN_KEYS = frozenset({"series", "history"})


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in MODEL_HIDDEN_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def args_summary(args: dict[str, Any]) -> str:
    parts = []
    for key in sorted(args):
        value = str(args[key])
        if len(value) > ARG_VALUE_CHARS:
            value = value[: ARG_VALUE_CHARS - 1] + "…"
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


FLAG_CODE = re.compile(r"[A-Z_]{2,40}")


def declared_flags(data: dict[str, Any]) -> set[str]:
    """Injection codes a tool reports for content it withheld (e.g. flagged KB passages)."""
    inner = data.get("data")
    flags = inner.get("security_flags") if isinstance(inner, dict) else None
    if not isinstance(flags, list):
        return set()
    return {f for f in flags if isinstance(f, str) and FLAG_CODE.fullmatch(f)}


def scan_result(data: dict[str, Any]) -> list[Finding]:
    """Instruction-like text in any string value of a tool result (keys are ours, not scanned)."""
    findings: list[Finding] = []
    for text in _strings(data):
        findings.extend(detect_instructions(text))
    return findings


@dataclass
class ToolRegistry:
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._specs:
            raise ValueError(f"tool {spec.name} already registered")
        self._specs[spec.name] = spec
        return spec

    def tool(
        self,
        *,
        name: str,
        tier: Tier,
        args_schema: type[BaseModel],
        output_schema: type[BaseModel],
        tags: tuple[str, ...] = (),
    ) -> Callable[[ToolFn], ToolFn]:
        def decorator(fn: ToolFn) -> ToolFn:
            doc = " ".join((fn.__doc__ or name).split())
            self.register(ToolSpec(name, doc, args_schema, output_schema, tier, fn, tags))
            return fn

        return decorator

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._specs)

    def llm_tools(self, allowed: frozenset[str]) -> list[str]:
        """Tools the model may be offered: allow-listed and within the LLM tier ceiling."""
        ceiling = MAX_LLM_TOOL_TIER
        return [n for n, spec in self._specs.items() if n in allowed and spec.max_tier <= ceiling]

    def definitions(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        wanted = (
            self._specs if names is None else {n: self._specs[n] for n in names if n in self._specs}
        )
        return [spec.definition() for spec in wanted.values()]

    def guard(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
        config: RunnableConfig | None = None,
        allowed: frozenset[str] | None = None,
    ) -> ToolOutcome:
        summary = args_summary(args)
        # Model-chosen names are untrusted: they end up in prompts, logs and the result wrapper.
        name = name if TOOL_NAME.fullmatch(name or "") else INVALID_TOOL_NAME
        spec = self.get(name)
        refs = {"tool": name, "user_id": str(ctx.user.id), "thread_id": ctx.thread_id or ""}
        if spec is None:
            return self._refuse(
                name, summary, "unknown_tool", "this tool is not available here", Tier.T0, refs
            )
        if spec.max_tier > MAX_LLM_TOOL_TIER:
            return self._refuse(
                name,
                summary,
                "requires_approval_flow",
                f"'{name}' is a Tier {int(spec.max_tier)} action. The assistant cannot run it; "
                "it must go through Setu's human approval flow.",
                spec.max_tier,
                refs,
                extra={"tier": int(spec.max_tier)},
            )
        if allowed is not None and name not in allowed:
            return self._refuse(
                name, summary, "unknown_tool", "this tool is not available here", Tier.T0, refs
            )
        try:
            parsed = spec.args_schema.model_validate(args)
        except ValidationError as exc:
            fields = sorted({".".join(str(p) for p in e["loc"]) or "args" for e in exc.errors()})
            return self._refuse(
                name,
                summary,
                "invalid_args",
                f"invalid arguments: {', '.join(fields)}",
                spec.max_tier,
                refs,
            )

        try:
            # Savepoint: a DB error inside a tool must not poison the turn's session.
            with ctx.db.begin_nested() if ctx.db is not None else nullcontext():
                result = self._run(spec, parsed, ctx, config)
            data = spec.output_schema.model_validate(result).model_dump(mode="json")
        except ToolError as exc:
            return self._refuse(name, summary, exc.code, exc.message, spec.max_tier, refs)
        except (Forbidden, NotFound) as exc:
            code = "forbidden" if isinstance(exc, Forbidden) else "not_found"
            return self._refuse(name, summary, code, exc.detail, spec.max_tier, refs)
        except DomainError as exc:
            return self._refuse(name, summary, "bad_request", exc.detail, spec.max_tier, refs)
        except Exception as exc:
            log.warning("tool_failed", tool=name, error=type(exc).__name__)
            return self._refuse(
                name,
                summary,
                "tool_failed",
                "the tool failed; try again later",
                spec.max_tier,
                refs,
            )

        findings = scan_result(data)
        codes = sorted({f.code for f in findings} | declared_flags(data))
        record_event(
            actor="llm",
            action=f"TOOL:{name}",
            tier=int(spec.max_tier),
            params=args,
            result="OK_FLAGGED" if codes else "OK",
            refs=refs,
        )
        if codes:
            # Instruction text in data is a Tier 3 trigger (DOC_INSTRUCTION). Phase 5 escalates it
            # to an approval; here the turn stops calling tools and the answer flags it.
            record_event(
                actor="system",
                action="INJECTION_DETECTED",
                tier=int(Tier.T3),
                params={"tool": name, "codes": codes},
                result="FLAGGED",
                refs=refs,
            )
        return ToolOutcome(name=name, ok=True, args_summary=summary, data=data, injection=codes)

    @staticmethod
    def _run(
        spec: ToolSpec, parsed: BaseModel, ctx: ToolContext, config: RunnableConfig | None
    ) -> Any:
        def call(**_: Any) -> Any:
            return spec.fn(parsed, ctx)

        runnable = StructuredTool.from_function(
            func=call,
            name=spec.name,
            description=spec.description,
            args_schema=spec.args_schema,
            tags=["setu", "tool", *spec.tags],
            metadata={"tool": spec.name, "tier": int(spec.max_tier)},
        )
        return runnable.invoke(parsed.model_dump(mode="json"), config=config)

    @staticmethod
    def _refuse(
        name: str,
        summary: str,
        code: str,
        message: str,
        tier: Tier,
        refs: dict[str, str],
        extra: dict[str, Any] | None = None,
    ) -> ToolOutcome:
        record_event(
            actor="llm",
            action=f"TOOL:{name}",
            tier=int(tier),
            params={"args": summary},
            result=f"REFUSED:{code}",
            refs=refs,
        )
        return ToolOutcome(
            name=name,
            ok=False,
            args_summary=summary,
            error={"code": code, "message": message, **(extra or {})},
        )


READONLY: frozenset[str] = frozenset(
    {"get_dashboard_snapshot", "get_deal_summary", "explain_how_setu_works"}
)
ANALYSIS = frozenset(
    {
        "analyze_order",
        "landed_cost_what_if",
        "compare_fx_route",
        "get_monthly_summary",
        "get_supplier_scorecard",
    }
)
CASHFLOW = frozenset({"forecast_cashflow", "simulate_cashflow_scenario", "get_alerts"})
FINANCING = frozenset({"match_financing", "financing_impact"})
KYB = frozenset({"verify_party"})
DOCS = frozenset({"check_documents", "registry_status"})
# Per-intent allow-lists (SR-3): the tools each intent is likely to need, all Tier 0.
# greeting and out_of_scope never reach the agent node.
INTENT_TOOLS: dict[Intent, frozenset[str]] = {
    "greeting": frozenset(),
    "out_of_scope": frozenset(),
    "analysis": READONLY | ANALYSIS | KYB | {"forecast_cashflow"},
    "cashflow": READONLY | CASHFLOW | FINANCING,
    "financing": READONLY | FINANCING | {"forecast_cashflow", "analyze_order", "compare_fx_route"},
    "deal_status": READONLY | KYB | DOCS | {"analyze_order", "get_alerts", "compare_fx_route"},
    # documents → smart model.
    "documents": DOCS | frozenset({"get_deal_summary", "explain_how_setu_works", "verify_party"}),
    "how_it_works": frozenset({"explain_how_setu_works", "get_deal_summary"}),
}
# Knowledge-base search (rules, definitions, how Setu works) is useful for every agent intent.
INTENT_TOOLS = {
    k: (v | {"search_knowledge"} if k not in ("greeting", "out_of_scope") else v)
    for k, v in INTENT_TOOLS.items()
}


AllowList = Callable[[Intent | None], frozenset[str]]


def intent_allowlist(intent: Intent | None) -> frozenset[str]:
    return INTENT_TOOLS.get(intent or "analysis", frozenset())


_default: ToolRegistry | None = None


def default_registry() -> ToolRegistry:
    global _default
    if _default is None:
        # Importing registers the finance, knowledge, KYB, document and escrow tools (one registry).
        # The escrow tools are Tier 2/3 and exist only so the guard can refuse them.
        from app.agent.tools import documents, escrow, finance, knowledge, kyb  # noqa: F401

        _default = finance.REGISTRY
    return _default
