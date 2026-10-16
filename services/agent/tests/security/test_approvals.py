import uuid

from app.security.approvals import approval_binding_hash

BASE = {
    "action": "RELEASE_MILESTONE",
    "tier": 2,
    "deal_id": uuid.UUID(int=1),
    "milestone_id": uuid.UUID(int=2),
    "bank_account_id": uuid.UUID(int=3),
    "params": {"amount": "2880.00", "currency": "USD"},
}


def test_binding_hash_is_stable() -> None:
    assert approval_binding_hash(**BASE) == approval_binding_hash(**dict(BASE))


def test_any_bound_field_change_breaks_the_hash() -> None:
    original = approval_binding_hash(**BASE)
    for field, value in {
        "action": "CHANGE_BENEFICIARY",
        "tier": 3,
        "deal_id": uuid.UUID(int=9),
        "milestone_id": None,
        "bank_account_id": uuid.UUID(int=4),
        "params": {"amount": "2880.01", "currency": "USD"},
    }.items():
        assert approval_binding_hash(**{**BASE, field: value}) != original, field
