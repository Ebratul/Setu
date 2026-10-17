import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Created, UUIDPk, str_enum
from app.db.enums import (
    Actor,
    ApprovalAction,
    ApprovalStatus,
    CheckStatus,
    DocStatus,
    DocType,
    Severity,
)


class Document(Base):
    """Trade document metadata. `sha256` is over file bytes; `canonical_hash` over key fields."""

    __tablename__ = "documents"

    id: Mapped[UUIDPk]
    key: Mapped[str] = mapped_column(String(80), unique=True)
    deal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="CASCADE")
    )
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "doc_type"))
    file_name: Mapped[str] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str | None] = mapped_column(CHAR(64), unique=True)
    canonical_hash: Mapped[str | None] = mapped_column(CHAR(64), index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocStatus] = mapped_column(str_enum(DocStatus, "doc_status"))
    check_status: Mapped[CheckStatus] = mapped_column(str_enum(CheckStatus, "doc_check_status"))
    variant: Mapped[str | None] = mapped_column(String(16))
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ForensicFinding(Base):
    __tablename__ = "forensic_findings"
    __table_args__ = (UniqueConstraint("document_id", "check_code"),)

    id: Mapped[UUIDPk]
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE")
    )
    check_code: Mapped[str] = mapped_column(String(48))
    status: Mapped[CheckStatus] = mapped_column(str_enum(CheckStatus, "finding_status"))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "finding_severity"))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HashRegistry(Base):
    """Shared cross-lender registry of financed documents (SR-6)."""

    __tablename__ = "hash_registry"
    __table_args__ = (UniqueConstraint("canonical_hash", "lender_party_id"),)

    id: Mapped[UUIDPk]
    sha256: Mapped[str] = mapped_column(CHAR(64), index=True)
    canonical_hash: Mapped[str] = mapped_column(CHAR(64))
    lender_party_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("parties.id"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="SET NULL")
    )
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "registry_doc_type"))
    external_ref: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ApprovalRequest(Base):
    """Pending human approval for a Tier 2/3 action. Only human HTTP endpoints execute these."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint("tier IN (2, 3)", name="tier_human"),
        CheckConstraint(
            "tier < 3 OR (otp_required AND cooling_off_until IS NOT NULL)", name="tier3_step_up"
        ),
    )

    id: Mapped[UUIDPk]
    key: Mapped[str] = mapped_column(String(80), unique=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="CASCADE")
    )
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("bank_accounts.id", ondelete="CASCADE")
    )
    action: Mapped[ApprovalAction] = mapped_column(str_enum(ApprovalAction, "approval_action"))
    tier: Mapped[int] = mapped_column(SmallInteger)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    params_hash: Mapped[str] = mapped_column(CHAR(64))
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    status: Mapped[ApprovalStatus] = mapped_column(
        str_enum(ApprovalStatus, "approval_status"), index=True
    )
    requested_by: Mapped[Actor] = mapped_column(str_enum(Actor, "approval_actor"))
    otp_required: Mapped[bool] = mapped_column(Boolean, default=False)
    cooling_off_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class AuditLog(Base):
    """Append-only, hash-chained, Ed25519-signed log (SR-5). See app/security/audit.py."""

    __tablename__ = "audit_log"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor: Mapped[Actor] = mapped_column(str_enum(Actor, "audit_actor"))
    action: Mapped[str] = mapped_column(String(64))
    tier: Mapped[int] = mapped_column(SmallInteger)
    params_hash: Mapped[str] = mapped_column(CHAR(64))
    result: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(CHAR(64))
    entry_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    signature: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(32))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)  # unsigned, for listings
    created_at: Mapped[Created]
