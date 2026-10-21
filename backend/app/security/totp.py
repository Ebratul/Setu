"""RFC 6238 TOTP (SHA-1, 6 digits, 30 s) with the standard library only.

`verify` accepts the current step and one step either side (clock skew) and refuses any step at or
before `last_step`, so a code that was already used - or an older one - is never accepted again.
Recovery codes are random, shown once, and stored as HMAC hashes; each works once.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
WINDOW = 1
RECOVERY_COUNT = 10
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 10**DIGITS:0{DIGITS}d}"


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD)


def verify(
    secret: str, code: str, *, last_step: int | None = None, now: float | None = None
) -> int | None:
    """The matching step number (store it as the new `last_step`), or None."""
    if len(code) != DIGITS or not (code.isascii() and code.isdigit()):
        return None
    centre = current_step(now)
    found: int | None = None
    for step in range(centre - WINDOW, centre + WINDOW + 1):  # no early exit: constant work
        if hmac.compare_digest(code_at(secret, step), code) and found is None:
            found = step
    if found is None or (last_step is not None and found <= last_step):
        return None
    return found


def otpauth_uri(secret: str, account: str, issuer: str = "Setu") -> str:
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}"
    )


def new_recovery_codes() -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(RECOVERY_COUNT)]


def normalise_recovery(code: str) -> str:
    return "".join(c for c in code.upper() if c.isalnum())
