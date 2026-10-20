"""A cold JWKS cache must not 503 the requests that lose the fetch race."""

import threading
import time
from typing import Any

from app.auth import neon
from app.config import get_settings

N = 5


def test_concurrent_cold_requests_share_one_fetch(monkeypatch: Any) -> None:
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": "k1",
        "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
    }
    calls: list[str] = []

    def slow_fetch(url: str) -> dict[str, Any]:
        calls.append(url)
        time.sleep(0.3)
        return {"keys": [jwk]}

    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    get_settings.cache_clear()
    cache = neon.JwksCache(fetch=slow_fetch)
    results: list[object] = []

    def call() -> None:
        try:
            results.append(cache.key_for("k1", get_settings()))
        except Exception as exc:
            results.append(exc)

    threads = [threading.Thread(target=call) for _ in range(N)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    get_settings.cache_clear()
    assert len(calls) == 1
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len(results) == N
