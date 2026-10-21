"""Fixtures for the injection tests: the pure ones need nothing; the DB ones use the migrated,
seeded `*_test` database (one per module) and a mock model so nothing touches the network."""

from collections.abc import Iterator

import pytest

from app.config import get_settings
from tests.api.conftest import client, seeded_db  # noqa: F401  (fixtures)


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("DOCUMENT_URL_SECRET", "test-document-url-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
