"""Scheme and verifier, no database: tampering reports the exact seq and reason."""

import copy
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.audit.export import line_of_dict
from app.audit.scheme import (
    GENESIS_HASH,
    canonical_json,
    compute_entry_hash,
    compute_payload_hash,
    fmt_ts,
)
from app.audit.tamper import TamperError, apply_tamper
from app.audit.verify import (
    BAD_SIGNATURE,
    BROKEN_LINK,
    HASH_MISMATCH,
    MALFORMED,
    MISSING_SEQ,
    REORDERED,
    verify_lines,
)
from app.audit.writer import PendingEntry, build_chain

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
OTHER = Ed25519PrivateKey.from_private_bytes(bytes(32))
T0 = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
DEAL = uuid.UUID("5c0b8a52-0d3e-5f64-9c7f-3d2a4b1e6f10")


def make(n: int = 100) -> list[dict[str, Any]]:
    entries = [
        PendingEntry(
            ts=T0 + timedelta(seconds=i),
            actor_type="user" if i % 3 == 0 else "system",
            actor_id=f"actor-{i % 5}",
            deal_id=DEAL if i % 2 else None,
            action="TRANCHE_RELEASED" if i % 7 == 0 else "KYB_CHECKED",
            tier=i % 4,
            decision="OK",
            payload={"amount": str(Decimal("5760.00") + i), "n": i, "name": "বাংলা ✓"},
        )
        for i in range(n)
    ]
    return [line_of_dict(r) for r in build_chain(KEY, entries)]


def test_a_chain_of_100_entries_verifies_and_is_anchored() -> None:
    lines = make(100)
    report = verify_lines(lines, KEY.public_key())
    assert report.ok and report.entries_checked == 100 and report.anchored
    assert lines[0]["prev_hash"] == GENESIS_HASH and lines[1]["prev_hash"] == lines[0]["entry_hash"]


def test_changing_one_payload_character_reports_that_seq() -> None:
    lines = make()
    lines[41]["payload"]["amount"] = "5761.00"
    report = verify_lines(lines, KEY.public_key())
    assert (report.ok, report.broken_seq, report.reason) == (False, 42, HASH_MISMATCH)


@pytest.mark.parametrize("field", ["tier", "action", "decision", "actor_id", "ts", "deal_id"])
def test_every_signed_field_is_covered(field: str) -> None:
    lines = make(10)
    lines[4][field] = 3 if field == "tier" else "x"
    report = verify_lines(lines, KEY.public_key())
    assert not report.ok and report.broken_seq == 5


def test_a_forged_entry_with_recomputed_hashes_fails_on_the_signature() -> None:
    lines = make(10)
    e = lines[4]
    e["payload"]["amount"] = "57600.00"
    e["payload_hash"] = compute_payload_hash({k: e[k] for k in list(e)[:9]})
    e["entry_hash"] = compute_entry_hash(e["prev_hash"], e["payload_hash"], e["seq"], e["ts"])
    report = verify_lines(lines, KEY.public_key())
    assert (report.broken_seq, report.reason) == (5, BAD_SIGNATURE)


def test_deleting_an_entry_reports_the_missing_seq() -> None:
    lines = make()
    del lines[30]
    report = verify_lines(lines, KEY.public_key())
    assert (report.broken_seq, report.reason) == (31, MISSING_SEQ)


def test_swapping_two_entries_reports_reordered() -> None:
    lines = make()
    lines[10], lines[11] = lines[11], lines[10]
    report = verify_lines(lines, KEY.public_key())
    assert (report.broken_seq, report.reason) == (11, REORDERED)


def test_the_wrong_public_key_fails_the_signature_on_the_first_entry() -> None:
    report = verify_lines(make(5), OTHER.public_key())
    assert (report.broken_seq, report.reason) == (1, BAD_SIGNATURE)


def test_a_rewritten_prev_hash_breaks_the_link() -> None:
    lines = make(10)
    # re-sign entry 6 over a different prev_hash: its own hashes and signature are then valid
    forged = build_chain(
        KEY,
        [PendingEntry(T0, "system", "system", None, "X", 0, "OK", {})],
        start_seq=6,
        prev_hash="f" * 64,
    )
    lines[5] = line_of_dict(forged[0])
    report = verify_lines(lines, KEY.public_key())
    assert (report.broken_seq, report.reason) == (6, BROKEN_LINK)


