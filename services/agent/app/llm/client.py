"""The only module that constructs chat models (CLAUDE.md rule 4).

Two providers for the same Claude models, chosen by `Settings.active_llm_provider`:
- anthropic: the Anthropic API (ANTHROPIC_API_KEY).
- openrouter: OpenRouter's Anthropic-compatible Messages endpoint (OPENROUTER_API_KEY), with
  model ids mapped to OpenRouter's names (claude-haiku-5-5 → anthropic/claude-haiku-5.5).
Model ids, token limits, timeouts and retries come from settings. The Anthropic SDK retries
connection errors, 408/409/429 and 5xx with exponential backoff (`LLM_MAX_RETRIES`).
Masking (app/privacy): the graph masks its messages through the request's PrivacyGateway before
each call, and `structured_call` masks its own inputs; nothing reaches a provider or LangSmith
unmasked. The LLM cache (Phase 3.1 plan) is not wired yet.
"""

import re

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
