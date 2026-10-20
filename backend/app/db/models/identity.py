import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Amount, Base, Created, Fraction, UUIDPk, str_enum
from app.db.enums import (
    AccountStatus,
    AccountType,
    KybStatus,
    Language,
    MemberRole,
    OnboardingStatus,
    PartyKind,
    Role,
    UserStatus,
)


class Party(Base):
    """A buyer SME, a supplier or a lender. All seeded parties are fictional."""

    __tablename__ = "parties"

    id: Mapped[UUIDPk]
    code: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[PartyKind] = mapped_column(str_enum(PartyKind, "party_kind"))
    legal_name: Mapped[str] = mapped_column(String(200))
    license_name: Mapped[str | None] = mapped_column(String(200))
    license_no: Mapped[str | None] = mapped_column(String(64))
    alias: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(CHAR(2))
    first_seen_on: Mapped[date] = mapped_column(Date)
    cash_balance: Mapped[Amount | None]
    cash_currency: Mapped[str | None] = mapped_column(CHAR(3))
    kyb_status: Mapped[KybStatus] = mapped_column(
        str_enum(KybStatus, "kyb_status"), default=KybStatus.PENDING
    )
    tax_id: Mapped[str | None] = mapped_column(String(32))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Created]


class User(Base):
    """Application account. Credentials live in Neon Auth (`auth_subject` is its stable user id);
    demo users have no `auth_subject` and no passwords (server-side 'login as' switch)."""

    __tablename__ = "users"

    id: Mapped[UUIDPk]
    email: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(str_enum(Role, "user_role"))
    language: Mapped[Language] = mapped_column(str_enum(Language, "user_language"))
    party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("parties.id"))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    auth_subject: Mapped[str | None] = mapped_column(String(128), unique=True)
    status: Mapped[UserStatus] = mapped_column(
        str_enum(UserStatus, "user_status"),
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[Created]

    def __init__(self, **kw: Any) -> None:
        """Real (non-demo) accounts start PENDING until activated; seeded demo users are ACTIVE."""
        if not kw.get("is_demo", True):
            kw.setdefault("status", UserStatus.PENDING)
        super().__init__(**kw)


class BankAccount(Base):
    """Receiving account of a party. Numbers are fictional and prefixed 'SIM-'."""

    __tablename__ = "bank_accounts"

    id: Mapped[UUIDPk]
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    bank_country: Mapped[str] = mapped_column(CHAR(2))
    account_number: Mapped[str] = mapped_column(String(64))
    holder_name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[AccountType] = mapped_column(str_enum(AccountType, "account_type"))
    currency: Mapped[str] = mapped_column(CHAR(3))
    status: Mapped[AccountStatus] = mapped_column(str_enum(AccountStatus, "account_status"))
    opened_on: Mapped[date] = mapped_column(Date)
    first_seen_on: Mapped[date] = mapped_column(Date)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    change_requested_via: Mapped[str | None] = mapped_column(String(32))
    change_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Created]


class KybCheck(Base):
    """Latest KYB result per (party, receiving account); reasons are [{code, message}]."""

    __tablename__ = "kyb_checks"

    id: Mapped[UUIDPk]
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("bank_accounts.id"))
    status: Mapped[KybStatus] = mapped_column(str_enum(KybStatus, "kyb_check_status"))
    score: Mapped[Fraction]
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KybRun(Base):
    """One row per KYB verification run (history). `result` is the full KybResult JSON."""

    __tablename__ = "kyb_runs"

    id: Mapped[UUIDPk]
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("deals.id"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    audit_seq: Mapped[int | None] = mapped_column(BigInteger)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PartyMember(Base):
    """A user's party-level role. A user with a `party_id` and no row here counts as OWNER (seeded
    demo users), so existing behaviour is unchanged."""

    __tablename__ = "party_members"
    __table_args__ = (UniqueConstraint("party_id", "user_id"),)

    id: Mapped[UUIDPk]
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    member_role: Mapped[MemberRole] = mapped_column(str_enum(MemberRole, "member_role"))
    created_at: Mapped[Created]


class OnboardingReview(Base):
    """Self-service onboarding submission and its KYB result. `checks` is a list of
    {code, status, detail}; the decision is an admin's (or the system's when auto-approved)."""

    __tablename__ = "onboarding_reviews"

    id: Mapped[UUIDPk]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"), index=True)
    status: Mapped[OnboardingStatus] = mapped_column(
        str_enum(OnboardingStatus, "onboarding_status"), default=OnboardingStatus.PENDING
    )
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    score: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "BankAccount",
    "KybCheck",
    "KybRun",
    "OnboardingReview",
    "Party",
    "PartyMember",
    "User",
]


class StepupChallenge(Base):
    """An emailed step-up code (HMAC only). One row per code sent; `attempts` caps wrong guesses and
    `consumed_at` makes a code single-use."""

    __tablename__ = "stepup_challenges"

    id: Mapped[UUIDPk]
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
