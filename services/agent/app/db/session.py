from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from app.config import get_settings


def _normalize_url(url: str) -> str:
    # Neon/Heroku-style URLs default to psycopg2 in SQLAlchemy; we use psycopg 3.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache
def get_engine() -> Engine | None:
    settings = get_settings()
    if settings.database_url is None:
        return None
    timeout_ms = int(settings.db_check_timeout_seconds * 1000)
    return create_engine(
        _normalize_url(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": max(1, int(settings.db_check_timeout_seconds)),
            "options": f"-c statement_timeout={timeout_ms}",
        },
    )


def ping() -> bool:
    """SELECT 1 against the configured database; never raises."""
    try:
        engine = get_engine()
        if engine is None:
            return False
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
