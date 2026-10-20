import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from app.config import Settings, get_settings
from app.llm.client import FailoverChatModel, anthropic_chat_model, is_quota_error, xai_model_id


class QuotaError(Exception):
    def __init__(self, status: int, msg: str = "") -> None:
        super().__init__(msg or f"HTTP {status}")
        self.status_code = status


class Exhausted(GenericFakeChatModel):
    status: int = 429

    def _generate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise QuotaError(self.status)


def _ok(text: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=text)]))


@pytest.mark.parametrize("status", [401, 402, 403, 429])
def test_quota_statuses(status: int) -> None:
    assert is_quota_error(QuotaError(status))


@pytest.mark.parametrize(
    "exc",
    [QuotaError(500), QuotaError(404), ValueError("bad schema"), httpx.ReadTimeout("slow")],
)
def test_other_errors_are_not_quota(exc: Exception) -> None:
    assert not is_quota_error(exc)


def test_credit_balance_message_is_quota() -> None:
    assert is_quota_error(QuotaError(400, "Your credit balance is too low to access the API"))


def test_falls_over_to_the_next_provider_on_quota() -> None:
    m = FailoverChatModel(
        candidates=[Exhausted(messages=iter([])), _ok("from grok")], labels=["a", "b"]
    )
    assert m.invoke([HumanMessage("hi")]).content == "from grok"


def test_non_quota_error_is_raised_not_swallowed() -> None:
    bad = Exhausted(messages=iter([]), status=500)
    m = FailoverChatModel(candidates=[bad, _ok("x")], labels=["a", "b"])
    with pytest.raises(QuotaError):
        m.invoke([HumanMessage("hi")])


def test_last_provider_quota_error_is_raised() -> None:
    m = FailoverChatModel(
        candidates=[Exhausted(messages=iter([])), Exhausted(messages=iter([]))], labels=["a", "b"]
    )
    with pytest.raises(QuotaError):
        m.invoke([HumanMessage("hi")])


def test_stream_fails_over_before_first_chunk() -> None:
    m = FailoverChatModel(
        candidates=[Exhausted(messages=iter([])), _ok("hello world")], labels=["a", "b"]
    )
    assert "".join(c.content for c in m.stream([HumanMessage("hi")])) == "hello world"


def test_chain_order_and_single_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MOCK_MODE", "false")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    for k, v in {"OPENROUTER_API_KEY": "o", "ANTHROPIC_API_KEY": "a", "XAI_API_KEY": "x"}.items():
        monkeypatch.setenv(k, v)
    assert Settings().llm_provider_chain == ["openrouter", "anthropic", "xai"]
    get_settings.cache_clear()
    m = anthropic_chat_model("claude-haiku-5-5")
    assert isinstance(m, FailoverChatModel) and m.labels == ["openrouter", "anthropic", "xai"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("XAI_API_KEY", "")
    get_settings.cache_clear()
    assert not isinstance(anthropic_chat_model("claude-haiku-5-5"), FailoverChatModel)


def test_grok_model_follows_the_tier() -> None:
    s = get_settings()
    assert xai_model_id(s.model_fast) == s.xai_model_fast
    assert xai_model_id(s.model_smart) == s.xai_model_smart
    assert xai_model_id("grok-4") == "grok-4"
