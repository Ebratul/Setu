import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
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
    RegistryPurpose,
    RegistryStatus,
    Severity,
)


class Document(Base):
    """Trade document metadata. `sha256` is over file bytes; `canonical_hash` over key fields."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("deal_id", "sha256"),)

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
    sha256: Mapped[str | None] = mapped_column(CHAR(64), index=True)
    canonical_hash: Mapped[str | None] = mapped_column(CHAR(64), index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[DocStatus] = mapped_column(str_enum(DocStatus, "doc_status"))
    check_status: Mapped[CheckStatus] = mapped_column(str_enum(CheckStatus, "doc_check_status"))
    variant: Mapped[str | None] = mapped_column(String(16))
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )


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
    """Shared cross-lender registry of documents used as escrow evidence or financing collateral
    (SR-6). Hashes and minimal metadata only: never document content, prices or counterparties.
    `context_key` (purpose + lender + deal) makes one entry per document per context."""

    __tablename__ = "hash_registry"
    __table_args__ = (UniqueConstraint("sha256", "context_key"),)

    id: Mapped[UUIDPk]
    sha256: Mapped[str] = mapped_column(CHAR(64), index=True)
    semantic_fingerprint: Mapped[str | None] = mapped_column(CHAR(64), index=True)
    doc_type: Mapped[DocType] = mapped_column(str_enum(DocType, "registry_doc_type"))
    purpose: Mapped[RegistryPurpose] = mapped_column(
        str_enum(RegistryPurpose, "registry_purpose"), default=RegistryPurpose.FINANCING_COLLATERAL
    )
    context_key: Mapped[str] = mapped_column(String(100))
    lender_party_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("parties.id"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="SET NULL")
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL")
    )
    external_ref: Mapped[str | None] = mapped_column(String(64))
    registered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[RegistryStatus] = mapped_column(
        str_enum(RegistryStatus, "registry_status"), default=RegistryStatus.ACTIVE, index=True
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exact_hits: Mapped[int] = mapped_column(Integer, default=0)
    near_hits: Mapped[int] = mapped_column(Integer, default=0)


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
    # Phase 17: the risk context the request was decided on, expiry, the simulated OTP (hash only).
    context_hash: Mapped[str | None] = mapped_column(CHAR(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_hash: Mapped[str | None] = mapped_column(CHAR(64))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    otp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(300))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class ApprovalEvent(Base):
    """Readable activity per approval (the deal timeline and the notification bell). One row per
    party that should see it; `audit_seq` links to the signed audit row of the same step."""

    __tablename__ = "approval_events"

    id: Mapped[UUIDPk]
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    party_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("parties.id", ondelete="CASCADE"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))
    tier: Mapped[int] = mapped_column(SmallInteger, default=0)
    actor: Mapped[str] = mapped_column(String(8), default="system")
    title_en: Mapped[str] = mapped_column(String(200))
    title_bn: Mapped[str] = mapped_column(String(200))
    detail_en: Mapped[str] = mapped_column(String(600), default="")
    detail_bn: Mapped[str] = mapped_column(String(900), default="")
    audit_seq: Mapped[int | None] = mapped_column(BigInteger)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemoPhoneMessage(Base):
    """The simulated SMS inbox of the buyer ("Demo phone"). Holds the one-time code in clear on
    purpose (it IS the simulated SMS); only served by the demo endpoint when DEMO_MODE is on."""

    __tablename__ = "demo_phone_messages"

    id: Mapped[UUIDPk]
    party_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("parties.id", ondelete="CASCADE"), index=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(String(300))
    code: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class RiskEvent(Base):
    """One row per risk-engine decision (Phase 5.1), readable by the admin console and the
    evaluation harness. The signed audit log holds only a hash of the same decision
    (`audit_seq`), so this table is the readable copy."""

    __tablename__ = "risk_events"

    id: Mapped[UUIDPk]
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    origin: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(20))
    tier: Mapped[int] = mapped_column(SmallInteger)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    explanation_en: Mapped[str] = mapped_column(String(600))
    explanation_bn: Mapped[str] = mapped_column(String(900))
    context_hash: Mapped[str] = mapped_column(CHAR(64))
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    hints: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    audit_seq: Mapped[int | None] = mapped_column(BigInteger)


class InjectionEvent(Base):
    """One detection of instruction-like text in untrusted content, or one tool call dropped by
    the gate (P19). Readable copy for /admin/security; the signed audit row is `audit_seq`.
    `flags_deal` = layer 3: the deal's next money action is Tier 3 until an admin resolves it.
    Only rule codes and a short safe snippet are kept, never the document."""

    __tablename__ = "injection_events"

    id: Mapped[UUIDPk]
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # DETECTED | BLOCKED_TOOL
    source: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16), default="live")  # live | console | suite
    rules: Mapped[list[str]] = mapped_column(JSONB, default=list)
    score: Mapped[int] = mapped_column(SmallInteger, default=0)
    snippet: Mapped[str] = mapped_column(String(200), default="")
    attack_style: Mapped[str | None] = mapped_column(String(32), index=True)
    tool: Mapped[str | None] = mapped_column(String(64))
    action_taken: Mapped[str] = mapped_column(String(32))
    layer: Mapped[int | None] = mapped_column(SmallInteger)
    defences_on: Mapped[bool] = mapped_column(Boolean, default=True)
    flags_deal: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("deals.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_seq: Mapped[int | None] = mapped_column(BigInteger)
