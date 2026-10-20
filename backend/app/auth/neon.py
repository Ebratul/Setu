"""Neon Auth (Managed Better Auth) JWT verification. The only module that trusts Neon's tokens.

Neon signs 15-minute access tokens with EdDSA (Ed25519). We verify signature, issuer, audience,
expiry and `sub` against the public JWKS (cached; refetched once when a `kid` is unknown, which
covers key rotation). Nothing here touches the database: callers map `sub` to a local user.
"""

import base64
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.config import Settings, get_settings

log = logging.getLogger(__name__)

LEEWAY_SECONDS = 10
MIN_REFETCH_SECONDS = 15.0
COLD_RETRY_SECONDS = 5.0
FETCH_TIMEOUT_SECONDS = 5.0

JwksFetcher = Callable[[str], dict[str, Any]]


class TokenError(Exception):
    """The bearer token is missing, malformed, expired, forged or from another issuer."""


class AuthUnavailable(Exception):
    """Neon Auth is misconfigured or its JWKS cannot be fetched (not the caller's fault)."""


@dataclass(frozen=True, slots=True)
class NeonIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str


def _http_fetch(url: str) -> dict[str, Any]:
    res = httpx.get(url, timeout=FETCH_TIMEOUT_SECONDS)
    res.raise_for_status()
    body = res.json()
    if not isinstance(body, dict):
        raise ValueError("JWKS is not an object")
    return body


class JwksCache:
    """Keys by `kid`. Network I/O never runs under the state lock, only one thread fetches at a
    time (others use the current keys), and every attempt, successful or not, is throttled, so a
    flood of unknown `kid`s or an outage cannot turn into a flood of 5 s fetches."""

    def __init__(
        self,
        fetch: JwksFetcher = _http_fetch,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._state = threading.Lock()
        self._fetching = threading.Lock()
        self._keys: dict[str, Ed25519PublicKey] = {}
        self._fetched_at: float | None = None
        self._attempted_at: float | None = None

    def clear(self) -> None:
        with self._state:
            self._keys, self._fetched_at, self._attempted_at = {}, None, None

    def _due(self, kid: str, ttl: float) -> bool:
        now = self._clock()
        since_attempt = None if self._attempted_at is None else now - self._attempted_at
        if not self._keys:
            return since_attempt is None or since_attempt >= COLD_RETRY_SECONDS
        if since_attempt is not None and since_attempt < MIN_REFETCH_SECONDS:
            return False
        assert self._fetched_at is not None
        return kid not in self._keys or now - self._fetched_at > ttl

    def _due_locked(self, kid: str, settings: Settings) -> bool:
        with self._state:
            return self._due(kid, settings.neon_auth_jwks_ttl_seconds)

    def key_for(self, kid: str, settings: Settings) -> Ed25519PublicKey:
        url = settings.neon_auth_jwks_url
        if url is None:
            raise AuthUnavailable("NEON_AUTH_BASE_URL is not set")
        with self._state:
            cold = not self._keys
            due = self._due(kid, settings.neon_auth_jwks_ttl_seconds)
        # A cold cache has no keys to fall back on, so callers wait (bounded) for the one fetch.
        if cold:
            got = self._fetching.acquire(timeout=FETCH_TIMEOUT_SECONDS + 1.0)
        else:
            got = due and self._fetching.acquire(blocking=False)
        if got:
            try:
                if self._due_locked(kid, settings):
                    self._refresh(url)
            finally:
                self._fetching.release()
        with self._state:
            key = self._keys.get(kid)
            have_keys = bool(self._keys)
        if key is None:
            if not have_keys:
                raise AuthUnavailable("the Neon Auth signing keys are not available")
            raise TokenError("unknown signing key")
        return key

    def _refresh(self, url: str) -> None:
        with self._state:
            self._attempted_at = self._clock()
        try:
            doc = self._fetch(url)
            keys: dict[str, Ed25519PublicKey] = {}
            for jwk in doc.get("keys", []):
                if jwk.get("kty") == "OKP" and jwk.get("crv") == "Ed25519" and jwk.get("kid"):
                    raw = base64.urlsafe_b64decode(jwk["x"] + "=" * (-len(jwk["x"]) % 4))
                    keys[jwk["kid"]] = Ed25519PublicKey.from_public_bytes(raw)
        except Exception as exc:
            log.warning("neon auth: JWKS fetch failed: %s", type(exc).__name__)
            return  # keep the last good keys; the next attempt is throttled
        if keys:
            with self._state:
                self._keys, self._fetched_at = keys, self._clock()


_cache = JwksCache()


def reset_cache() -> None:
    _cache.clear()


def verify_token(
    token: str, settings: Settings | None = None, cache: JwksCache | None = None
) -> NeonIdentity:
    settings = settings or get_settings()
    origin = settings.neon_auth_origin
    if origin is None:
        raise AuthUnavailable("NEON_AUTH_BASE_URL is not set")
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "EdDSA" or not isinstance(kid, str):
            raise TokenError("unsupported token header")
        key = (cache or _cache).key_for(kid, settings)
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["EdDSA"],
            issuer=origin,
            audience=origin,
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(type(exc).__name__) from exc
    if claims.get("banned") is True:
        raise TokenError("banned")
    subject, email = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise TokenError("missing identity claims")
    return NeonIdentity(
        subject=subject,
        email=email.strip().lower(),
        email_verified=claims.get("emailVerified") is True,
        name=str(claims.get("name") or ""),
    )
