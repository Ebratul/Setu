"""PII masking of audit payloads: identifiers are redacted one-way, amounts and digests survive."""

import hashlib
import uuid

import pytest

from app.audit.export import line_of
from app.audit.mask import clean_payload
from app.audit.writer import write_audit
from app.db.models import AuditLog
from app.db.session import batch_session
from tests.audit.support import has_float, pii_hits

pytestmark = pytest.mark.db

SHA = hashlib.sha256(b"invoice").hexdigest()
UUID = str(uuid.uuid4())

IDENTIFIERS = {
    "phone_text": ("call +8801712345678 today", "PHONE"),
    "nid": ("1234567890", "NID"),
    "bank_account": ("0012345678901", "ACCT"),
    "email": ("a.b@example.com", "EMAIL"),
    "iban": ("GB82WEST12345698765432", "IBAN"),
    "holder_name": ("Rahima Begum", "NAME"),
}


def stored(params: dict) -> dict:
    with batch_session() as s:
        seq = write_audit(s, actor="system", action="TEST_MASK", tier=0, params=params, result="OK")
        s.flush()
        return line_of(s.get(AuditLog, seq))["payload"]  # type: ignore[arg-type]


@pytest.mark.parametrize("key", list(IDENTIFIERS))
def test_identifier_is_redacted_in_the_stored_payload(migrated_db: str, key: str) -> None:
    raw, kind = IDENTIFIERS[key]
    payload = stored({key: raw})
    assert f"[redacted:{kind}]" in payload[key]
    assert raw.split()[-2] not in payload[key] if " " in raw else raw not in payload[key]


def test_a_plain_usd_amount_is_kept(migrated_db: str) -> None:
    payload = stored({"amount": "5760.00", "note": "USD 5,760.00 released", "currency": "USD"})
    assert payload == {"amount": "5760.00", "note": "USD 5,760.00 released", "currency": "USD"}


def test_uuids_and_sha256_hex_pass_through_untouched(migrated_db: str) -> None:
    payload = stored(
        {"deal_id": UUID, "document_sha256": SHA, "bank_account": UUID, "holder_name": SHA}
    )
    assert payload == {
        "deal_id": UUID,
        "document_sha256": SHA,
        "bank_account": UUID,
        "holder_name": SHA,
    }


def test_floats_are_stored_as_decimal_strings_never_as_floats(migrated_db: str) -> None:
    payload = stored({"rate": 7.1234, "nested": {"xs": [0.1, 2.5]}, "n": 3})
    assert payload == {"rate": "7.1234", "nested": {"xs": ["0.1", "2.5"]}, "n": 3}
    assert not has_float(payload)


def test_stored_payload_has_no_detectable_identifier_left(migrated_db: str) -> None:
    params = {k: v[0] for k, v in IDENTIFIERS.items()} | {"free": "mail a.b@example.com now"}
    payload = stored(params)
    assert pii_hits([{"seq": 1, "payload": payload}]) == []


def test_free_text_is_truncated_at_a_thousand_characters() -> None:
    out = clean_payload({"note": "x" * 5000})
    assert len(out["note"]) == 1001 and out["note"].endswith("…")


def test_non_dict_values_nest_safely_and_deep_structures_are_truncated() -> None:
    deep: dict = {}
    cur = deep
    for _ in range(12):
        cur["a"] = {}
        cur = cur["a"]
    flat = str(clean_payload(deep))
    assert "[truncated]" in flat
