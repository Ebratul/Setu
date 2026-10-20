from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
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
    privacy,
    registry,
    risk,
    suppliers,
)
from app.api.body_limit import BodyLimit
from app.api.ratelimit import RateLimit
from app.api.security_headers import SecurityHeaders
from app.audit.middleware import AuditActorMiddleware
from app.config import Settings, get_settings
from app.demo.middleware import SandboxMiddleware
from app.errors import install_handlers


def check_prod_settings(settings: Settings) -> None:
    """Refuse to start in prod with the demo auth stub's dev fallbacks."""
    if settings.app_env != "prod":
        return
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


def create_app() -> FastAPI:
    settings = get_settings()
    check_prod_settings(settings)
    app = FastAPI(
        title="Setu Agent API",
        version=settings.app_version,
        description="Setu AI SME Finance Copilot. All money movement is simulated.",
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
    app.include_router(demo.router)
    app.include_router(inbox.router)
    app.include_router(privacy.router)
    app.include_router(injection.router)
    app.include_router(audit.router)
    return app


app = create_app()
