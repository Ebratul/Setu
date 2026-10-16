"""Shared seed helpers: anchor date, deterministic ids, Dhaka timestamps, seeded RNG.

Every date in the demo is `DEMO_TODAY + n days`, so the demo never goes stale. Every row id is a
uuid5 of a stable key, so re-running the seed upserts the same rows.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.db.base import Base

SEED_VERSION = "v1"
NAMESPACE = uuid.UUID("5e7a0c3e-2b1d-4f6a-9c8e-5e7475000001")
DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")

Row = dict[str, Any]
Rows = list[tuple[type[Base], list[Row]]]


def sid(kind: str, key: str) -> uuid.UUID:
    """Stable id for a seeded row, e.g. sid("deal", "SETU-2026-0001")."""
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


def rng(stream: str) -> random.Random:
    """Seeded RNG per named stream (str seeds are hashed with sha512, stable across processes)."""
    return random.Random(f"setu-seed-{SEED_VERSION}:{stream}")


def usd(value: str | int) -> Decimal:
    if isinstance(value, float):
        raise TypeError("no floats in seed money")
    return Decimal(value)


@dataclass(frozen=True, slots=True)
class Ctx:
    today: date

    def day(self, offset: int) -> date:
        return self.today + timedelta(days=offset)

    def at(self, offset: int, hh: int = 10, mm: int = 0) -> datetime:
        d = self.day(offset)
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=DHAKA)

    def month_start(self, months_back: int) -> date:
        """First day of the month `months_back` calendar months before today's month."""
        index = self.today.year * 12 + (self.today.month - 1) - months_back
        return date(index // 12, index % 12 + 1, 1)


def default_ctx() -> Ctx:
    return Ctx(today=get_settings().demo_today)
