"""Pure validators for onboarding input (no I/O).

USCC (unified social credit code, GB 32100-2015): 18 characters from an alphabet that drops
I, O, S, V, Z; the 18th is a check character: with the 17 leading characters mapped to their
index `i` in the alphabet and weights W, `check = (31 - sum(W[k] * i[k]) % 31) % 31`.
"""

import re
from datetime import date, timedelta

USCC_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY"
USCC_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)
BD_MOBILE = re.compile(r"^\+8801[3-9]\d{8}$")
EXPIRY_WARN_DAYS = 30


def uscc_check_char(first17: str) -> str | None:
    if len(first17) != 17 or any(c not in USCC_ALPHABET for c in first17):
        return None
    total = sum(w * USCC_ALPHABET.index(c) for w, c in zip(USCC_WEIGHTS, first17, strict=True))
    return USCC_ALPHABET[(31 - total % 31) % 31]


def uscc_valid(value: str) -> bool:
    v = value.strip().upper()
    return len(v) == 18 and uscc_check_char(v[:17]) == v[17]


def normalise_bd_mobile(value: str) -> str | None:
    """Canonical +8801XXXXXXXXX or None. Accepts 01712345678, 8801712345678, +880 1712-345678."""
    compact = re.sub(r"[\s\-()]", "", value)
    if compact.startswith("01"):
        compact = "+88" + compact
    elif compact.startswith("8801"):
        compact = "+" + compact
    return compact if BD_MOBILE.match(compact) else None


E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalise_mobile(value: str) -> str | None:
    """Canonical E.164 for any country (suppliers), or None. Bangladesh shortcuts still work."""
    bd = normalise_bd_mobile(value)
    if bd is not None:
        return bd
    compact = re.sub(r"[\s\-()]", "", value)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    return compact if E164.match(compact) else None


def id_matches(pattern: str, value: str) -> bool:
    """`pattern` is an operator-configurable regex over the upper-cased value without spaces."""
    try:
        return (
            re.fullmatch(pattern.lstrip("^").rstrip("$"), re.sub(r"\s", "", value.upper()))
            is not None
        )
    except re.error:
        return False


def expiry_state(expiry: date, today: date) -> str:
    """'EXPIRED' | 'EXPIRING' (within 30 days) | 'OK'."""
    if expiry < today:
        return "EXPIRED"
    return "EXPIRING" if expiry <= today + timedelta(days=EXPIRY_WARN_DAYS) else "OK"
