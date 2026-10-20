"""Short-lived signed download tokens. `GET /documents/{id}` does the role check and hands out
`/documents/{id}/file?token=...`; the file endpoint verifies the HMAC, the expiry and that the
signed-in user is the one the token was issued to."""

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass

from app.config import get_settings

DEV_SECRET = b"setu-dev-document-url-not-secret"


@dataclass(frozen=True, slots=True)
class FileToken:
    document_id: uuid.UUID
    user_id: uuid.UUID
    expires_at: int


def _secret() -> bytes:
    s = get_settings()
    for candidate in (s.document_url_secret, s.demo_session_secret):
        if candidate is not None and candidate.get_secret_value():
            return hashlib.sha256(b"doc-url:" + candidate.get_secret_value().encode()).digest()
    return DEV_SECRET


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sig(payload: str) -> str:
    return _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())


def make_token(document_id: uuid.UUID, user_id: uuid.UUID, *, now: int | None = None) -> FileToken:
    ttl = get_settings().document_url_ttl_seconds
    return FileToken(document_id, user_id, (now if now is not None else int(time.time())) + ttl)


def encode(token: FileToken) -> str:
    payload = f"{token.document_id}.{token.user_id}.{token.expires_at}"
    return f"{_b64(payload.encode())}.{_sig(payload)}"


def decode(raw: str, *, now: int | None = None) -> FileToken | None:
    """The token if the signature and expiry hold, else None."""
    try:
        body, sig = raw.split(".")
        padded = body + "=" * (-len(body) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        if not hmac.compare_digest(sig, _sig(payload)):
            return None
        doc, user, exp = payload.split(".")
        token = FileToken(uuid.UUID(doc), uuid.UUID(user), int(exp))
    except (ValueError, TypeError, UnicodeError):
        return None
    return token if token.expires_at >= (now if now is not None else int(time.time())) else None


def signed_path(document_id: uuid.UUID, user_id: uuid.UUID) -> tuple[str, int]:
    token = make_token(document_id, user_id)
    return f"/documents/{document_id}/file?token={encode(token)}", token.expires_at
