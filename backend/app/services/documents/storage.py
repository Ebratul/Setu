"""File storage behind an interface. Files live outside any public folder: the local backend
writes under `storage/` (git-ignored), the cloudinary backend into private assets, with names
derived from the sha256, never from user input.
Seeded demo rows point at the committed `data/demo/...` files, which are read-only here."""

import io
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final, Protocol

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import cloudinary.utils
import structlog

from app.config import REPO_ROOT, Settings, get_settings
from app.errors import NotFound, ServiceUnavailable

DEMO_PREFIX = "data/demo/"
log = structlog.get_logger("setu.storage")
FETCH_TIMEOUT_SECONDS = 15


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> str:
        """Store bytes under a relative key; returns the path to keep in `Document.storage_path`."""
        ...

    def get(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, path: str) -> Path:
        base = REPO_ROOT if path.startswith(DEMO_PREFIX) else self.root
        full = (base / path).resolve()
        if not full.is_relative_to(base.resolve()):
            raise NotFound("file not found")
        return full

    def put(self, key: str, data: bytes) -> str:
        if key.startswith(("/", DEMO_PREFIX)) or ".." in Path(key).parts:
            raise ValueError("invalid storage key")
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return key

    def get(self, path: str) -> bytes:
        full = self._resolve(path)
        if not full.is_file():
            raise NotFound("file not found")
        return full.read_bytes()

    def delete(self, path: str) -> None:
        if path.startswith(DEMO_PREFIX):
            return  # the committed demo files are read-only
        self._resolve(path).unlink(missing_ok=True)


class CloudinaryStorage:
    """Cloudinary backend. Assets are `raw` + `authenticated`, so a bare URL never serves them:
    reads go through a signed delivery URL built with the API secret. Keys are the same
    sha256-derived names as the local backend; the committed `data/demo/` files stay on disk."""

    RAW: Final = {"resource_type": "raw", "type": "authenticated"}

    def __init__(self, settings: Settings, demo_root: Path) -> None:
        key, secret = settings.cloudinary_api_key, settings.cloudinary_api_secret
        if not (settings.cloudinary_cloud_name and key and secret):
            raise ServiceUnavailable("object storage is not configured", "STORAGE_UNAVAILABLE")
        self.creds = {
            "cloud_name": settings.cloudinary_cloud_name.strip(),
            "api_key": key.get_secret_value().strip(),
            "api_secret": secret.get_secret_value().strip(),
            "secure": True,
        }
        self._demo = LocalStorage(demo_root)

    @staticmethod
    def _unavailable() -> ServiceUnavailable:
        return ServiceUnavailable("object storage is unavailable", "STORAGE_UNAVAILABLE")

    def put(self, key: str, data: bytes) -> str:
        if key.startswith(("/", DEMO_PREFIX)) or ".." in Path(key).parts:
            raise ValueError("invalid storage key")
        try:
            cloudinary.uploader.upload(
                io.BytesIO(data), public_id=key, overwrite=True, invalidate=True,
                **self.RAW, **self.creds,
            )  # fmt: skip
        except cloudinary.exceptions.Error as exc:
            log.warning("storage_put_failed", error=type(exc).__name__, reason=str(exc)[:200])
            raise self._unavailable() from exc
        return key

    def get(self, path: str) -> bytes:
        if path.startswith(DEMO_PREFIX):
            return self._demo.get(path)
        url, _ = cloudinary.utils.cloudinary_url(path, sign_url=True, **self.RAW, **self.creds)
        try:
            with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as res:
                return res.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFound("file not found") from exc
            raise self._unavailable() from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise self._unavailable() from exc

    def delete(self, path: str) -> None:
        if path.startswith(DEMO_PREFIX):
            return
        try:
            cloudinary.uploader.destroy(path, invalidate=True, **self.RAW, **self.creds)
        except cloudinary.exceptions.Error as exc:
            raise self._unavailable() from exc


def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "cloudinary":
        return CloudinaryStorage(settings, REPO_ROOT)
    root = settings.storage_dir
    return LocalStorage(root if root.is_absolute() else REPO_ROOT / root)
