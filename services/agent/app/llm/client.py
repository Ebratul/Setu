"""The only module that constructs chat models (CLAUDE.md rule 4).

Two providers for the same Claude models, chosen by `Settings.active_llm_provider`:
- anthropic: the Anthropic API (ANTHROPIC_API_KEY).
- openrouter: OpenRouter's Anthropic-compatible Messages endpoint (OPENROUTER_API_KEY), with
  model ids mapped to OpenRouter's names (claude-haiku-5-5 → anthropic/claude-haiku-5.5).
Model ids, token limits, timeouts and retries come from settings. The Anthropic SDK retries
connection errors, 408/409/429 and 5xx with exponential backoff (`LLM_MAX_RETRIES`).
Masking happens in the graph's `privacy_gateway` node before any call (TODO(P18): real masking);
the LLM cache (Phase 3.1 plan) is not wired yet.
"""

import re
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.config import get_settings

_VERSION = re.compile(r"-(\d+)-(\d+)$")


def openrouter_model_id(model: str) -> str:
    """Anthropic id → OpenRouter id; ids that already name a vendor are kept as given."""
    if "/" in model:
        return model
    return "anthropic/" + _VERSION.sub(r"-\1.\2", model)


def provider_model_id(model: str) -> str:
    if get_settings().active_llm_provider == "openrouter":
        return openrouter_model_id(model)
    return model


def anthropic_chat_model(model: str) -> BaseChatModel:
    settings = get_settings()
    provider = settings.active_llm_provider
    common = {
        "max_tokens": settings.llm_max_tokens,
        "default_request_timeout": settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        "stream_usage": True,
    }
    if provider == "anthropic" and settings.anthropic_api_key is not None:
        return ChatAnthropic(model=model, api_key=settings.anthropic_api_key, **common)
    if provider == "openrouter" and settings.openrouter_api_key is not None:
        key = settings.openrouter_api_key
        return ChatAnthropic(
            model=openrouter_model_id(model),
            api_key=key,
            base_url=settings.openrouter_base_url,
            # OpenRouter authenticates with a bearer token; X-Title labels the app in its dashboard.
            default_headers={
                "Authorization": f"Bearer {key.get_secret_value()}",
                "X-Title": "Setu",
            },
            **common,
        )
    raise RuntimeError("no LLM key set (ANTHROPIC_API_KEY or OPENROUTER_API_KEY); use mock mode")


def structured_call[T: BaseModel](
    schema: type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    tags: list[str] | None = None,
) -> T:
    """One structured-output call (`json_schema`) to a real model; never used in mock mode.
    The caller wraps untrusted text in <untrusted_document> tags and validates the result.
    Inputs go through the Privacy Gateway (identity stub until P18) and string values of the
    answer are unmasked with the same vault, like the chat path."""
    from app.security import privacy_gateway

    settings = get_settings()
    masked_system, masked_user = privacy_gateway.mask(system), privacy_gateway.mask(user)
    vault = {**masked_system.vault, **masked_user.vault}
    chat = anthropic_chat_model(model or settings.model_smart)
    runnable = chat.with_structured_output(schema, method="json_schema")
    out = runnable.invoke(
        [SystemMessage(masked_system.text), HumanMessage(masked_user.text)],
        config={"tags": ["setu", *(tags or [])]},
    )
    result = schema.model_validate(out)
    data = _unmask_strings(result.model_dump(), vault)
    return schema.model_validate(data)


def _unmask_strings(value: Any, vault: dict[str, str]) -> Any:
    from app.security import privacy_gateway

    if isinstance(value, str):
        return privacy_gateway.unmask(value, vault)
    if isinstance(value, dict):
        return {k: _unmask_strings(v, vault) for k, v in value.items()}
    if isinstance(value, list):
        return [_unmask_strings(v, vault) for v in value]
    return value
