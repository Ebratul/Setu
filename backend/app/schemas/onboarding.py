"""Request/response models for onboarding, the admin review queue and party members."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.enums import AccountType

Currency = Literal["BDT", "USD", "CNY"]
LanguageOut = Literal["en", "bn", "zh"]
ReviewStatus = Literal["PENDING", "APPROVED", "REJECTED"]
CheckStatus = Literal["PASS", "WARN", "FAIL"]
MemberRoleOut = Literal["OWNER", "FINANCE", "VIEWER"]

ISO2 = re.compile(r"^[A-Za-z]{2}$")
ACCOUNT_NO = re.compile(r"^[A-Za-z0-9]{8,34}$")
BD_TIN = re.compile(r"^\d{9,13}$")


def _iso2(value: str) -> str:
    if not ISO2.match(value):
        raise ValueError("must be a 2-letter ISO country code")
    return value.upper()


class BankAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_name: str = Field(min_length=2, max_length=120)
    bank_country: str
    account_number: str
    holder_name: str = Field(min_length=2, max_length=200)
    currency: Currency
    account_type: AccountType

    @field_validator("bank_country")
    @classmethod
    def _country(cls, v: str) -> str:
        return _iso2(v)

    @field_validator("account_number")
    @classmethod
    def _number(cls, v: str) -> str:
        if v.upper().startswith("SIM-"):
            raise ValueError("demo (SIM-) account numbers cannot be used for a real account")
        if not ACCOUNT_NO.match(v):
            raise ValueError("account number must be 8-34 letters or digits")
        return v


class OnboardingIn(BaseModel):
    """What a new user submits. The role is derived from `account_type` by the server; ADMIN and
    JUDGE cannot be chosen."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_type: Literal["BUYER", "SUPPLIER"]
    display_name: str = Field(min_length=2, max_length=120)
    legal_name: str = Field(min_length=2, max_length=200)
    license_name: str | None = Field(default=None, min_length=2, max_length=200)
    license_no: str = Field(min_length=3, max_length=64)
    tax_id: str = Field(min_length=5, max_length=32)
    city: str = Field(min_length=2, max_length=80)
    country: str
    language: LanguageOut = "en"
    bank_account: BankAccountIn

    @field_validator("country")
    @classmethod
    def _country(cls, v: str) -> str:
        return _iso2(v)

    @model_validator(mode="after")
    def _bd_buyer(self) -> "OnboardingIn":
        if self.account_type == "BUYER" and self.country == "BD" and not BD_TIN.match(self.tax_id):
            raise ValueError("a Bangladesh buyer needs a TIN of 9-13 digits")
        return self


class PublicCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    status: CheckStatus
    detail: str


class OnboardingStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus
    account_status: Literal["PENDING", "ACTIVE", "SUSPENDED"]
    role: Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"]
    party_name: str | None
    checks: list[PublicCheck]
    submitted_at: datetime | None
    decided_at: datetime | None
    reason: str | None


class AdminCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    status: CheckStatus
    detail: str


class AdminParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    kind: Literal["BUYER", "SUPPLIER", "LENDER"]
    legal_name: str
    license_name: str | None
    license_no: str | None
    tax_id: str | None
    city: str
    country: str
    kyb_status: Literal["PENDING", "VERIFIED", "WARNING", "FAILED"]


class AdminBank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_name: str
    bank_country: str
    account_masked: str
    holder_name: str
    account_type: Literal["CORPORATE", "PERSONAL"]
    currency: str
    status: Literal["ACTIVE", "PENDING_CHANGE", "RETIRED"]


class ReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    status: ReviewStatus
    recommendation: Literal["AUTO_CLEAR", "NEEDS_REVIEW", "BLOCK"]
    score: int
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    party: AdminParty
    bank_account: AdminBank | None
    checks: list[AdminCheck]
    submitted_at: datetime
    decided_at: datetime | None
    decided_by: uuid.UUID | None
    reason: str | None


class ReviewList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReviewOut]


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=10, max_length=500)


class MemberOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    email: str
    display_name: str
    member_role: MemberRoleOut
    status: Literal["PENDING", "ACTIVE", "SUSPENDED"]
    signed_in_once: bool
    created_at: datetime


class MemberList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_id: uuid.UUID
    items: list[MemberOut]


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=2, max_length=120)
    member_role: MemberRoleOut
