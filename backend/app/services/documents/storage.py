"""File storage behind an interface. Files live outside any public folder: the local backend
writes under `storage/` (git-ignored) with names derived from the sha256, never from user input.
Seeded demo rows point at the committed `data/demo/...` files, which are read-only here."""

import os
import tempfile
from pathlib import Path
from typing import Protocol

from app.config import REPO_ROOT, get_settings
from app.errors import NotFound, ServiceUnavailable

DEMO_PREFIX = "data/demo/"


class Storage(Protocol):
    def put(self, key: str, data: bytes) -> str:
        """Store bytes under a relative key; returns the path to keep in `Document.storage_path`."""
        ...

    def get(self, path: str) -> bytes: ...


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


class S3Storage:
    """S3-compatible backend for production (interface stub; wire boto3/Vercel Blob here)."""

    def put(self, key: str, data: bytes) -> str:
        raise ServiceUnavailable("object storage is not configured", "STORAGE_UNAVAILABLE")

    def get(self, path: str) -> bytes:
        raise ServiceUnavailable("object storage is not configured", "STORAGE_UNAVAILABLE")


def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage()
    root = settings.storage_dir
    return LocalStorage(root if root.is_absolute() else REPO_ROOT / root)
