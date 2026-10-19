"""Privacy Gateway (SR-4): reversible masking in front of every model call.

One `PrivacyGateway` lives for one request (a chat turn, a document check, a playground dry-run).
`mask` replaces identifiers with stable tokens held in its in-memory vault; `unmask` restores them
in code after the model answers; `protect` masks the messages of one LLM call, re-scans the
outgoing payload (a hit that slipped through is counted as a leak and masked again) and keeps a
safe transparency record: the masked payload plus counters, never the vault.

Deterministic code always works on real values; only the model sees tokens.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from app.config import get_settings
from app.privacy.detectors import (
    ACCT,
    AMT,
    EMAIL,
    IBAN,
    NAME,
    NID,
    PASSPORT,
    PHONE,
    SWIFT,
    Hit,
    detect,
)
from app.privacy.vault import TOKEN, Vault

# Numeric values under these keys are amounts (tool outputs are JSON, so there is no "USD" next
# to the number for the regex detectors to see).
MONEY_KEY = re.compile(
    r"(?:^|_)(?:amount|amounts|total|price|cost|fee|fees|gap|shortfall|balance|escrow|advance|"
    r"duty|vat|tax|margin|profit|payable|due|bdt|usd|cny|rmb|value|deposit|loan|limit)(?:_|$)",
    re.I,
)
ID_KEYS = {
    "account": ACCT,
    "acct": ACCT,
    "iban": IBAN,
    "swift": SWIFT,
    "bic": SWIFT,
    "phone": PHONE,
    "mobile": PHONE,
    "email": EMAIL,
    "nid": NID,
    "passport": PASSPORT,
    "holder": NAME,
    "beneficiary": NAME,
}
NOT_ID_WORDS = frozenset(
    {"type", "status", "currency", "id", "ids", "count", "kind", "verified", "masked", "invoice"}
)
NOT_MONEY_KEY = re.compile(r"rate|pct|percent|ratio|share|count|score|tier", re.I)
ZERO_WIDTH_TABLE = {c: None for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD, 0x180E)}
UNRESOLVED = "[protected {type}]"


class PrivacyBlocked(RuntimeError):
    """A payload still held an identifier after two masking passes: nothing was sent."""


@dataclass(slots=True)
class Stats:
    masked_by_type: dict[str, int] = field(default_factory=dict)
    leaked_count: int = 0
    chars_sent: int = 0

    @property
    def protected(self) -> int:
        return sum(self.masked_by_type.values())


@dataclass(slots=True)
class CallRecord:
    node: str
    model: str | None
    payload: str  # masked
    stats: Stats
    sent: bool = True
    output: str | None = None  # masked model output
    persisted: bool = False


def is_money_key(key: str | None) -> bool:
    return bool(key) and bool(MONEY_KEY.search(key)) and not NOT_MONEY_KEY.search(key)


def id_type(key: str | None) -> str | None:
    """Identifier type implied by a field name (`bank_account`, `holder_name`, `phone` …)."""
    if not key:
        return None
    parts = key.casefold().split("_")
    if any(p in NOT_ID_WORDS for p in parts):
        return None
    return next((t for word, t in ID_KEYS.items() if word in parts), None)


def _fmt_amount(value: Any) -> tuple[str, str] | None:
    """(canonical, display) for a numeric value, or None when it is not a non-zero number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d == 0:
        return None
    exp = d.as_tuple().exponent
    places = -exp if isinstance(exp, int) and exp < 0 else 0
    return format(d.normalize(), "f"), f"{d:,.{places}f}"


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


