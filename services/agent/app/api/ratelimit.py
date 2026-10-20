"""In-process sliding-window rate limiter (pure ASGI, no dependency).

Limits are per process: with `uvicorn --workers N` or several serverless instances each one counts
on its own, so the effective ceiling is roughly N x the configured number. That is enough to stop a
runaway client or a cheap flood; a shared limiter (Redis, the platform's WAF) is the next step.

Buckets (all per minute, settings RATE_LIMIT_*):
  chat           POST /chat, /chat/stream               keyed by IP + session cookie
  upload         POST /deals/{id}/documents, lender file  keyed by IP + session cookie
  sandbox-create POST /demo/sandbox                      keyed by IP only (cookies are free to mint)
  global         every other request                     keyed by IP only, so rotating cookies
                                                         never gets around the ceiling
/health, the OpenAPI docs and CORS preflights are exempt. The client IP is the socket peer; an
X-Forwarded-For header is believed only when the peer is in TRUSTED_PROXIES.
"""

import hashlib
import ipaddress
import math
import re
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from http.cookies import SimpleCookie

from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.demo import COOKIE_NAME as USER_COOKIE
from app.config import Settings, get_settings
from app.demo.sandbox import COOKIE_NAME as SANDBOX_COOKIE
from app.errors import problem

EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")
UPLOAD_PATH = re.compile(r"^(/deals/[^/]+/documents|/registry/lender-check/file)/?$")
INTERNAL_PEERS = frozenset({"testclient"})  # Starlette's in-process client (demo runner, tests)
MAX_KEYS = 20_000
WINDOW = 60.0

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _parse_networks(entries: list[str]) -> tuple[bool, list[Network]]:
    nets: list[Network] = []
    everyone = False
    for entry in entries:
        if entry == "*":
            everyone = True
            continue
        try:
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return everyone, nets


def client_ip(scope: Scope, trusted: tuple[bool, list[Network]]) -> str:
    everyone, nets = trusted
    peer = (scope.get("client") or ("unknown", 0))[0]

    def is_trusted(addr: str) -> bool:
        if everyone:
            return True
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in n for n in nets)

    if not is_trusted(peer):
        return peer
    headers = dict(scope["headers"])
    raw = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    hops = [h.strip() for h in raw.split(",") if h.strip()]
    for hop in reversed(hops):  # right to left: skip our own proxies, stop at the first outsider
        if not is_trusted(hop):
            return hop
    return hops[0] if hops else peer


def _is_internal(scope: Scope) -> bool:
    """The in-process Starlette client (demo runner, tests) has no socket. A request carrying a
    forwarding header is never internal, so the name cannot be spoofed through a proxy."""
    peer = (scope.get("client") or ("unknown", 0))[0]
    return peer in INTERNAL_PEERS and b"x-forwarded-for" not in dict(scope["headers"])


def _session_key(scope: Scope) -> str:
    raw = dict(scope["headers"]).get(b"cookie", b"").decode("latin-1")
    if not raw:
        return ""
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ""
    for name in (SANDBOX_COOKIE, USER_COOKIE):
        if name in jar:
            return hashlib.sha256(jar[name].value.encode()).hexdigest()[:16]
    return ""


class SlidingWindows:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def hit(self, bucket: str, key: str, limit: int) -> float | None:
        """None if the request fits, else the seconds until the oldest hit leaves the window."""
        now = self._clock()
        with self._lock:
            window = self._windows[(bucket, key)]
            while window and now - window[0] >= WINDOW:
                window.popleft()
            if len(window) >= limit:
                return max(0.0, WINDOW - (now - window[0]))
            window.append(now)
            if len(self._windows) > MAX_KEYS:
                for k in [k for k, w in self._windows.items() if not w or now - w[-1] >= WINDOW]:
                    self._windows.pop(k, None)
        return None


def bucket_for(method: str, path: str, settings: Settings) -> tuple[str, int, bool]:
    """(bucket, limit per minute, keyed by session as well as IP)."""
    if method == "POST" and path.rstrip("/") in ("/chat", "/chat/stream"):
        return "chat", settings.rate_limit_chat_per_minute, True
    if method == "POST" and UPLOAD_PATH.match(path):
        return "upload", settings.rate_limit_upload_per_minute, True
    if method == "POST" and path.rstrip("/") == "/demo/sandbox":
        return "sandbox-create", settings.rate_limit_sandbox_create_per_minute, False
    return "global", settings.rate_limit_global_per_minute, False


class RateLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.windows = SlidingWindows()
        self._trusted_src = ""
        self._trusted: tuple[bool, list[Network]] = (False, [])

    def _trusted_networks(self, settings: Settings) -> tuple[bool, list[Network]]:
        if settings.trusted_proxies != self._trusted_src:
            self._trusted = _parse_networks(settings.trusted_proxy_list)
            self._trusted_src = settings.trusted_proxies
        return self._trusted

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        settings = get_settings()
        if (
            scope["type"] != "http"
            or not settings.rate_limit_enabled
            or scope["method"] == "OPTIONS"
            or scope["path"].startswith(EXEMPT_PREFIXES)
            or _is_internal(scope)
        ):
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope, self._trusted_networks(settings))
        bucket, limit, by_session = bucket_for(scope["method"], scope["path"], settings)
        wait: float | None = None
        if bucket != "global":  # a chat call also counts toward the caller's global ceiling
            key = f"{ip}|{_session_key(scope)}" if by_session else ip
            wait = self.windows.hit(bucket, key, limit)
        if wait is None:
            wait = self.windows.hit("global", ip, settings.rate_limit_global_per_minute)
        if wait is not None:
            response = problem(
                429,
                "Too many requests",
                "you are sending requests too fast; wait a moment and try again",
                "RATE_LIMITED",
            )
            response.headers["Retry-After"] = str(max(1, math.ceil(wait)))
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
