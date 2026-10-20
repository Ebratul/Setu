from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import SecretStr

from app.api import (
    admin_onboarding,
    analysis,
    approvals,
    audit,
    auth,
    cashflow,
    chat,
    credit_records,
    deals,
    demo,
    documents,
    financing,
    health,
    inbox,
    injection,
    kyb,
    members,
    onboarding,
    privacy,
    registry,
    risk,
    suppliers,
)
from app.api.body_limit import BodyLimit
from app.api.ratelimit import RateLimit
from app.api.security_headers import SecurityHeaders
from app.audit.middleware import AuditActorMiddleware
from app.auth.deps import bind_actor
from app.config import Settings, get_settings
from app.demo.middleware import SandboxMiddleware
from app.errors import install_handlers


def _long_secret(name: str, value: SecretStr | None) -> None:
    if value is None or len(value.get_secret_value()) < 32:
        raise RuntimeError(f"{name} (>= 32 chars) is required when APP_ENV=prod")


def check_prod_settings(settings: Settings) -> None:
    """Refuse to start in prod with the demo auth stub's dev fallbacks, demo switches left on,
    missing secrets or an unconfigured mail provider."""
    if settings.auth_mode == "neon" and not settings.neon_auth_base_url:
        raise RuntimeError("NEON_AUTH_BASE_URL is required when AUTH_MODE=neon")
    if settings.app_env != "prod":
        return
    if settings.auth_mode != "neon":
        raise RuntimeError("AUTH_MODE=neon is required when APP_ENV=prod (the demo login is open)")
    if not (settings.neon_auth_base_url or "").startswith("https://"):
        raise RuntimeError("NEON_AUTH_BASE_URL must be an https URL when APP_ENV=prod")
    if "*" in settings.cors_origins or not settings.cors_origins:
        raise RuntimeError(
            "ALLOWED_ORIGINS must be an exact list of origins (no '*', not empty) when "
            "APP_ENV=prod: credentials are allowed"
        )
    secret = settings.demo_session_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise RuntimeError("DEMO_SESSION_SECRET (>= 32 chars) is required when APP_ENV=prod")
    if not settings.demo_cookie_secure:
        raise RuntimeError("DEMO_COOKIE_SECURE=true is required when APP_ENV=prod")
    if settings.demo_mode:
        raise RuntimeError("DEMO_MODE=false is required when APP_ENV=prod (no OTP in clear)")
    if settings.cooling_off_seconds < 600:
        raise RuntimeError("COOLING_OFF_SECONDS must be >= 600 when APP_ENV=prod (SR-9)")
    _long_secret("OTP_SECRET_SEED", settings.otp_secret_seed)
    _long_secret("DOCUMENT_URL_SECRET", settings.document_url_secret)
    _long_secret("CRON_SECRET", settings.cron_secret)
    if settings.mail_provider != "resend":
        raise RuntimeError("MAIL_PROVIDER=resend is required when APP_ENV=prod (codes are emailed)")
    key = settings.mail_resend_api_key
    if key is None or not key.get_secret_value().strip():
        raise RuntimeError("MAIL_RESEND_API_KEY is required when APP_ENV=prod")
    if not (settings.mail_from or "").strip():
        raise RuntimeError("MAIL_FROM is required when APP_ENV=prod")
    if any(not o.startswith("https://") for o in settings.cors_origins):
        raise RuntimeError("ALLOWED_ORIGINS must be https:// origins only when APP_ENV=prod")
    for name, on in (
        ("DEMO_REPLAY", settings.demo_replay),
        ("SANDBOXES_ENABLED", settings.sandboxes_enabled),
        ("ENABLE_DEV_EVIDENCE", settings.enable_dev_evidence),
        ("ONBOARDING_AUTO_APPROVE", settings.onboarding_auto_approve),
    ):
        if on:
            raise RuntimeError(f"{name}=false is required when APP_ENV=prod")
    if settings.stepup_required is False:
        raise RuntimeError("STEPUP_REQUIRED=false is not allowed when APP_ENV=prod")
    if settings.four_eyes_enforce is False:
        raise RuntimeError("FOUR_EYES_ENFORCE=false is not allowed when APP_ENV=prod")


def create_app() -> FastAPI:
    settings = get_settings()
    check_prod_settings(settings)
    app = FastAPI(
        title="Setu Agent API",
        version=settings.app_version,
        description="Setu AI SME Finance Copilot. All money movement is simulated.",
        dependencies=[Depends(bind_actor)],
    )
    app.add_middleware(AuditActorMiddleware)
    app.add_middleware(SandboxMiddleware)
    # Last added = outermost. Limits sit inside CORS, so 413/429 still carry CORS headers.
    app.add_middleware(BodyLimit)
    app.add_middleware(RateLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeaders)
    install_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    if settings.auth_mode == "demo":
        app.include_router(auth.demo_router)
    app.include_router(onboarding.router)
    app.include_router(admin_onboarding.router)
    app.include_router(members.router)
    app.include_router(analysis.router)
    app.include_router(cashflow.router)
    app.include_router(financing.router)
    app.include_router(chat.router)
    app.include_router(kyb.router)
    app.include_router(suppliers.router)
    app.include_router(deals.router)
    app.include_router(credit_records.router)
    app.include_router(documents.router)
    app.include_router(registry.router)
    app.include_router(risk.router)
    app.include_router(approvals.router)
    if settings.auth_mode == "demo":
        app.include_router(demo.router)
    app.include_router(inbox.router)
    app.include_router(privacy.router)
    app.include_router(injection.router)
    app.include_router(audit.router)
    return app


app = create_app()
