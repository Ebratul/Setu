from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_DIR.parent.parent


class Settings(BaseSettings):
    """Loaded from env, then root .env, then services/agent/.env (later files win)."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", AGENT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"
    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: SecretStr | None = None
    db_check_timeout_seconds: float = 2.0
    allowed_origins: str = "http://localhost:3000"

    anthropic_api_key: SecretStr | None = None
    # OpenRouter's Anthropic-compatible endpoint (same Claude models, routed via openrouter.ai).
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api"
    # auto: Anthropic if ANTHROPIC_API_KEY is set, else OpenRouter if OPENROUTER_API_KEY is set.
    llm_provider: Literal["auto", "anthropic", "openrouter"] = "auto"
    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "setu"

    # Knowledge base (app/rag). Local multilingual model, Apache-2.0; "hash" = offline test stub.
    kb_embedder: Literal["fastembed", "hash"] = "fastembed"
    kb_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    kb_model_cache_dir: Path = Path.home() / ".cache" / "setu-fastembed"

    # Agent (app/agent). Model ids come from env; SETU_MODEL_* are the older names.
    model_fast: str = Field(
        "claude-haiku-5-5", validation_alias=AliasChoices("MODEL_FAST", "SETU_MODEL_FAST")
    )
    model_smart: str = Field(
        "claude-sonnet-5-5", validation_alias=AliasChoices("MODEL_SMART", "SETU_MODEL_REASONING")
    )
    llm_max_tokens: int = 2048
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    thread_token_budget: int = 60_000
    agent_max_tool_steps: int = 6
    # true, or no usable LLM key, -> deterministic offline model (dev, tests, demo).
    agent_mock_mode: bool = False

    audit_signing_key: SecretStr | None = None
    audit_dev_key_path: Path = REPO_ROOT / "keys" / "audit_dev_ed25519.key"

    demo_today: date = date(2026, 10, 20)

    # Supplier KYB (app/domain/kyb.py): name-match bands and the mock sanctions list.
    kyb_match_threshold: float = Field(92.0, ge=0, le=100)
    kyb_partial_threshold: float = Field(80.0, ge=0, le=100)
    kyb_sanctions_path: Path = Path("data/demo/sanctions_mock.json")  # relative to REPO_ROOT

    # Demo "login as" stub (app/auth/demo.py). Replace with real auth before any non-demo use.
    demo_session_secret: SecretStr | None = None
    demo_cookie_secure: bool = False

    @property
    def kyb_sanctions_file(self) -> Path:
        path = self.kyb_sanctions_path
        return path if path.is_absolute() else REPO_ROOT / path

    @staticmethod
    def _usable(key: SecretStr | None) -> bool:
        return key is not None and bool(key.get_secret_value().strip())

    @property
    def has_anthropic_key(self) -> bool:
        return self._usable(self.anthropic_api_key)

    @property
    def has_openrouter_key(self) -> bool:
        return self._usable(self.openrouter_api_key)

    @property
    def active_llm_provider(self) -> Literal["anthropic", "openrouter"] | None:
        """The provider real model calls go to, or None (then mock mode)."""
        if self.llm_provider == "anthropic":
            return "anthropic" if self.has_anthropic_key else None
        if self.llm_provider == "openrouter":
            return "openrouter" if self.has_openrouter_key else None
        if self.has_anthropic_key:
            return "anthropic"
        return "openrouter" if self.has_openrouter_key else None

    @property
    def use_mock_llm(self) -> bool:
        return self.agent_mock_mode or self.active_llm_provider is None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
