"""Audit signing key handling. The private key never leaves the AUDIT_SIGNING_KEY setting or the
git-ignored dev key file; the matching public key is committed at
docs/submission/audit-public-key.pem."""

import base64
import binascii
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

from app.config import REPO_ROOT, get_settings

PUBLIC_KEY_PATH = REPO_ROOT / "docs" / "submission" / "audit-public-key.pem"


def _parse_seed(value: str) -> bytes:
    value = value.strip()
    try:
        raw = bytes.fromhex(value)
        if len(raw) == 32:
            return raw
    except ValueError:
        pass
    try:
        raw = base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("audit signing key must be 32 bytes as hex or base64") from exc
    if len(raw) != 32:
        raise ValueError("audit signing key must be 32 bytes as hex or base64")
    return raw


def create_dev_key_file(path: Path) -> bool:
    """Write a new dev key at `path` unless one exists. Returns True when it created one."""
    if path.exists():
        return False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(base64.b64encode(os.urandom(32)).decode("ascii") + "\n")
    return True


def load_signing_key(*, create_dev_key: bool = False) -> Ed25519PrivateKey:
    """The configured AUDIT_SIGNING_KEY if set; otherwise the git-ignored dev key file (keys/),
    generated on first use when `create_dev_key` is True (seed time, keygen)."""
    settings = get_settings()
    if settings.audit_signing_key is not None:
        return Ed25519PrivateKey.from_private_bytes(
            _parse_seed(settings.audit_signing_key.get_secret_value())
        )
    path: Path = settings.audit_dev_key_path
    if not path.exists():
        if not create_dev_key:
            raise FileNotFoundError(
                f"no audit signing key: set AUDIT_SIGNING_KEY or run the seed ({path})"
            )
        create_dev_key_file(path)
    if path.stat().st_mode & 0o077:
        raise PermissionError(f"{path} must not be readable by group/others (chmod 600)")
    return Ed25519PrivateKey.from_private_bytes(_parse_seed(path.read_text()))


def raw_public(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def fingerprint(public_key: Ed25519PublicKey) -> str:
    """sha256 of the 32 raw public-key bytes, hex."""
    return hashlib.sha256(raw_public(public_key)).hexdigest()


def key_id(public_key: Ed25519PublicKey) -> str:
    return fingerprint(public_key)[:16]


def public_pem(public_key: Ed25519PublicKey) -> str:
    return public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def load_public_pem(path: Path) -> Ed25519PublicKey:
    key = load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError(f"{path} is not an Ed25519 public key")
    return key


def sign_hash(private_key: Ed25519PrivateKey, digest_hex: str) -> str:
    return private_key.sign(bytes.fromhex(digest_hex)).hex()


def verify_signature(public_key: Ed25519PublicKey, digest_hex: str, signature_hex: str) -> bool:
    try:
        public_key.verify(bytes.fromhex(signature_hex), bytes.fromhex(digest_hex))
    except Exception:
        return False
    return True
