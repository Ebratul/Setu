"""Field-level encryption, masking and blind indexes for onboarding PII.

Sensitive values (full phone, licence/IRC/TIN/USCC numbers, bank account numbers) are stored only
as Fernet ciphertext (`FIELD_ENCRYPTION_KEY`, a comma list of keys, newest first, so a key can be
rotated: MultiFernet decrypts with any and always encrypts with the first). API responses carry the
masked form. `blind_index` is an HMAC used to compare/de-duplicate a value without decrypting it.

Dev fallback: with no key configured a key is derived from the demo session secret and a warning
is logged once. `APP_ENV=prod` refuses to start without a real key (`create_app` checks it).
"""

import base64
import hashlib
import hmac
import json
import re
from functools import lru_cache
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

log = structlog.get_logger("setu.crypto")
_DEV_SEED = b"setu-dev-field-encryption-not-secret"


class DecryptionError(Exception):
    """The ciphertext is damaged or was made with a key that is no longer configured."""


def _dev_key() -> bytes:
    s = get_settings()
    seed = s.demo_session_secret.get_secret_value().encode() if s.demo_session_secret else _DEV_SEED
    return base64.urlsafe_b64encode(hashlib.sha256(b"field-key:" + seed).digest())


@lru_cache
def _fernet_for(configured: str | None, dev_seed: str, app_env: str) -> MultiFernet:
    keys = [k.strip() for k in (configured or "").split(",") if k.strip()]
    if not keys:
        if app_env == "prod":
            raise RuntimeError("FIELD_ENCRYPTION_KEY is required when APP_ENV=prod")
        log.warning("field_encryption_dev_key", detail="FIELD_ENCRYPTION_KEY is not set")
        return MultiFernet([Fernet(_dev_key())])
    return MultiFernet([Fernet(k.encode()) for k in keys])


def fernet() -> MultiFernet:
    s = get_settings()
    key = s.field_encryption_key.get_secret_value() if s.field_encryption_key else None
    seed = s.demo_session_secret.get_secret_value() if s.demo_session_secret else ""
    return _fernet_for(key, seed, s.app_env)


def validate_configuration() -> None:
    """Fail early (startup) on a missing or malformed key."""
    fernet()


def encrypt_text(value: str) -> bytes:
    return fernet().encrypt(value.encode())


def decrypt_text(blob: bytes) -> str:
    try:
        return fernet().decrypt(bytes(blob)).decode()
    except InvalidToken as exc:
        raise DecryptionError("cannot decrypt stored value") from exc


def encrypt_json(value: dict[str, Any]) -> bytes:
    return encrypt_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def decrypt_json(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        return {}
    out = json.loads(decrypt_text(blob))
    return out if isinstance(out, dict) else {}


def _base_secret() -> bytes:
    from app.services import approval_otp

    secret = get_settings().phone_hash_secret
    if secret is not None and secret.get_secret_value():
        return secret.get_secret_value().encode()
    return approval_otp.secret_key()


def _index_key(family: str) -> bytes:
    """A separate 256-bit key per purpose family (phone, dedupe, recovery, ...), HKDF-SHA256 from
    the base secret, so a value hashed for one purpose can never be tested against another.
    P24 stored no blind indexes (it compared plaintext licences), so nothing needs re-keying."""
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"setu-blind-index-v1", info=family.encode()
    ).derive(_base_secret())


def blind_index(purpose: str, value: str) -> str:
    """HMAC-SHA256 (hex, 64 chars) of a normalised value under the key of `purpose`'s family
    (the part before the first ':'), domain-separated by the full `purpose`."""
    family = purpose.split(":", 1)[0]
    return hmac.new(_index_key(family), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def normalise_id(value: str) -> str:
    """Upper-case alphanumerics only: 'tl-001/2024' and 'TL 001 2024' compare equal."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def mask_phone(phone: str) -> str:
    """'+8801712345678' -> '01*******78' style: keep the first two and last two digits."""
    digits = re.sub(r"\D", "", phone)
    local = "0" + digits[-10:] if len(digits) >= 10 else digits
    if len(local) <= 4:
        return "*" * len(local)
    return f"{local[:2]}{'*' * (len(local) - 4)}{local[-2:]}"


def mask_tail(value: str, keep: int = 4) -> str:
    """'123456789012' -> '****9012'."""
    tail = re.sub(r"[^A-Za-z0-9]", "", value)[-keep:]
    return f"****{tail}"
