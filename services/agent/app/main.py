from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, auth, cashflow, financing, health
from app.config import Settings, get_settings
from app.errors import install_handlers


def check_prod_settings(settings: Settings) -> None:
    """Refuse to start in prod with the demo auth stub's dev fallbacks."""
    if settings.app_env != "prod":
        return
    secret = settings.demo_session_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise RuntimeError("DEMO_SESSION_SECRET (>= 32 chars) is required when APP_ENV=prod")
    if not settings.demo_cookie_secure:
        raise RuntimeError("DEMO_COOKIE_SECURE=true is required when APP_ENV=prod")
    if "*" in settings.cors_origins:
        raise RuntimeError("ALLOWED_ORIGINS must not contain '*' (credentials are allowed)")


def create_app() -> FastAPI:
    settings = get_settings()
    check_prod_settings(settings)
    app = FastAPI(
        title="Setu Agent API",
        version=settings.app_version,
        description="Setu AI SME Finance Copilot. All money movement is simulated.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(analysis.router)
    app.include_router(cashflow.router)
    app.include_router(financing.router)
    return app


app = create_app()
