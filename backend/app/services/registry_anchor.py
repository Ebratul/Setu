"""Optional on-chain anchoring seam (not enabled). A daily Merkle root over the registry entries
registered that day could be anchored to a public testnet so the registry's history is publicly
verifiable without revealing any hash. Only the interface and the pure root computation live here;
there is no network code and no feature flag wired. Build `Anchorer` for a chain only if the
organiser confirms the on-chain bonus applies to Topic E."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol


def merkle_root(leaves: Sequence[str]) -> str | None:
    """Root of a binary tree over hex sha256 leaves (sorted, a lone node is paired with itself).
    None for an empty day."""
    level = sorted(bytes.fromhex(x) for x in leaves)
    if not level:
        return None
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(a + b).digest() for a, b in zip(level[::2], level[1::2], strict=True)
        ]
    return level[0].hex()


@dataclass(frozen=True, slots=True)
class Anchor:
    day: date
    root: str
    tx_hash: str


class Anchorer(Protocol):
    def anchor(self, day: date, root: str) -> Anchor:
        """Publish `root` for `day` and return the transaction reference."""
        ...
