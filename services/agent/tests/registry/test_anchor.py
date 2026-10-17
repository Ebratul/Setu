import hashlib

from app.services.registry_anchor import merkle_root


def h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


def test_merkle_root_is_order_independent_and_changes_with_content() -> None:
    a, b, c = h("a"), h("b"), h("c")
    assert merkle_root([]) is None
    assert merkle_root([a]) == bytes.fromhex(a).hex()
    assert merkle_root([a, b, c]) == merkle_root([c, a, b])
    assert merkle_root([a, b, c]) != merkle_root([a, b, h("d")])
    pair = hashlib.sha256(*[b"".join(sorted([bytes.fromhex(a), bytes.fromhex(b)]))]).hexdigest()
    assert merkle_root([a, b]) == pair
