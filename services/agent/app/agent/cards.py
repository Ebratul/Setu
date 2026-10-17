"""Turn tool results into validated cards for the API and SSE (UI rendering only)."""

import json
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.agent.state import ToolResult
from app.schemas.cards import CARD_TYPES, Card

_CARD = TypeAdapter(Card)


def parse_card(payload: str) -> Card | None:
    try:
        data: Any = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("card_type") not in CARD_TYPES:
        return None
    try:
        return _CARD.validate_python(data)
    except ValidationError:
        return None


def card_of(result: ToolResult) -> Card | None:
    return parse_card(result["payload"]) if result["ok"] else None


def cards_of(results: list[ToolResult]) -> list[Card]:
    return [c for c in (card_of(r) for r in results) if c is not None]
