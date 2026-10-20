import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from sqlalchemy import CHAR, DateTime, Enum, MetaData, Numeric, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Money columns: NUMERIC(20,4); FX rates NUMERIC(20,8); fractions (0.30 = 30%) NUMERIC(9,6).
Amount = Annotated[Decimal, mapped_column(Numeric(20, 4))]
Rate = Annotated[Decimal, mapped_column(Numeric(20, 8))]
Fraction = Annotated[Decimal, mapped_column(Numeric(9, 6))]
CurrencyCode = Annotated[str, mapped_column(CHAR(3))]
UUIDPk = Annotated[uuid.UUID, mapped_column(Uuid, primary_key=True)]
Str64 = Annotated[str, mapped_column(String(64))]
Created = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now())]


def str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """VARCHAR + CHECK constraint (no native PG enum, so adding values never needs ALTER TYPE)."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
