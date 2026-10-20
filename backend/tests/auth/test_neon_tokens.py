import time

import jwt
import pytest

from app.auth import neon
from app.config import Settings
from tests.auth.support import BASE_URL, FakeNeon


def settings(**kw: object) -> Settings:
    return Settings(auth_mode="neon", neon_auth_base_url=BASE_URL, _env_file=None, **kw)  # type: ignore[call-arg]


def verify(fake: FakeNeon, token: str, cache: neon.JwksCache | None = None) -> neon.NeonIdentity:
    return neon.verify_token(token, settings(), cache or fake.cache())


def test_valid_token_yields_identity() -> None:
    fake = FakeNeon()
    ident = verify(fake, fake.token(sub="abc", email="  Buyer@Example.com "))
    assert ident == neon.NeonIdentity("abc", "buyer@example.com", True, "Test User")


def test_unverified_email_is_reported_not_hidden() -> None:
    fake = FakeNeon()
    assert verify(fake, fake.token(emailVerified=False)).email_verified is False
    assert verify(fake, fake.token(emailVerified=None)).email_verified is False


@pytest.mark.parametrize(
    "over",
    [
        {"exp": int(time.time()) - 3600},
        {"iss": "https://evil.example"},
        {"aud": "https://evil.example"},
        {"banned": True},
        {"sub": None},
        {"email": None},
        {"exp": None},
    ],
)
def test_bad_claims_are_rejected(over: dict[str, object]) -> None:
    fake = FakeNeon()
    with pytest.raises(neon.TokenError):
        verify(fake, fake.token(**over))


def test_token_signed_by_another_key_is_rejected() -> None:
    real, attacker = FakeNeon(), FakeNeon()
    with pytest.raises(neon.TokenError):
        verify(real, attacker.token())


def test_alg_none_and_hmac_confusion_are_rejected() -> None:
    fake = FakeNeon()
    unsigned = jwt.encode({"sub": "u", "email": "a@b.c"}, None, algorithm="none")
    with pytest.raises(neon.TokenError):
        verify(fake, unsigned)
    public = fake.jwks()["keys"][0]["x"]
    forged = jwt.encode({"sub": "u", "email": "a@b.c"}, public * 2, "HS256", {"kid": fake.kid})
    with pytest.raises(neon.TokenError):
        verify(fake, forged)


@pytest.mark.parametrize("token", ["", "x", "a.b.c", "é"])
def test_garbage_never_raises_anything_else(token: str) -> None:
    fake = FakeNeon()
    with pytest.raises(neon.TokenError):
        verify(fake, token)


def test_key_rotation_refetches_once_then_throttles() -> None:
    fake = FakeNeon("old")
    now = [0.0]
    cache = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    s = settings()
    assert neon.verify_token(fake.token(), s, cache).subject == "u-1"
    assert fake.fetches == 1
    fake.rotate("new")
    with pytest.raises(neon.TokenError):  # same moment: unknown kid is not refetched yet
        neon.verify_token(fake.token(), s, cache)
    assert fake.fetches == 1
    now[0] = neon.MIN_REFETCH_SECONDS + 1
    assert neon.verify_token(fake.token(), s, cache).subject == "u-1"
    assert fake.fetches == 2


def test_jwks_is_cached_until_ttl() -> None:
    fake = FakeNeon()
    now = [0.0]
    cache = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    s = settings(neon_auth_jwks_ttl_seconds=60)
    for _ in range(5):
        neon.verify_token(fake.token(), s, cache)
    assert fake.fetches == 1
    now[0] = 61
    neon.verify_token(fake.token(), s, cache)
    assert fake.fetches == 2


def test_outage_keeps_last_good_keys_but_cold_start_fails_closed() -> None:
    fake = FakeNeon()
    now = [0.0]
    cache = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    s = settings(neon_auth_jwks_ttl_seconds=60)
    neon.verify_token(fake.token(), s, cache)
    fake.fail = True
    now[0] = 120
    assert neon.verify_token(fake.token(), s, cache).subject == "u-1"  # stale keys still verify

    cold = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    with pytest.raises(neon.AuthUnavailable):
        neon.verify_token(fake.token(), s, cold)


def test_missing_base_url_is_unavailable_not_valid() -> None:
    fake = FakeNeon()
    unset = Settings(auth_mode="neon", _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(neon.AuthUnavailable):
        neon.verify_token(fake.token(), unset, fake.cache())


def test_unknown_kid_flood_during_outage_is_throttled() -> None:
    fake = FakeNeon()
    now = [0.0]
    cache = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    s = settings(neon_auth_jwks_ttl_seconds=60)
    neon.verify_token(fake.token(), s, cache)
    fake.fail = True
    now[0] = 100.0
    other = FakeNeon("other")
    before = fake.fetches
    for _ in range(20):
        with pytest.raises(neon.TokenError):
            neon.verify_token(other.token(), s, cache)
    assert fake.fetches - before == 1  # one attempt per window, even though every one failed


def test_cold_start_outage_is_throttled_too() -> None:
    fake = FakeNeon()
    fake.fail = True
    now = [0.0]
    cache = neon.JwksCache(fetch=fake.fetch, clock=lambda: now[0])
    s = settings()
    for _ in range(10):
        with pytest.raises(neon.AuthUnavailable):
            neon.verify_token(fake.token(), s, cache)
    assert fake.fetches == 1
    now[0] = neon.COLD_RETRY_SECONDS + 1
    fake.fail = False
    assert neon.verify_token(fake.token(), s, cache).subject == "u-1"


def test_concurrent_requests_do_not_fetch_in_parallel() -> None:
    import threading

    fake = FakeNeon()
    inside = threading.Event()
    release = threading.Event()

    def slow(url: str) -> dict[str, object]:
        inside.set()
        release.wait(5)
        return fake.fetch(url)

    cache = neon.JwksCache(fetch=slow)
    s = settings()
    results: list[str] = []
    first = threading.Thread(
        target=lambda: results.append(neon.verify_token(fake.token(), s, cache).subject)
    )
    first.start()
    assert inside.wait(5)
    second = threading.Thread(  # a cold cache makes it wait for the one fetch, not fetch again
        target=lambda: results.append(neon.verify_token(fake.token(), s, cache).subject)
    )
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert results == ["u-1", "u-1"] and fake.fetches == 1
