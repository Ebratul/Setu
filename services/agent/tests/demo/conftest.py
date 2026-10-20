"""Shared fixtures for the guided-demo tests: one migrated test database per module, the real app,
recorded AI fixtures (replay), nothing that needs a network or a model key."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import TEST_AUDIT_KEY, _clear_caches

pytestmark = pytest.mark.db

SCHEMAS_SQL = text(
    "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'sbx\\_%'"
)


@pytest.fixture(scope="module")
def demo_db(test_db_url: str) -> Iterator[str]:
    from alembic.config import Config

    from alembic import command
    from app.config import AGENT_DIR
    from app.db import session as db_session

    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", test_db_url)
    mp.setenv("AUDIT_SIGNING_KEY", TEST_AUDIT_KEY)
    mp.setenv("DEMO_MODE", "true")
    mp.setenv("COOLING_OFF_SECONDS", "30")
    mp.setenv("AGENT_MOCK_MODE", "true")
    mp.setenv("KB_EMBEDDER", "hash")
    mp.setenv("SANDBOX_CREATES_PER_HOUR_PER_IP", "1000")
    _clear_caches()
    engine = db_session.get_batch_engine()
    with engine.begin() as conn:  # sandbox schemas from an aborted run
        for (name,) in conn.execute(SCHEMAS_SQL).all():
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield test_db_url
    from app.demo import sandbox

    sandbox._cache.clear()
    with db_session.get_batch_engine().begin() as conn:
        for (name,) in conn.execute(SCHEMAS_SQL).all():
            conn.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
    db_session.get_batch_engine().dispose()
    mp.undo()
    _clear_caches()


@pytest.fixture(autouse=True)
def _demo_env(demo_db: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Function-level reset of what other autouse fixtures clear (settings and engine caches)."""
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", demo_db)
    monkeypatch.setenv("AUDIT_SIGNING_KEY", TEST_AUDIT_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    c = TestClient(app, base_url="http://localhost")
    yield c
    c.delete("/demo/sandbox")


def new_client(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app, base_url="http://localhost")
