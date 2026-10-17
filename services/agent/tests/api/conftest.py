from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import session as db_session
from app.main import create_app
from tests.conftest import TEST_AUDIT_KEY, _clear_caches


@pytest.fixture(scope="module")
def seeded_db(test_db_url: str) -> Iterator[str]:
    """Migrated + seeded *_test database shared by one test module (tests only read)."""
    from alembic.config import Config

    from alembic import command
    from app.config import AGENT_DIR
    from seed.cli import seed

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", test_db_url)
        mp.setenv("AUDIT_SIGNING_KEY", TEST_AUDIT_KEY)
        _clear_caches()
        cfg = Config(str(AGENT_DIR / "alembic.ini"))
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        seed()
        yield test_db_url
        db_session.get_batch_engine().dispose()
        engine = db_session.get_engine()
        if engine is not None:
            engine.dispose()
        _clear_caches()


@pytest.fixture
def client(seeded_db: str) -> TestClient:
    return TestClient(create_app())


def login(client: TestClient, email: str) -> TestClient:
    res = client.post("/auth/demo-login", json={"email": email})
    assert res.status_code == 200, res.text
    return client


@pytest.fixture(autouse=True)
def dev_evidence_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The dev evidence endpoint is opt-in (ENABLE_DEV_EVIDENCE); API tests turn it on."""
    from app.config import get_settings

    monkeypatch.setenv("ENABLE_DEV_EVIDENCE", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
