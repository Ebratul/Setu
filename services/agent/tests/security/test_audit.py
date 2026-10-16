import base64
import dataclasses
from datetime import UTC, datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.security.audit import (
    GENESIS_HASH,
    SignedEntry,
    _parse_seed,
    build_chain,
    compute_entry_hash,
    params_hash,
    verify_chain,
)

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
DHAKA = timezone(timedelta(hours=6))


def _chain() -> list[SignedEntry]:
    t0 = datetime(2026, 10, 20, 10, 0, tzinfo=DHAKA)
    return build_chain(
        KEY,
        [
            (t0, "user", "DEAL_CREATED", 0, params_hash({"deal_ref": "X"}), "OK"),
            (
                t0 + timedelta(minutes=1),
                "system",
                "MILESTONE_RELEASED",
                1,
                params_hash({"m": 1}),
                "OK",
            ),
            (t0 + timedelta(minutes=2), "user", "APPROVAL_GRANTED", 2, params_hash({"m": 2}), "OK"),
        ],
    )


def test_chain_links_and_verifies() -> None:
    chain = _chain()
    assert chain[0].fields.prev_hash == GENESIS_HASH
    assert chain[1].fields.prev_hash == chain[0].entry_hash
    assert verify_chain(KEY.public_key(), chain) == []


def test_tampered_field_is_detected() -> None:
    chain = _chain()
    bad = dataclasses.replace(chain[1], fields=dataclasses.replace(chain[1].fields, tier=0))
    problems = verify_chain(KEY.public_key(), [chain[0], bad, chain[2]])
    assert any("seq 2: entry_hash mismatch" in p for p in problems)


def test_removed_entry_breaks_the_link() -> None:
    chain = _chain()
    problems = verify_chain(KEY.public_key(), [chain[0], chain[2]])
    assert any("prev_hash does not link" in p for p in problems)


def test_wrong_key_signature_is_rejected() -> None:
    other = Ed25519PrivateKey.from_private_bytes(bytes(32))
    problems = verify_chain(other.public_key(), _chain())
    assert all("bad signature" in p for p in problems) and len(problems) == 3


def test_hash_is_independent_of_timezone_representation() -> None:
    entry = _chain()[0]
    as_utc = dataclasses.replace(entry.fields, ts=entry.fields.ts.astimezone(UTC))
    assert compute_entry_hash(as_utc) == entry.entry_hash


def test_seed_parsing_accepts_hex_and_base64_only_32_bytes() -> None:
    raw = bytes(range(32))
    assert _parse_seed(raw.hex()) == raw
    assert _parse_seed(base64.b64encode(raw).decode()) == raw
    with pytest.raises(ValueError):
        _parse_seed(base64.b64encode(b"short").decode())


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_chain(KEY, [(datetime(2026, 10, 20, 10, 0), "user", "X", 0, "0" * 64, "OK")])


def test_tail_gap_in_seq_is_detected() -> None:
    chain = _chain()
    shifted = dataclasses.replace(chain[2], fields=dataclasses.replace(chain[2].fields, seq=7))
    problems = verify_chain(KEY.public_key(), [chain[0], chain[1], shifted])
    assert any("gap or reorder" in p for p in problems)
