import base64
import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.db import session as db_session
from app.db.session import LOCAL_HOSTS

TEST_AUDIT_KEY = base64.b64encode(bytes(range(32))).decode()


def _clear_caches() -> None:
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_batch_engine.cache_clear()


@pytest.fixture
def audit_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Deterministic audit signing key so tests never create or read keys/."""
    monkeypatch.setenv("AUDIT_SIGNING_KEY", TEST_AUDIT_KEY)
    _clear_caches()
    yield
    _clear_caches()


def unsafe_test_db_reason(url: str, main_url: str | None) -> str | None:
    """Why `url` must not be used as a throwaway test database (tests drop every table in it)."""
    target = make_url(db_session.normalize_url(url))
    if target.host not in LOCAL_HOSTS:
        return f"host {target.host!r} is not local"
    if not (target.database or "").endswith("_test"):
        return f"database {target.database!r} does not end in '_test'"
    if main_url is not None:
        main = make_url(db_session.normalize_url(main_url))
        if (main.host, main.port, main.database) == (target.host, target.port, target.database):
            return "test database is the same as DATABASE_URL"
    return None


def _test_db_url() -> str | None:
    """TEST_DATABASE_URL, else '<db>_test' next to a *local* DATABASE_URL. Anything unsafe stops
    the run, so tests can never drop tables in a hosted or dev database."""
    settings = get_settings()
    main_url = settings.database_url.get_secret_value() if settings.database_url else None
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if main_url is None or not db_session.is_local_url(main_url):
            return None
        main = make_url(db_session.normalize_url(main_url))
        url = main.set(database=f"{main.database}_test").render_as_string(hide_password=False)
    reason = unsafe_test_db_reason(url, main_url)
    if reason:
        pytest.exit(f"refusing to use test database: {reason}", returncode=2)
    return db_session.normalize_url(url)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = _test_db_url()
    if url is None:
        pytest.skip("no local Postgres configured (set TEST_DATABASE_URL)")
    target = make_url(url)
    try:
        admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            exists = conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": target.database}
            )
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
        admin.dispose()
    except Exception as exc:  # pragma: no cover - depends on local docker
        pytest.skip(f"Postgres not reachable: {type(exc).__name__}")
    return url


@pytest.fixture
def migrated_db(
    test_db_url: str, monkeypatch: pytest.MonkeyPatch, audit_key: None
) -> Iterator[str]:
    """Fresh schema at head in the test database; DATABASE_URL points at it for the test."""
    from alembic.config import Config

    from alembic import command
    from app.config import AGENT_DIR

    monkeypatch.setenv("DATABASE_URL", test_db_url)
    _clear_caches()
    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield test_db_url
    db_session.get_batch_engine().dispose()
    _clear_caches()


@pytest.fixture(autouse=True)
def kb_hash_embedder(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never load or download the embedding model unless a test builds one explicitly."""
    monkeypatch.setenv("KB_EMBEDDER", "hash")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def default_to_mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A real key in a developer's .env must never make the tests call a model."""
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    for key in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
