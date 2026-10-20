"""Field encryption, masking and blind indexes. No database."""

import pytest
from cryptography.fernet import Fernet

from app.config import get_settings
from app.security import crypto


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> str:
    k = Fernet.generate_key().decode()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", k)
    get_settings.cache_clear()
    yield k
    get_settings.cache_clear()


def test_round_trip_and_ciphertext_hides_the_value(key: str) -> None:
    blob = crypto.encrypt_text("TL-0042/2024")
    assert b"0042" not in blob and crypto.decrypt_text(blob) == "TL-0042/2024"
    assert crypto.encrypt_text("TL-0042/2024") != blob  # fresh IV every time
    data = {"mobile": "+8801712345678", "n": 3}
    assert crypto.decrypt_json(crypto.encrypt_json(data)) == data
    assert crypto.decrypt_json(None) == {}


def test_key_rotation_decrypts_old_values_and_encrypts_with_the_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", old)
    get_settings.cache_clear()
    blob = crypto.encrypt_text("secret")
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", f"{new},{old}")
    get_settings.cache_clear()
    assert crypto.decrypt_text(blob) == "secret"
    fresh = crypto.encrypt_text("secret")
    assert Fernet(new.encode()).decrypt(fresh) == b"secret"
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", new)
    get_settings.cache_clear()
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_text(blob)
    get_settings.cache_clear()


def test_prod_refuses_to_run_without_a_key_and_dev_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "dev")
    get_settings.cache_clear()
    assert crypto.decrypt_text(crypto.encrypt_text("x")) == "x"  # dev key, with a warning
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
        crypto.encrypt_text("x")
    with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
        crypto.validate_configuration()
    get_settings.cache_clear()


def test_masks() -> None:
    assert crypto.mask_phone("+8801712345678") == "01*******78"
    assert crypto.mask_phone("01712345678") == "01*******78"
    assert crypto.mask_phone("12") == "**"
    assert crypto.mask_tail("123456789012") == "****9012"
    assert crypto.mask_tail("TL-0042/2024") == "****2024"
    assert crypto.mask_tail("12") == "****12"


def test_blind_index_is_deterministic_separated_and_not_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHONE_HASH_SECRET", "p" * 32)
    get_settings.cache_clear()
    a = crypto.blind_index("dedupe:BUYER", "TL0042")
    assert a == crypto.blind_index("dedupe:BUYER", "TL0042") and len(a) == 64
    assert a != crypto.blind_index("dedupe:SUPPLIER", "TL0042")
    assert a != crypto.blind_index("dedupe:BUYER", "TL0043") and "TL0042" not in a
    monkeypatch.setenv("PHONE_HASH_SECRET", "q" * 32)
    get_settings.cache_clear()
    assert a != crypto.blind_index("dedupe:BUYER", "TL0042")  # another secret, another index
    get_settings.cache_clear()


def test_normalise_id_makes_formatting_irrelevant() -> None:
    assert (
        crypto.normalise_id("tl-0042/2024") == crypto.normalise_id("TL 0042 2024") == "TL00422024"
    )
