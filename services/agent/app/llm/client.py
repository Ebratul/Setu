"""The only module that constructs Anthropic chat models (CLAUDE.md rule 4).

Model ids, token limits, timeouts and retries come from settings. The Anthropic SDK retries
connection errors, 408/409/429 and 5xx with exponential backoff (`LLM_MAX_RETRIES`).
Masking happens in the graph's `privacy_gateway` node before any call (TODO(P18): real masking);
the LLM cache (Phase 3.1 plan) is not wired yet.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from app.config import get_settings


def anthropic_chat_model(model: str) -> BaseChatModel:
    settings = get_settings()
    if not settings.has_anthropic_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; use AGENT_MOCK_MODE=true")
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        max_tokens=settings.llm_max_tokens,
        default_request_timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        stream_usage=True,
    )
