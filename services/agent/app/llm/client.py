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

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

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
