"""RFC 6238 TOTP and recovery codes (stdlib implementation). No database."""

import re

from app.security import totp

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII "12345678901234567890", RFC 6238 appendix B


def test_rfc_6238_vectors_sha1_six_digits() -> None:
    for at, expected in (
        (59, "287082"),
        (1111111109, "081804"),
        (1234567890, "005924"),
        (2000000000, "279037"),
    ):
        assert totp.code_at(RFC_SECRET, at // 30) == expected


def test_window_is_one_step_either_side() -> None:
    now = 1_700_000_000
    step = totp.current_step(now)
    for s, ok in (
        (step - 2, False),
        (step - 1, True),
        (step, True),
        (step + 1, True),
        (step + 2, False),
    ):
        assert (totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, s), now=now) == s) is ok


def test_a_step_is_never_accepted_twice_nor_an_older_one() -> None:
    now = 1_700_000_000
    step = totp.current_step(now)
    code = totp.code_at(RFC_SECRET, step)
    assert totp.verify(RFC_SECRET, code, now=now) == step
    assert totp.verify(RFC_SECRET, code, last_step=step, now=now) is None  # replay
    older = totp.code_at(RFC_SECRET, step - 1)
    assert totp.verify(RFC_SECRET, older, last_step=step, now=now) is None
    newer = totp.code_at(RFC_SECRET, step + 1)
    assert totp.verify(RFC_SECRET, newer, last_step=step, now=now) == step + 1


def test_malformed_codes_are_rejected() -> None:
    for bad in ("", "12345", "1234567", "abcdef", "12 456", "٠١٢٣٤٥"):
        assert totp.verify(RFC_SECRET, bad, now=59) is None


def test_secret_and_uri() -> None:
    secret = totp.new_secret()
    assert re.fullmatch(r"[A-Z2-7]{32}", secret) and secret != totp.new_secret()
    uri = totp.otpauth_uri(secret, "ana@example.com")
    assert uri.startswith("otpauth://totp/Setu%3Aana%40example.com?secret=" + secret)
    assert "issuer=Setu" in uri and "digits=6" in uri and "period=30" in uri


def test_ten_distinct_recovery_codes() -> None:
    codes = totp.new_recovery_codes()
    assert len(codes) == 10 and len(set(codes)) == 10
    assert all(re.fullmatch(r"[A-HJ-NP-Z2-9]{5}-[A-HJ-NP-Z2-9]{5}", c) for c in codes)
    assert totp.normalise_recovery("abcde-fghjk") == "ABCDEFGHJK"
