"""Request/response models for the multi-step onboarding (P30), the admin review queue, the
account page and party members. Inputs are `extra="forbid"`; field errors carry a stable `code`
(pydantic custom error type) that the friendly 422 handler passes to the client."""

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.config import get_settings
from app.domain import onboarding_validation as rules

LanguageOut = Literal["en", "bn", "zh"]
RoleOut = Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"]
AccountStatusOut = Literal[
    "PENDING_PROFILE", "PENDING_VERIFICATION", "ACTIVE", "REJECTED", "SUSPENDED"
]
ReviewStatus = Literal["PENDING", "APPROVED", "REJECTED", "CHANGES_REQUESTED", "SUSPENDED"]
DecisionOut = Literal["APPROVED", "CHANGES_REQUESTED", "REJECTED", "SUSPENDED"]
CheckStatus = Literal["PASS", "WARN", "FAIL"]
MemberRoleOut = Literal["OWNER", "FINANCE", "VIEWER"]
DocTypeOut = Literal["TRADE_LICENSE", "IRC", "TIN_CERT", "BUSINESS_LICENSE", "BANK_PROOF", "OTHER"]
DocStatusOut = Literal["UPLOADED", "VERIFIED", "REJECTED"]
RevealField = Literal["mobile", "trade_license_no", "irc_no", "tin", "uscc", "bank_account_no"]
ImportVolume = Literal["UNDER_500K_BDT", "500K_2M_BDT", "2M_10M_BDT", "OVER_10M_BDT"]

SWIFT = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")
ACCOUNT_NO = re.compile(r"^[A-Za-z0-9]{6,34}$")
CJK = re.compile(r"[㐀-鿿]")
PHONE_ANY = re.compile(r"^\+?[0-9][0-9\- ]{6,18}[0-9]$")


def _bad(code: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(code, message)


# --- onboarding input ------------------------------------------------------------------------


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["BUYER", "SUPPLIER", "ADMIN", "JUDGE"]
    invite_code: str | None = Field(default=None, max_length=128)


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=2, max_length=120)
    designation: str = Field(min_length=2, max_length=80)
    mobile: str = Field(max_length=32)
    language: LanguageOut = "en"

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        normal = rules.normalise_mobile(v)
        if normal is None:
            raise _bad(
                "INVALID_MOBILE", "enter a mobile number with country code, e.g. +8801712345678"
            )
        return normal


class PhoneVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")


class BuyerAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    division: str = Field(min_length=2, max_length=60)
    district: str = Field(min_length=2, max_length=60)
    upazila: str = Field(min_length=2, max_length=60)
    street: str = Field(min_length=3, max_length=200)


class BuyerBusinessIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legal_name: str = Field(min_length=2, max_length=200)
    trade_name: str | None = Field(default=None, min_length=2, max_length=200)
    trade_license_no: str = Field(max_length=64)
    license_authority: str = Field(min_length=2, max_length=120)
    license_expiry: date
    irc_no: str = Field(max_length=64)
    tin: str = Field(max_length=32)
    address: BuyerAddress
    business_type: Literal["MANUFACTURER", "TRADER"]
    main_import_goods: str = Field(min_length=2, max_length=200)
    monthly_import_volume: ImportVolume

    @field_validator("trade_license_no")
    @classmethod
    def _license(cls, v: str) -> str:
        if not rules.id_matches(get_settings().bd_trade_license_regex, v):
            raise _bad("INVALID_TRADE_LICENSE", "trade licence number looks wrong")
        return v

    @field_validator("irc_no")
    @classmethod
    def _irc(cls, v: str) -> str:
        if not rules.id_matches(get_settings().bd_irc_regex, v):
            raise _bad("INVALID_IRC", "import registration certificate number looks wrong")
        return v

    @field_validator("tin")
    @classmethod
    def _tin(cls, v: str) -> str:
        if not rules.id_matches(get_settings().bd_tin_regex, v):
            raise _bad("INVALID_TIN", "TIN must be 9-13 digits")
        return v

    @field_validator("license_expiry")
    @classmethod
    def _expiry(cls, v: date) -> date:
        if v < date.today():
            raise _bad("LICENSE_EXPIRED", "the trade licence has expired")
        return v


class SupplierAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    province: str = Field(min_length=2, max_length=60)
    city: str = Field(min_length=2, max_length=60)
    district: str = Field(min_length=2, max_length=60)
    street: str | None = Field(default=None, min_length=2, max_length=200)


