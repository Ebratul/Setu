"""The gateway of the request that is running, for call sites that have no graph config
(document extraction). A ContextVar, so concurrent requests never share a vault."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.privacy.gateway import PrivacyGateway

_current: ContextVar[PrivacyGateway | None] = ContextVar("setu_privacy_gateway", default=None)


def current_gateway() -> PrivacyGateway | None:
    return _current.get()


@contextmanager
def use_gateway(gw: PrivacyGateway) -> Iterator[PrivacyGateway]:
    token = _current.set(gw)
    try:
        yield gw
    finally:
        _current.reset(token)