def test_seq_one_must_link_to_genesis() -> None:
    forged = build_chain(
        KEY, [PendingEntry(T0, "system", "system", None, "X", 0, "OK", {})], prev_hash="a" * 64
    )
    report = verify_lines([line_of_dict(forged[0])], KEY.public_key())
    assert (report.broken_seq, report.reason) == (1, BROKEN_LINK)


def test_a_range_is_checked_against_a_trusted_anchor() -> None:
    lines = make(20)
    window = lines[9:15]
    ok = verify_lines(window, KEY.public_key(), anchor_prev_hash=lines[8]["entry_hash"])
    assert ok.ok and not ok.anchored
    bad = verify_lines(window, KEY.public_key(), anchor_prev_hash="b" * 64)
    assert (bad.broken_seq, bad.reason) == (10, BROKEN_LINK)


def test_a_filtered_export_verifies_per_entry_and_checks_neighbours() -> None:
    lines = make(30)
    subset = [ln for ln in lines if ln["deal_id"]]
    assert verify_lines(subset, KEY.public_key(), contiguous=False).ok
    subset[3]["payload"]["n"] = -1
    report = verify_lines(subset, KEY.public_key(), contiguous=False)
    assert report.broken_seq == subset[3]["seq"] and report.reason == HASH_MISMATCH


def test_malformed_lines_are_reported_not_raised() -> None:
    lines = make(3)
    del lines[1]["signature"]
    assert verify_lines(lines, KEY.public_key()).reason == MALFORMED
    lines = make(3)
    lines[1]["entry_hash"] = "xyz"
    assert verify_lines(lines, KEY.public_key()).reason == MALFORMED


def test_canonical_json_is_sorted_compact_utf8_and_decimal_safe() -> None:
    text = canonical_json({"b": [1, {"z": Decimal("1.50"), "a": "বাংলা"}], "a": None})
    assert text == '{"a":null,"b":[1,{"a":"বাংলা","z":"1.50"}]}'


def test_floats_are_refused_in_payloads() -> None:
    with pytest.raises(TypeError):
        canonical_json({"score": 0.1})
    with pytest.raises(TypeError):
        canonical_json({"nested": [{"x": 1.5}]})


def test_timestamps_are_fixed_width_utc_and_timezone_independent() -> None:
    dhaka = datetime(2026, 10, 20, 15, 0, 0, 123, tzinfo=UTC).astimezone(timezone_of(6))
    assert fmt_ts(dhaka) == "2026-10-20T15:00:00.000123Z"
    with pytest.raises(ValueError):
        fmt_ts(datetime(2026, 10, 20, 15, 0))


def timezone_of(hours: int):  # type: ignore[no-untyped-def]
    from datetime import timezone

    return timezone(timedelta(hours=hours))


def test_a_known_vector_pins_the_scheme_for_other_implementations() -> None:
    """If this changes, frontend/src/lib/audit/verify.ts must change with it."""
    body = {
        "seq": 1,
        "ts": "2026-10-19T09:00:00.000000Z",
        "actor_type": "user",
        "actor_id": "demo-buyer",
        "deal_id": None,
        "action": "DEAL_CREATED",
        "tier": 0,
        "decision": "OK",
        "payload": {"deal_ref": "SETU-2026-0001"},
    }
    p = compute_payload_hash(body)
    e = compute_entry_hash(GENESIS_HASH, p, 1, body["ts"])
    assert len(p) == len(e) == 64
    assert compute_payload_hash(copy.deepcopy(body)) == p
    # the second hash binds prev_hash, payload_hash, seq and ts with '|' separators
    assert (
        e == __import__("hashlib").sha256(f"{GENESIS_HASH}|{p}|1|{body['ts']}".encode()).hexdigest()
    )


def test_tamper_helpers_work_on_a_copy_and_reject_bad_input() -> None:
    lines = make(10)
    before = copy.deepcopy(lines)
    out = apply_tamper(lines, mode="edit", seq=5, field="amount", value="1")
    assert lines == before and out[4]["payload"]["amount"] == "1"
    assert [ln["seq"] for ln in apply_tamper(lines, mode="delete", seq=5)] == [
        1, 2, 3, 4, 6, 7, 8, 9, 10,
    ]  # fmt: skip
    assert [ln["seq"] for ln in apply_tamper(lines, mode="reorder", seq=5)][3:7] == [4, 6, 5, 7]
    with pytest.raises(TamperError):
        apply_tamper(lines, mode="edit", seq=5, field="tier", value="high")
    with pytest.raises(TamperError):
        apply_tamper(lines, mode="delete", seq=99)
    with pytest.raises(TamperError):
        apply_tamper(lines, mode="edit", seq=5)
