"""The evaluation toggle. INJECTION_DEFENCES=off (or a per-run override from the attack console)
disables layers 2 (detector), 4 (tool gating) and 5 (output guard) only.

Layer 3 (money safety: propose-only tools, the risk engine, Tier 3 on instruction-from-document)
has no switch and must never read this module. `defences(True, layers=...)` exists so the
evaluation can ablate a single layer; production code only ever calls `layer_on`.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.config import get_settings

SWITCHABLE = frozenset({2, 4, 5})
_override: ContextVar[frozenset[int] | None] = ContextVar("injection_layers", default=None)


def layer_on(layer: int) -> bool:
    """Whether a switchable layer (2, 4 or 5) is active in this context."""
    if layer not in SWITCHABLE:
        raise ValueError("only layers 2, 4 and 5 can be switched; layer 3 is always on")
    forced = _override.get()
    if forced is not None:
        return layer in forced
    settings = get_settings()
    # INJECTION_DEFENCES=off is an evaluation setting: a prod deployment ignores it.
    return settings.injection_defences == "on" or settings.app_env == "prod"


def defences_on() -> bool:
    return all(layer_on(n) for n in SWITCHABLE)


@contextmanager
def defences(on: bool, layers: Iterable[int] | None = None) -> Iterator[None]:
    """Force the defences on/off for this context (`layers`: which switchable layers stay on)."""
    active = frozenset(layers) if layers is not None else (SWITCHABLE if on else frozenset())
    token = _override.set(active & SWITCHABLE)
    try:
        yield
    finally:
        _override.reset(token)
