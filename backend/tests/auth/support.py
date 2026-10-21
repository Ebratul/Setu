"""A fake Neon Auth: an Ed25519 key pair, a JWKS document and a token minter."""

import base64
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from app.auth.neon import JwksCache

BASE_URL = "https://ep-test.neonauth.example/neondb/auth"
ORIGIN = "https://ep-test.neonauth.example"


class FakeNeon:
    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self.key = Ed25519PrivateKey.generate()
        self.fetches = 0
        self.fail = False

    def jwks(self) -> dict[str, Any]:
        raw = self.key.public_key().public_bytes_raw()
        x = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        return {"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": self.kid, "x": x}]}

    def fetch(self, _url: str) -> dict[str, Any]:
        self.fetches += 1
        if self.fail:
            raise ConnectionError("down")
        return self.jwks()

    def cache(self) -> JwksCache:
        return JwksCache(fetch=self.fetch)

    def rotate(self, kid: str) -> None:
        self.kid, self.key = kid, Ed25519PrivateKey.generate()

    def token(self, *, sub: str = "u-1", email: str = "buyer@example.com", **over: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": sub,
            "id": sub,
            "email": email,
            "emailVerified": True,
            "name": "Test User",
            "role": "authenticated",
            "banned": False,
            "iat": now,
            "exp": now + 900,
            "iss": ORIGIN,
            "aud": ORIGIN,
        }
        claims.update(over)
        for k in [k for k, v in claims.items() if v is None]:
            del claims[k]
        pem = self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        return jwt.encode(claims, pem, algorithm="EdDSA", headers={"kid": self.kid})
