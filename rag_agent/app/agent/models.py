"""Model factory: real Claude models via app/llm/client.py, or the deterministic mock."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.agent.mock_llm import MockChatModel
from app.agent.state import ModelTier
from app.config import get_settings
from app.llm import replay
from app.llm.client import anthropic_chat_model, provider_model_id


@dataclass(frozen=True, slots=True)
class ModelSet:
    fast: BaseChatModel
    smart: BaseChatModel
    fast_id: str
    smart_id: str

    def for_tier(self, tier: ModelTier) -> BaseChatModel:
        return self.smart if tier == "smart" else self.fast

    def id_for(self, tier: ModelTier) -> str:
        return self.smart_id if tier == "smart" else self.fast_id


def mock_model(name: str) -> BaseChatModel:
    return MockChatModel(model_name=name)


def _model(tier: str, name: str) -> BaseChatModel:
    """The tier's chat model. With sandboxes or replay on it is wrapped so every call can be
    served from, or recorded to, the demo fixtures (app/llm/replay.py); otherwise unchanged."""
    s = get_settings()
    fallback = mock_model(f"mock-{tier}")
    real = None if s.use_mock_llm else anthropic_chat_model(name)
    if not (s.sandboxes_enabled or s.demo_replay or s.demo_record):
        return fallback if real is None else real
    return replay.wrap(real, name, fallback=fallback)


def get_fast_model() -> BaseChatModel:
    return _model("fast", get_settings().model_fast)


def get_smart_model() -> BaseChatModel:
    return _model("smart", get_settings().model_smart)


def get_models() -> ModelSet:
    s = get_settings()
    if s.use_mock_llm:
        return ModelSet(get_fast_model(), get_smart_model(), "mock-fast", "mock-smart")
    return ModelSet(
        get_fast_model(),
        get_smart_model(),
        provider_model_id(s.model_fast),
        provider_model_id(s.model_smart),
    )
