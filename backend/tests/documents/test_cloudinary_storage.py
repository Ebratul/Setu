import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import cloudinary.exceptions
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import NotFound, ServiceUnavailable
from app.services.documents import storage as mod
from app.services.documents.storage import DEMO_PREFIX, CloudinaryStorage

ROOT = Path(__file__).resolve().parents[3]


def settings(**kw: object) -> Settings:
    base = {
        "cloudinary_cloud_name": "demo",
        "cloudinary_api_key": SecretStr("key"),
        "cloudinary_api_secret": SecretStr("secret"),
    }
    return Settings(_env_file=None, **{**base, **kw})  # type: ignore[arg-type]


@pytest.fixture
def store() -> CloudinaryStorage:
    return CloudinaryStorage(settings(), ROOT)


def test_missing_credentials_fail_closed() -> None:
    with pytest.raises(ServiceUnavailable) as err:
        CloudinaryStorage(settings(cloudinary_api_secret=None), ROOT)
    assert err.value.code == "STORAGE_UNAVAILABLE"


def test_put_uploads_a_private_raw_asset(store: CloudinaryStorage, monkeypatch) -> None:
    up = MagicMock()
    monkeypatch.setattr(mod.cloudinary.uploader, "upload", up)
    assert store.put("onboarding/u1/abc.pdf", b"%PDF-1") == "onboarding/u1/abc.pdf"
    (file,), kw = up.call_args
    assert file.read() == b"%PDF-1"
    assert (kw["resource_type"], kw["type"]) == ("raw", "authenticated")
    assert kw["public_id"] == "onboarding/u1/abc.pdf"


@pytest.mark.parametrize("key", ["/abs.pdf", "a/../b.pdf", f"{DEMO_PREFIX}x.pdf"])
def test_unsafe_keys_are_refused(store: CloudinaryStorage, key: str) -> None:
    with pytest.raises(ValueError):
        store.put(key, b"x")


def test_get_reads_through_a_signed_url(store: CloudinaryStorage, monkeypatch) -> None:
    seen: list[str] = []

    def fake_open(url: str, timeout: int):
        seen.append(url)
        res = MagicMock()
        res.__enter__.return_value.read.return_value = b"bytes"
        return res

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_open)
    assert store.get("onboarding/u1/abc.pdf") == b"bytes"
    assert "/raw/authenticated/s--" in seen[0] and "secret" not in seen[0]


def test_get_maps_404_and_outages(store: CloudinaryStorage, monkeypatch) -> None:
    def failing(code: int):
        def fake_open(url: str, timeout: int):
            raise urllib.error.HTTPError(url, code, "x", {}, None)  # type: ignore[arg-type]

        return fake_open

    monkeypatch.setattr(mod.urllib.request, "urlopen", failing(404))
    with pytest.raises(NotFound):
        store.get("k.pdf")
    monkeypatch.setattr(mod.urllib.request, "urlopen", failing(503))
    with pytest.raises(ServiceUnavailable):
        store.get("k.pdf")


def test_api_errors_become_service_unavailable(store: CloudinaryStorage, monkeypatch) -> None:
    boom = MagicMock(side_effect=cloudinary.exceptions.Error("nope"))
    monkeypatch.setattr(mod.cloudinary.uploader, "upload", boom)
    monkeypatch.setattr(mod.cloudinary.uploader, "destroy", boom)
    with pytest.raises(ServiceUnavailable):
        store.put("k.pdf", b"x")
    with pytest.raises(ServiceUnavailable):
        store.delete("k.pdf")


def test_demo_files_never_leave_the_disk(store: CloudinaryStorage, monkeypatch) -> None:
    destroy = MagicMock()
    monkeypatch.setattr(mod.cloudinary.uploader, "destroy", destroy)
    store.delete(f"{DEMO_PREFIX}anything.pdf")
    destroy.assert_not_called()
