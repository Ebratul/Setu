"""The only module that constructs chat models (CLAUDE.md rule 4).

Providers, tried in this order (`Settings.llm_provider_chain`; only those with a key):
- openrouter: OpenRouter's Anthropic-compatible Messages endpoint (OPENROUTER_API_KEY), with
  model ids mapped to OpenRouter's names (claude-haiku-5-5 → anthropic/claude-haiku-5.5).
- anthropic: the Anthropic API (ANTHROPIC_API_KEY).
- xai: xAI Grok (XAI_API_KEY), the last resort; the model tier maps to XAI_MODEL_FAST / _SMART.
When a provider's quota, credit or key is used up (402/429/401/403 or a "credit balance" style
message) the call moves to the next provider (`FailoverChatModel`); other errors are raised.
Model ids, token limits, timeouts and retries come from settings. The Anthropic SDK retries
connection errors, 408/409/429 and 5xx with exponential backoff (`LLM_MAX_RETRIES`).
Masking (app/privacy): the graph masks its messages through the request's PrivacyGateway before
each call, and `structured_call` masks its own inputs; nothing reaches a provider or LangSmith
unmasked. The LLM cache (Phase 3.1 plan) is not wired yet.
"""

import re
from collections.abc import Iterator, Sequence
from typing import Any

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from langchain_xai import ChatXAI
from pydantic import BaseModel, Field

from app.config import get_settings

log = structlog.get_logger("setu.llm")

_VERSION = re.compile(r"-(\d+)-(\d+)$")


def openrouter_model_id(model: str) -> str:
    """Anthropic id → OpenRouter id; ids that already name a vendor are kept as given."""
    if "/" in model:
        return model
    return "anthropic/" + _VERSION.sub(r"-\1.\2", model)


def xai_model_id(model: str) -> str:
    """Claude tier id → the Grok model for the same tier; Grok ids are kept as given."""
    s = get_settings()
    if model.startswith("grok"):
        return model
    return s.xai_model_fast if model == s.model_fast else s.xai_model_smart


def provider_model_id(model: str) -> str:
    """The model id as the first provider in the chain names it."""
    provider = get_settings().active_llm_provider
    if provider == "openrouter":
        return openrouter_model_id(model)
    if provider == "xai":
        return xai_model_id(model)
    return model


def _build(provider: str, model: str) -> BaseChatModel:
    settings = get_settings()
    common = {
        "max_tokens": settings.llm_max_tokens,
        "max_retries": settings.llm_max_retries,
        "stream_usage": True,
    }
    if provider == "anthropic" and settings.anthropic_api_key is not None:
        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            default_request_timeout=settings.llm_timeout_seconds,
            **common,
        )
    if provider == "openrouter" and settings.openrouter_api_key is not None:
        key = settings.openrouter_api_key
        return ChatAnthropic(
            model=openrouter_model_id(model),
            api_key=key,
            base_url=settings.openrouter_base_url,
            default_request_timeout=settings.llm_timeout_seconds,
            # OpenRouter authenticates with a bearer token; X-Title labels the app in its dashboard.
            default_headers={
                "Authorization": f"Bearer {key.get_secret_value()}",
                "X-Title": "Setu",
            },
            **common,
        )
    if provider == "xai" and settings.xai_api_key is not None:
        return ChatXAI(
            model=xai_model_id(model),
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            timeout=settings.llm_timeout_seconds,
            **common,
        )
    raise RuntimeError(f"no API key set for LLM provider {provider!r}")


_QUOTA_WORDS = (
    "credit balance",
    "insufficient",
    "quota",
    "billing",
    "payment required",
    "rate limit",
    "usage limit",
    "spending limit",
    "exceeded your current",
    "out of credits",
)


def is_quota_error(exc: BaseException) -> bool:
    """True when a provider refused because its limit, credit or key is used up (so the next
    provider should be tried). Bad requests, timeouts and server errors are not quota errors."""
    status = getattr(exc, "status_code", None)
    if status in {401, 402, 403, 429}:
        return True
    return status in {None, 400} and any(w in str(exc).lower() for w in _QUOTA_WORDS)