class PrivacyGateway:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        mask_amounts: bool | None = None,
        known: dict[str, set[str]] | None = None,
    ) -> None:
        s = get_settings()
        self.enabled = s.privacy_enabled if enabled is None else enabled
        self.mask_amounts = s.privacy_mask_amounts if mask_amounts is None else mask_amounts
        self.known = known or {}
        self.vault = Vault()
        self.calls: list[CallRecord] = []
        # Real tool payloads, same order as the graph's masked `tool_results`; only the UI cards
        # read them. Request-scoped like the vault; never persisted or traced.
        self.raw_results: list[str] = []
        self._seen: set[str] = set()

    # --- masking ------------------------------------------------------------------------------

    def hits(self, text: str) -> list[Hit]:
        return detect(text, mask_amounts=self.mask_amounts, known=self.known)

    def token_of(self, hit: Hit, text: str) -> str:
        raw = text[hit.start : hit.end].translate(ZERO_WIDTH_TABLE)
        return self.vault.token_for(hit.type, hit.normalized, raw)

    @staticmethod
    def defang(text: str) -> str:
        """Token look-alikes in untrusted text become plain brackets, so only tokens this
        gateway issued can ever be restored."""
        return text.replace("⟦", "[").replace("⟧", "]")

    def mask_text(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        self.vault.reserve_from(text)
        hits = self.hits(text)
        tokens = [self.token_of(h, text) for h in hits]  # numbered in order of appearance
        out = text
        for h, token in zip(reversed(hits), reversed(tokens), strict=True):
            out = out[: h.start] + token + out[h.end :]
        return out

    def mask(self, value: Any, *, key: str | None = None) -> Any:
        """Mask a string, or the strings (and money-keyed numbers) inside a dict / list."""
        if not self.enabled:
            return value
        if isinstance(value, str):
            forced = id_type(key)
            if forced and value.strip() and "⟦" not in value:
                digits = "".join(c for c in value if c.isdigit())
                canon = value.casefold() if forced in (NAME, EMAIL) or not digits else digits
                return self.vault.token_for(forced, canon, value.strip())
            if self.mask_amounts and is_money_key(key):
                amt = _fmt_amount(value)
                if amt is not None:
                    return self.vault.token_for(AMT, amt[0], amt[1])
            return self.mask_text(value)
        if isinstance(value, dict):
            return {k: self.mask(v, key=str(k)) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.mask(v, key=key) for v in value]
        if (
            isinstance(value, int | float | Decimal)
            and not isinstance(value, bool)
            and self.mask_amounts
            and is_money_key(key)
        ):
            amt = _fmt_amount(value)
            if amt is not None:
                return self.vault.token_for(AMT, amt[0], amt[1])
        return value

    def mask_payload(self, payload: str) -> str:
        """A tool result (never holds tokens of ours): JSON is masked structurally, anything
        else as text."""
        if not self.enabled:
            return payload
        payload = self.defang(payload)
        try:
            data = json.loads(payload)
        except ValueError:
            return self.mask_text(payload)
        return json.dumps(self.mask(data), ensure_ascii=False, default=str)

    def unmask(self, value: Any, *, unresolved: bool = False, canonical: bool = False) -> Any:
        """Restore tokens in a string or in the strings of a dict / list. `canonical` gives
        amounts as plain numbers (tool arguments) instead of their display form."""
        if isinstance(value, str):
            return self.vault.restore(
                value, unresolved=UNRESOLVED if unresolved else None, canonical=canonical
            )
        if isinstance(value, dict):
            return {
                k: self.unmask(v, unresolved=unresolved, canonical=canonical)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.unmask(v, unresolved=unresolved, canonical=canonical) for v in value]
        return value

    # --- per-call protection and transparency -------------------------------------------------

    def scan(self, text: str) -> int:
        """Identifiers still visible in `text` (0 once it is masked)."""
        return len(self.hits(text))

    def mask_message(self, m: BaseMessage) -> BaseMessage:
        update: dict[str, Any] = {}
        if isinstance(m.content, str):
            update["content"] = self.mask_text(m.content)
        elif isinstance(m.content, list):
            update["content"] = [
                {**b, "text": self.mask_text(b["text"])}
                if isinstance(b, dict) and isinstance(b.get("text"), str)
                else b
                for b in m.content
            ]
        if isinstance(m, AIMessage) and m.tool_calls:
            update["tool_calls"] = [
                {**c, "args": self.mask(c.get("args") or {})} for c in m.tool_calls
            ]
        return m.model_copy(update=update) if update else m

    def protect(
        self,
        messages: list[BaseMessage],
        *,
        node: str,
        model: str | None = None,
        sent: bool = True,
    ) -> tuple[list[BaseMessage], CallRecord]:
        masked = [self.mask_message(m) for m in messages]
        payload = render_payload(masked)
        leaked = self.scan(payload)
        if leaked and self.enabled:
            masked = [self.mask_message(m) for m in masked]  # second pass; still counted
            payload = render_payload(masked)
        record = CallRecord(node, model, payload, self._stats(payload, leaked), sent)
        self.calls.append(record)
        if self.enabled and sent and self.scan(payload):
            raise PrivacyBlocked("an identifier survived masking; the call was not made")
        return masked, record

    def protect_text(
        self, text: str, *, node: str, model: str | None = None, sent: bool = True
    ) -> tuple[str, CallRecord]:
        masked = self.mask_text(text)
        leaked = self.scan(masked)
        if leaked and self.enabled:
            masked = self.mask_text(masked)
        record = CallRecord(node, model, masked, self._stats(masked, leaked), sent)
        self.calls.append(record)
        return masked, record

    def _stats(self, payload: str, leaked: int) -> Stats:
        """Counters of one call. `masked_by_type` counts tokens NEW in this call (not seen in an
        earlier call of the same request), so summing calls counts each protected value once."""
        tokens = {m.group(0) for m in TOKEN.finditer(payload)}
        by_type: Counter[str] = Counter(t[1:-1].rsplit("_", 1)[0] for t in tokens - self._seen)
        self._seen |= tokens
        return Stats(dict(by_type), leaked, len(payload))

    # --- aggregates ---------------------------------------------------------------------------

    def totals(self) -> Stats:
        by_type: Counter[str] = Counter()
        for c in self.calls:
            by_type.update(c.stats.masked_by_type)
        return Stats(
            dict(by_type),
            sum(c.stats.leaked_count for c in self.calls),
            sum(c.stats.chars_sent for c in self.calls),
        )


def render_payload(messages: list[BaseMessage]) -> str:
    """What the provider receives, as one readable text (role-labelled)."""
    parts: list[str] = []
    for m in messages:
        body = text_of(m.content)
        if isinstance(m, AIMessage) and m.tool_calls:
            body += "\n" + json.dumps(
                [{"tool": c["name"], "args": c.get("args")} for c in m.tool_calls],
                ensure_ascii=False,
                default=str,
            )
        parts.append(f"[{m.type}]\n{body}")
    return "\n\n".join(parts)


class StreamUnmasker:
    """Unmasks streamed text chunks; holds back a trailing partial token (`⟦ACCT_`) until it is
    complete, so the client never sees half a token."""

    def __init__(self, gateway: PrivacyGateway) -> None:
        self.gateway = gateway
        self.buffer = ""

    def feed(self, chunk: str) -> str:
        text = self.buffer + chunk
        cut = max(text.rfind("⟦"), text.rfind("[["), text.rfind("【"))
        if cut != -1 and not re.search(r"[⟧】]|\]\]", text[cut:]) and len(text) - cut < 24:
            self.buffer, text = text[cut:], text[:cut]
        else:
            self.buffer = ""
        return self.gateway.unmask(text, unresolved=True)

    def flush(self) -> str:
        text, self.buffer = self.buffer, ""
        return self.gateway.unmask(text, unresolved=True)