class SupplierBank(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    bank_name: str = Field(min_length=2, max_length=120)
    holder_name: str = Field(min_length=2, max_length=200)
    account_no: str
    currency: Literal["CNY", "USD"]
    swift: str

    @field_validator("account_no")
    @classmethod
    def _account(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v)
        if not ACCOUNT_NO.match(v):
            raise _bad("INVALID_ACCOUNT_NO", "account number must be 6-34 letters or digits")
        return v

    @field_validator("swift")
    @classmethod
    def _swift(cls, v: str) -> str:
        v = v.upper().replace(" ", "")
        if not SWIFT.match(v):
            raise _bad("INVALID_SWIFT", "SWIFT/BIC must be 8 or 11 characters")
        return v


class SupplierBusinessIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    legal_name_en: str = Field(min_length=2, max_length=200)
    legal_name_zh: str = Field(min_length=2, max_length=200)
    uscc: str = Field(max_length=32)
    address: SupplierAddress
    business_scope: str = Field(min_length=3, max_length=500)
    export_experience_years: int = Field(ge=0, le=80)
    wechat_id: str | None = Field(default=None, min_length=2, max_length=64)
    contact_phone: str | None = Field(default=None, max_length=32)
    bank: SupplierBank

    @field_validator("legal_name_zh")
    @classmethod
    def _zh(cls, v: str) -> str:
        if not CJK.search(v):
            raise _bad("NEEDS_CHINESE_NAME", "enter the company name in Chinese characters")
        return v

    @field_validator("uscc")
    @classmethod
    def _uscc(cls, v: str) -> str:
        v = re.sub(r"\s", "", v).upper()
        if len(v) != 18:
            raise _bad("INVALID_USCC_LENGTH", "a USCC has 18 characters")
        if not rules.uscc_valid(v):
            raise _bad("INVALID_USCC_CHECKSUM", "this USCC fails its check digit; re-check it")
        return v

    @field_validator("contact_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v is not None and not PHONE_ANY.match(v):
            raise _bad("INVALID_PHONE", "enter a valid phone number")
        return v


BusinessIn = Annotated[BuyerBusinessIn | SupplierBusinessIn, Field(union_mode="left_to_right")]


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms_version: str = Field(max_length=32)
    accept_terms: Literal[True]
    accept_privacy: Literal[True]
    consent_verification: Literal[True]


class ChangeItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.]+$")
    note: str = Field(min_length=3, max_length=500)


class RequestChangesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChangeItem] = Field(min_length=1, max_length=20)


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=10, max_length=500)


class RevealIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field: RevealField
    reason: str = Field(min_length=10, max_length=300)


# --- onboarding output -----------------------------------------------------------------------


class PublicCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    status: CheckStatus
    detail: str


class StepOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal["role", "contact", "business", "documents", "security", "review"]
    done: bool


class ContactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    designation: str
    mobile_masked: str
    phone_verified: bool
    language: LanguageOut


class VerificationDocumentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    type: DocTypeOut
    original_name: str
    mime: str
    size: int
    status: DocStatusOut
    reviewer_notes: str | None
    created_at: datetime


class ConsentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms_version: str
    accepted_at: datetime


class MfaOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    required: bool


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    note: str


class OnboardingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_status: AccountStatusOut | None
    role: RoleOut | None
    step: int
    steps: list[StepOut]
    contact: ContactOut | None
    business: dict[str, Any] | None
    documents: list[VerificationDocumentOut]
    consent: ConsentOut | None
    mfa: MfaOut
    checks: list[PublicCheck]
    submitted_at: datetime | None
    decision: DecisionOut | None
    change_requests: list[ChangeRequestOut]
    terms_version: str
    demo_mode: bool


class PhoneSent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sent: Literal[True] = True
    expires_in_seconds: int
    sends_left: int
    demo_code: str | None = None


# --- admin review ----------------------------------------------------------------------------


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
    risk_summary: CheckStatus
    score: int
    role: RoleOut
    account_status: AccountStatusOut
    decision: DecisionOut | None
    revision: int
    user_id: uuid.UUID
    user_email: str
    user_display_name: str
    party: AdminParty
    bank_account: AdminBank | None
    contact: ContactOut | None
    business: dict[str, Any] | None
    documents: list[VerificationDocumentOut]
    change_requests: list[ChangeRequestOut]
    checks: list[AdminCheck]
    submitted_at: datetime
    decided_at: datetime | None
    decided_by: uuid.UUID | None
    reason: str | None


class ReviewList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReviewOut]


class RevealOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: RevealField
    value: str


class UrlOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    expires_at: int


# --- account ---------------------------------------------------------------------------------


class AccountOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    email: str
    display_name: str
    role: RoleOut
    language: LanguageOut
    account_status: AccountStatusOut
    auth_provider: str | None
    mfa_enabled: bool
    terms_version: str | None
    terms_accepted_at: datetime | None
    party_name: str | None
    mobile_masked: str | None
    created_at: datetime
    last_login_at: datetime | None


class AccountPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    language: LanguageOut | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


class DeleteRequested(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["SUSPENDED"] = "SUSPENDED"
    deleted_at: datetime


# --- mfa -------------------------------------------------------------------------------------


class TotpSetupOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    otpauth_uri: str
    secret: str


class TotpCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=16, pattern=r"^[A-Za-z0-9-]+$")


class RecoveryCodesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recovery_codes: list[str]
    mfa_enabled: Literal[True] = True


class MfaDisabledOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mfa_enabled: Literal[False] = False


# --- members ---------------------------------------------------------------------------------


class MemberOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    email: str
    display_name: str
    member_role: MemberRoleOut
    status: AccountStatusOut
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
