"""Demo-only "login as" session token. Isolated so real auth can replace it (see app/auth/deps.py).

The cookie value is `<user_id>.<issued_at>.<hmac>` with HMAC-SHA256 over `<user_id>.<issued_at>`
using DEMO_SESSION_SECRET (a fixed dev secret when unset; `create_app` refuses to start in prod
without one). Anyone can pick any demo user on the login screen, so the signature only stops
hand-edited cookies, not impersonation of demo users. Logout is client-side only.
"""

import hashlib
import hmac
import time
import uuid

from app.config import get_settings

COOKIE_NAME = "setu_demo_session"
MAX_AGE_SECONDS = 12 * 60 * 60
DEV_SECRET = b"setu-dev-demo-session-not-secret"


def _secret() -> bytes:
    secret = get_settings().demo_session_secret
    return secret.get_secret_value().encode() if secret else DEV_SECRET


def _sign(payload: str) -> bytes:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest().encode()


def make_token(user_id: uuid.UUID, now: int | None = None) -> str:
    payload = f"{user_id}.{now if now is not None else int(time.time())}"
    return f"{payload}.{_sign(payload).decode()}"


def parse_token(token: str, now: int | None = None) -> uuid.UUID | None:
    try:
        uid, issued, sig = token.split(".")
        payload = f"{uid}.{issued}"
        if not hmac.compare_digest(sig.encode(), _sign(payload)):
            return None
        age = (now if now is not None else int(time.time())) - int(issued)
        if not 0 <= age <= MAX_AGE_SECONDS:
            return None
        return uuid.UUID(uid)
    except (ValueError, TypeError, UnicodeError):
        return None
