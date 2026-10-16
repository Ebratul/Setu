from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
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
    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "setu"

    audit_signing_key: SecretStr | None = None
    audit_dev_key_path: Path = REPO_ROOT / "keys" / "audit_dev_ed25519.key"

    demo_today: date = date(2026, 10, 20)

    # Demo "login as" stub (app/auth/demo.py). Replace with real auth before any non-demo use.
    demo_session_secret: SecretStr | None = None
    demo_cookie_secure: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
