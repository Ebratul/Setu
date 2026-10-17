"""Model factory: real Claude models via app/llm/client.py, or the deterministic mock."""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.agent.mock_llm import MockChatModel
from app.agent.state import ModelTier
from app.config import get_settings
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


def get_fast_model() -> BaseChatModel:
    s = get_settings()
    return mock_model("mock-fast") if s.use_mock_llm else anthropic_chat_model(s.model_fast)


def get_smart_model() -> BaseChatModel:
    s = get_settings()
    return mock_model("mock-smart") if s.use_mock_llm else anthropic_chat_model(s.model_smart)


def get_models() -> ModelSet:
    s = get_settings()
    if s.use_mock_llm:
        return ModelSet(
            mock_model("mock-fast"), mock_model("mock-smart"), "mock-fast", "mock-smart"
        )
    return ModelSet(
        get_fast_model(),
        get_smart_model(),
        provider_model_id(s.model_fast),
        provider_model_id(s.model_smart),
    )
