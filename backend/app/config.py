import os
import tempfile
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_DIR = Path(__file__).resolve().parent.parent  # the backend/ folder
# In a staged bundle (Vercel) data/, docs/ and rag_agent/ sit inside backend/ itself.
REPO_ROOT = AGENT_DIR if (AGENT_DIR / "rag_agent").is_dir() else AGENT_DIR.parent
RAG_AGENT_DIR = REPO_ROOT / "rag_agent"
# Vercel's bundle is read-only; only /tmp is writable (per instance, not durable).
DEFAULT_STORAGE_DIR = (
    Path(tempfile.gettempdir()) / "setu-storage"
    if os.environ.get("VERCEL")
    else AGENT_DIR / "storage"
)


class Settings(BaseSettings):
    """Loaded from env, then root .env, rag_agent/.env, then backend/.env (later files win)."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", RAG_AGENT_DIR / ".env", AGENT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_version: str = "0.1.0"
    app_env: Literal["dev", "test", "prod"] = "dev"
    database_url: SecretStr | None = None
    # Dev/test-only POST /milestones/{id}/evidence: explicit opt-in, ignored when APP_ENV=prod.
    enable_dev_evidence: bool = False
    db_check_timeout_seconds: float = 2.0
    allowed_origins: str = "http://localhost:3000"
    # Build identity for /health (set by CI / the Docker build args; never secrets).
    git_sha: str | None = Field(
        None, validation_alias=AliasChoices("GIT_SHA", "VERCEL_GIT_COMMIT_SHA")
    )
    build_time: str | None = None

    # Edge protection (app/api/ratelimit.py, body_limit.py). In-process sliding windows: each
    # worker / instance counts on its own, so the effective limit is N x workers.
    rate_limit_enabled: bool = True
    rate_limit_chat_per_minute: int = Field(20, ge=1)
    rate_limit_upload_per_minute: int = Field(10, ge=1)
    rate_limit_sandbox_create_per_minute: int = Field(5, ge=1)
    rate_limit_global_per_minute: int = Field(300, ge=1)
    # Comma list of proxy IPs/CIDRs whose X-Forwarded-For is believed ("*" = every peer is a
    # trusted proxy, only when the app is unreachable except through one).
    trusted_proxies: str = ""
    max_body_bytes: int = Field(1024 * 1024, gt=0)  # every non-upload request body

    anthropic_api_key: SecretStr | None = None
    # OpenRouter's Anthropic-compatible endpoint (same Claude models, routed via openrouter.ai).
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api"
    # xAI Grok (OpenAI-compatible API): last-resort fallback once the others' quota is used up.
    xai_api_key: SecretStr | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model_fast: str = "grok-4-fast"
    xai_model_smart: str = "grok-4"
    # auto: OpenRouter, then Anthropic, then xAI Grok (only providers with a key). A named provider
    # goes first (and must have a key); keyed providers after it stay as fallbacks.
    llm_provider: Literal["auto", "openrouter", "anthropic", "xai"] = "auto"
    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str = "setu"

    # Privacy Gateway (app/privacy). Amounts in documents and tool outputs are masked by default.
    privacy_enabled: bool = True
    privacy_mask_amounts: bool = True

    # Prompt-injection defences (app/security/injection). INJECTION_DEFENCES=off disables layers
    # 2 (detector), 4 (tool gating) and 5 (output guard) for the evaluation only: layer 3 (money
    # safety: propose-only tools, Tier 3 on document-borne instructions) is never switchable.
    injection_defences: Literal["on", "off"] = "on"
    injection_llm_check: bool = False  # optional fast-model second opinion; rules win on conflict

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

    # Document forensics (app/services/documents, app/forensics). Weights: docs/forensics.md.
    storage_dir: Path = DEFAULT_STORAGE_DIR  # git-ignored; never under a public folder
    storage_backend: Literal["local", "s3"] = "local"
    # <= 4 MB: Vercel functions reject request bodies over 4.5 MB (multipart framing included).
    document_max_bytes: int = Field(4 * 1024 * 1024, gt=0)
    document_url_ttl_seconds: int = Field(300, gt=0, le=3600)
    document_url_secret: SecretStr | None = None  # falls back to DEMO_SESSION_SECRET / dev value
    forensics_quantity_tolerance_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    forensics_money_tolerance: Decimal = Field(Decimal("0.01"), ge=0)
    forensics_min_transit_days: int = Field(7, ge=0)
    forensics_warn_score: int = Field(30, ge=0, le=100)  # score >= this -> WARNING
    forensics_fail_score: int = Field(60, ge=0, le=100)  # score > this -> FAILED
    forensics_sandbox: bool = True  # parse PDFs in a resource-limited child process
    forensics_parse_timeout_seconds: float = Field(20.0, gt=0)
    forensics_parse_memory_mb: int = Field(1024, ge=128)
    forensics_llm_extraction: bool = True  # still skipped in mock mode (no network)
    forensics_vision: bool = False  # optional vision model for photo checks (off by default)

    # Approvals (app/services/approvals.py). DEMO_MODE shows the simulated "Demo phone" inbox; with
    # DEMO_MODE=false no OTP ever leaves the server. COOLING_OFF_SECONDS: 600, 30 for demos.
    demo_mode: bool = True
    cooling_off_seconds: int = Field(
        600,
        ge=0,
        le=86_400,
        validation_alias=AliasChoices("COOLING_OFF_SECONDS", "DEMO_COOLING_OFF_SECONDS"),
    )
    approval_expiry_minutes: int = Field(1440, gt=0)
    otp_ttl_seconds: int = Field(300, gt=0)
    otp_max_attempts: int = Field(3, gt=0, le=10)
    otp_secret_seed: SecretStr | None = None  # falls back to the demo session secret / dev value
    # Four-eyes: the person who asked for an approval may not approve it (unless they are the only
    # OWNER/FINANCE member). None = on when AUTH_MODE=neon, off in the demo.
    four_eyes_enforce: bool | None = None
    # Email-code step-up for admin actions, Tier 2 approvals and member changes (AUTH_MODE=neon).
    # None = on in neon mode. Refused as false when APP_ENV=prod.
    stepup_required: bool | None = None
    stepup_code_ttl_seconds: int = Field(300, gt=0, le=900)
    stepup_token_ttl_seconds: int = Field(600, gt=0, le=3600)

    # Outgoing mail (app/services/mail.py): console logs only, resend sends via api.resend.com.
    mail_provider: Literal["console", "resend"] = "console"
    mail_from: str | None = None
    mail_resend_api_key: SecretStr | None = None

    # Guided demo (app/demo). DEMO_REPLAY serves every LLM call from recorded fixtures keyed by the
    # masked prompt, so a run is identical and works offline. DEMO_RECORD calls the real model and
    # writes fixtures (pnpm demo:record). Judge sandboxes are one Postgres schema each.
    demo_replay: bool = False
    demo_record: bool = False
    demo_fixtures_dir: Path = REPO_ROOT / "data" / "demo" / "fixtures"
    demo_steps_path: Path = REPO_ROOT / "data" / "demo" / "demo_steps.yaml"
    sandboxes_enabled: bool = True
    sandbox_ttl_hours: float = Field(4.0, gt=0, le=72)
    sandbox_max_active: int = Field(40, ge=1)
    sandbox_requests_per_minute: int = Field(600, ge=10)
    sandbox_chat_per_minute: int = Field(12, ge=1)
    sandbox_upload_per_minute: int = Field(12, ge=1)
    sandbox_live_ai_budget: int = Field(25, ge=0)
    sandbox_creates_per_hour_per_ip: int = Field(12, ge=1)
    cron_secret: SecretStr | None = None  # Bearer secret of POST /demo/cleanup
    demo_step_timeout_seconds: float = Field(60.0, gt=0)

    # AUTH_MODE=demo: the "login as" stub (app/auth/demo.py), judge deployment only.
    # AUTH_MODE=neon: Neon Auth (Managed Better Auth) JWTs verified via its JWKS (app/auth/neon.py).
    auth_mode: Literal["demo", "neon"] = "demo"
    neon_auth_base_url: str | None = None
    neon_auth_jwks_ttl_seconds: int = Field(600, ge=30)
    demo_session_secret: SecretStr | None = None
    demo_cookie_secure: bool = False

    # Self-service onboarding (app/services/onboarding.py).
    onboarding_countries: str = "BD,CN"  # comma list of ISO-2 codes a party may register from
    onboarding_auto_approve: bool = False  # approve clean (AUTO_CLEAR) submissions without an admin
    # P30 role gates: an allowlisted email becomes ADMIN on sign-up; an invite code makes a JUDGE.
    admin_email_allowlist: str = ""  # comma list, case-insensitive
    judge_invite_codes: SecretStr | None = None  # comma list
    terms_version: str = "2026-10"
    google_signin_enabled: bool | None = None  # None = on in neon mode
    sms_provider: Literal["console", "webhook"] = "console"
    sms_webhook_url: str | None = None  # POST {to, text, message_id}; https only in prod
    sms_webhook_token: SecretStr | None = None
    # Field encryption (app/security/crypto.py): comma list of Fernet keys, newest first.
    field_encryption_key: SecretStr | None = None
    phone_hash_secret: SecretStr | None = None  # falls back to OTP_SECRET_SEED
    # Business-id formats (regex, applied to the upper-cased value without spaces).
    bd_trade_license_regex: str = r"^[A-Z0-9][A-Z0-9/\-]{4,31}$"
    bd_irc_regex: str = r"^[A-Z0-9][A-Z0-9/\-]{4,31}$"
    bd_tin_regex: str = r"^\d{9,13}$"
    phone_otp_ttl_seconds: int = Field(300, gt=0, le=900)
    phone_otp_max_attempts: int = Field(5, gt=0, le=10)
    phone_otp_max_sends: int = Field(3, gt=0, le=10)
    phone_otp_send_window_seconds: int = Field(600, gt=0)
    # P30 per-user / per-IP abuse limits (app/api/ratelimit.py `check_limit`).
    rate_limit_auth_per_minute: int = Field(30, ge=1)  # /auth/session, callbacks
    rate_limit_role_per_10min: int = Field(10, ge=1)  # role / invite-code attempts, per IP
    rate_limit_onboarding_upload_per_hour: int = Field(10, ge=1)
    rate_limit_submit_per_hour: int = Field(5, ge=1)
    rate_limit_reveal_per_hour: int = Field(30, ge=1)
    rate_limit_mfa_per_10min: int = Field(10, ge=1)

    @property
    def four_eyes_active(self) -> bool:
        if self.four_eyes_enforce is not None:
            return self.four_eyes_enforce
        return self.auth_mode == "neon"

    @property
    def stepup_enabled(self) -> bool:
        if self.auth_mode != "neon":
            return False
        return True if self.stepup_required is None else self.stepup_required

    @property
    def admin_allowlist(self) -> frozenset[str]:
        return frozenset(
            e.strip().lower() for e in self.admin_email_allowlist.split(",") if e.strip()
        )

    @property
    def judge_codes(self) -> list[str]:
        raw = self.judge_invite_codes.get_secret_value() if self.judge_invite_codes else ""
        return [c.strip() for c in raw.split(",") if c.strip()]

    # Opt-in to keep the seeded demo login/cookie next to Neon sign-in (staging only; never prod).
    demo_cookie_in_neon: bool = True

    @property
    def demo_login_enabled(self) -> bool:
        """The "login as" routes, the signed demo cookie and the MFA-exempt seeded admin exist only
        in the demo deployment (AUTH_MODE=demo). With AUTH_MODE=neon they need the explicit
        DEMO_COOKIE_IN_NEON flag as well, and never in prod."""
        if not self.demo_mode or self.app_env == "prod":
            return False
        return self.auth_mode == "demo" or self.demo_cookie_in_neon

    @property
    def demo_enabled(self) -> bool:
        """Demo conveniences that are not a login (OTP echo, auto-approve) need DEMO_MODE."""
        return self.demo_mode and self.app_env != "prod"

    @property
    def google_enabled(self) -> bool:
        if self.google_signin_enabled is not None:
            return self.google_signin_enabled
        return self.auth_mode == "neon"

    @property
    def onboarding_country_list(self) -> list[str]:
        return [c.strip().upper() for c in self.onboarding_countries.split(",") if c.strip()]

    @property
    def neon_auth_origin(self) -> str | None:
        """Issuer and audience of Neon Auth JWTs: the scheme+host of the Auth URL."""
        if not self.neon_auth_base_url:
            return None
        parts = urlsplit(self.neon_auth_base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def neon_auth_jwks_url(self) -> str | None:
        if not self.neon_auth_base_url:
            return None
        return f"{self.neon_auth_base_url.rstrip('/')}/.well-known/jwks.json"

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
    def has_xai_key(self) -> bool:
        return self._usable(self.xai_api_key)

    @property
    def llm_provider_chain(self) -> list[Literal["openrouter", "anthropic", "xai"]]:
        """Providers to try, in order. A call moves to the next one when a provider's quota,
        credit or key is exhausted (see app/llm/client.py)."""
        have: dict[str, bool] = {
            "openrouter": self.has_openrouter_key,
            "anthropic": self.has_anthropic_key,
            "xai": self.has_xai_key,
        }
        order = ["openrouter", "anthropic", "xai"]
        if self.llm_provider != "auto":
            if not have[self.llm_provider]:
                return []
            order.remove(self.llm_provider)
            order.insert(0, self.llm_provider)
        return [p for p in order if have[p]]  # type: ignore[misc]

    @property
    def active_llm_provider(self) -> Literal["anthropic", "openrouter", "xai"] | None:
        """The provider real model calls go to first, or None (then mock mode)."""
        chain = self.llm_provider_chain
        return chain[0] if chain else None

    @property
    def use_mock_llm(self) -> bool:
        return self.agent_mock_mode or self.active_llm_provider is None

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
