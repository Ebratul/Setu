"""Code-side validation of extracted values (parser and LLM alike): a value that fails becomes
None and a warning is recorded. The model never decides what is valid."""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.forensics.fields import FIELD_MODELS, DocFields
from app.forensics.parse_fields import CURRENCIES, MAX_TEXT, clean_text

_HS = re.compile(r"^\d{4}(\.\d{2}){0,2}$|^\d{6,10}$")
POSITIVE = frozenset(
    {"quantity", "unit_price", "total", "net_weight_kg", "gross_weight_kg", "packages",
     "assessed_value_usd", "fx_usd_bdt"}
)  # fmt: skip
NON_NEGATIVE = frozenset({"duty_usd", "duty_bdt", "assessed_value_bdt"})
DATE_FIELDS = frozenset(
    {"date", "production_complete", "est_ship_date", "eta", "on_board_date", "issue_date"}
)
MIN_DATE, MAX_DATE = dt.date(2000, 1, 1), dt.date(2100, 1, 1)


def validate_value(name: str, value: Any) -> Any:
    """The cleaned value, or raise ValueError."""
    if value is None:
        return None
    if name in DATE_FIELDS:
        d = value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
        if not MIN_DATE <= d <= MAX_DATE:
            raise ValueError("date out of range")
        return d
    if name == "packages":
        n = int(str(value).replace(",", ""))
        if n <= 0:
            raise ValueError("must be positive")
        return n
    if name in POSITIVE | NON_NEGATIVE or name == "total":
        try:
            n = Decimal(str(value).replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError("not a number") from exc
        if not n.is_finite() or abs(n) >= Decimal("1e15"):
            raise ValueError("out of range")
        if (name in POSITIVE and n <= 0) or n < 0:
            raise ValueError("must be positive")
        return n
    text = clean_text(str(value))
    if not text:
        return None
    if name == "currency":
        code = text.upper()
        if code not in CURRENCIES:
            raise ValueError("unknown currency")
        return "CNY" if code == "RMB" else code
    if name == "hs_code" and not _HS.match(text):
        raise ValueError("not an HS code")
    return text[:MAX_TEXT]


def sanitise(doc_type: str, data: dict[str, Any]) -> tuple[DocFields, list[str]]:
    """Validate every field against its rule; invalid -> None + `FIELD_INVALID:<name>`."""
    model = FIELD_MODELS[doc_type]
    clean: dict[str, Any] = {"doc_type": doc_type}
    warnings: list[str] = []
    for name, value in data.items():
        if name == "doc_type" or name not in model.model_fields:
            continue
        try:
            clean[name] = validate_value(name, value)
        except (ValueError, TypeError):
            warnings.append(f"FIELD_INVALID:{name}")
    return model.model_validate(clean), warnings  # type: ignore[return-value]
