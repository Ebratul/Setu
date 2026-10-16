from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def database_url() -> str:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    return normalize_url(settings.database_url.get_secret_value())


LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_local_url(url: str) -> bool:
    return make_url(normalize_url(url)).host in LOCAL_HOSTS


def normalize_url(url: str) -> str:
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
        normalize_url(settings.database_url.get_secret_value()),
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


@lru_cache
def get_batch_engine() -> Engine:
    """Engine for migrations/seed/scripts: no short statement timeout."""
    return create_engine(database_url(), pool_pre_ping=True)


@contextmanager
def batch_session() -> Iterator[Session]:
    """Session that commits on success and rolls back on error (seed and scripts)."""
    with sessionmaker(get_batch_engine(), expire_on_commit=False)() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
