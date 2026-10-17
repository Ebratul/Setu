"""Privacy Gateway (SR-4).

TODO(P18): real masking — NID, bank accounts, phones, emails, amounts in documents and known
party names become reversible tokens (⟦ACCT_1⟧ …) with a per-request vault; unmask only the
final user-facing answer. Until then every function is an identity pass-through, but the call
sites (graph node before any LLM call, tool-result storage) are already wired.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Masked:
    text: str
    vault: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.vault)


def mask(text: str) -> Masked:
    return Masked(text)


def unmask(text: str, vault: dict[str, str]) -> str:
    for token, value in vault.items():
        text = text.replace(token, value)
    return text


def mask_for_storage(text: str) -> str:
    """Tool results are stored masked (chat_messages.content)."""
    return mask(text).text