class FailoverChatModel(BaseChatModel):
    """Tries each provider's model in order; moves to the next only on a quota-type error
    (`is_quota_error`). Tool binding and structured output are applied per provider, because each
    formats them differently. Streaming fails over only before the first chunk is produced."""

    candidates: list[BaseChatModel]
    labels: list[str]
    tools: list[Any] | None = None
    tool_kwargs: dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "setu-failover"

    def _bound(self, cand: BaseChatModel) -> Any:
        return cand if self.tools is None else cand.bind_tools(self.tools, **self.tool_kwargs)

    def _next(self, i: int, exc: Exception) -> None:
        if i == len(self.candidates) - 1 or not is_quota_error(exc):
            raise exc
        log.warning(
            "llm_provider_failover", failed=self.labels[i], next=self.labels[i + 1],
            error=type(exc).__name__, status=getattr(exc, "status_code", None),
        )  # fmt: skip

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        for i, cand in enumerate(self.candidates):
            try:
                ai = self._bound(cand).invoke(messages, stop=stop, **kwargs)
                return ChatResult(generations=[ChatGeneration(message=ai)])
            except Exception as exc:
                self._next(i, exc)
        raise RuntimeError("no LLM provider configured")

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        for i, cand in enumerate(self.candidates):
            started = False
            try:
                for chunk in self._bound(cand).stream(messages, stop=stop, **kwargs):
                    started = True
                    yield ChatGenerationChunk(message=chunk)  # type: ignore[arg-type]
                return
            except Exception as exc:
                if started:
                    raise
                self._next(i, exc)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FailoverChatModel":  # type: ignore[override]
        return self.model_copy(update={"tools": list(tools), "tool_kwargs": kwargs})

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:  # type: ignore[override]
        def run(value: Any, config: RunnableConfig | None = None) -> Any:
            for i, cand in enumerate(self.candidates):
                try:
                    return cand.with_structured_output(schema, **kwargs).invoke(value, config)
                except Exception as exc:
                    self._next(i, exc)
            raise RuntimeError("no LLM provider configured")

        return RunnableLambda(run)


def anthropic_chat_model(model: str) -> BaseChatModel:
    """The real chat model for a Claude tier id. One provider -> that provider's model; several
    keyed providers -> a FailoverChatModel (OpenRouter -> Anthropic -> xAI Grok by default)."""
    chain = get_settings().llm_provider_chain
    if not chain:
        raise RuntimeError(
            "no LLM key set (OPENROUTER_API_KEY, ANTHROPIC_API_KEY or XAI_API_KEY); use mock mode"
        )
    models = [_build(p, model) for p in chain]
    if len(models) == 1:
        return models[0]
    return FailoverChatModel(candidates=models, labels=list(chain))


def structured_call[T: BaseModel](
    schema: type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    tags: list[str] | None = None,
    node: str = "extract",
) -> T:
    """One structured-output call (`json_schema`) to a real model; never used in mock mode.
    The caller wraps untrusted text in <untrusted_document> tags and validates the result.
    Inputs are masked by the request's Privacy Gateway (a fresh one outside a request), the call
    is recorded masked, and string values of the answer are unmasked by code."""
    from app.privacy.context import current_gateway
    from app.privacy.gateway import PrivacyGateway

    settings = get_settings()
    gw = current_gateway() or PrivacyGateway()
    name = model or settings.model_smart
    messages, call = gw.protect(
        [SystemMessage(system), HumanMessage(user)], node=node, model=provider_model_id(name)
    )
    from app.agent.mock_llm import MockChatModel
    from app.llm import replay

    chat = anthropic_chat_model(name)
    if settings.sandboxes_enabled or settings.demo_replay or settings.demo_record:
        chat = replay.wrap(chat, name, fallback=MockChatModel(model_name="mock-smart"))
    runnable = chat.with_structured_output(schema, method="json_schema")
    out = runnable.invoke(messages, config={"tags": ["setu", *(tags or [])]})
    result = schema.model_validate(out)
    call.output = result.model_dump_json()
    data = gw.unmask(result.model_dump())
    return schema.model_validate(data)
