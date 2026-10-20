"""Per-request token vault: value ↔ token such as ⟦ACCT_1⟧.

In memory only. It is never persisted, logged, pickled or sent anywhere: `repr` shows a count,
pickling raises, and the owning gateway is dropped at the end of the request. The same value maps
to the same token within a request (so the model can tell two mentions are one account)."""

import re
from typing import NoReturn

TOKEN = re.compile(r"⟦([A-Z]+)_(\d+)⟧")
# Only exact tokens are restored: look-alike brackets in untrusted text must stay text.
LOOSE_TOKEN = TOKEN


class Vault:
    __slots__ = ("_by_key", "_by_token", "_canon", "_next")

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], str] = {}
        self._by_token: dict[str, str] = {}
        self._canon: dict[str, str] = {}
        self._next: dict[str, int] = {}

    def __repr__(self) -> str:
        return f"<Vault tokens={len(self._by_token)}>"

    def __reduce__(self) -> NoReturn:
        raise TypeError("a Vault is never serialised")

    def __len__(self) -> int:
        return len(self._by_token)

    def reserve_from(self, text: str) -> None:
        """Start numbering after tokens already present in earlier turns' (masked) history, so a
        new value can never reuse an old token."""
        for kind, n in TOKEN.findall(text):
            self._next[kind] = max(self._next.get(kind, 0), int(n))

    def token_for(self, kind: str, canonical: str, raw: str) -> str:
        key = (kind, canonical)
        token = self._by_key.get(key)
        if token is None:
            n = self._next.get(kind, 0) + 1
            self._next[kind] = n
            token = f"⟦{kind}_{n}⟧"
            self._by_key[key] = token
            self._by_token[token] = raw
            self._canon[token] = canonical
        return token

    def get(self, token: str) -> str | None:
        return self._by_token.get(token)

    def restore(self, text: str, *, unresolved: str | None = None, canonical: bool = False) -> str:
        """Replace known tokens with their values. Unknown tokens (from an earlier request) are
        left as they are, or replaced by `unresolved` (e.g. "[protected]") when given."""

        def sub(m: re.Match[str]) -> str:
            token = f"⟦{m.group(1)}_{m.group(2)}⟧"
            value = (self._canon if canonical and m.group(1) == "AMT" else self._by_token).get(
                token
            )
            if value is not None:
                return value
            return unresolved.format(type=m.group(1)) if unresolved else m.group(0)

        return LOOSE_TOKEN.sub(sub, text)
