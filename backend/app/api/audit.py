"""Audit log API: chain view, verification, execution-evidence export, tamper demo, public key.

Reading the whole log is for admins and judges. A buyer may open entries and the export of their
own deals (receipts). Nothing here writes to the log or changes it.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import tamper
from app.audit.export import export_lines, fetch_rows, line_of
from app.audit.keys import (
    PUBLIC_KEY_PATH,
    fingerprint,
    load_signing_key,
    public_pem,
)
from app.audit.scheme import GENESIS_HASH, SCHEME, canonical_json
from app.audit.timeline import describe_entry
from app.audit.verify import Report, verify_lines
from app.auth.deps import CurrentUser, current_user
from app.db.models import AuditLog, Deal
from app.db.session import get_db, get_engine
from app.errors import DomainError, Forbidden, NotFound, ServiceUnavailable
from app.services import escrow as escrow_service

router = APIRouter(tags=["audit"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]

MAX_PAGE = 200
TAMPER_WINDOW = 12


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicKeyOut(Out):
    scheme: str
    genesis: str
    fingerprint: str
    key_id: str
    pem: str
    matches_committed_key: bool


class EntryOut(Out):
    seq: int
    ts: str
    actor_type: Literal["user", "llm", "system"]
    actor_id: str
    deal_id: uuid.UUID | None
    action: str
    tier: int
    decision: str
    payload: dict[str, Any]
    payload_hash: str
    prev_hash: str
    entry_hash: str
    signature: str
    key_id: str
    text_en: str
    text_bn: str


class EntryDetailOut(EntryOut):
    canonical: str = Field(description="The exact bytes hashed into payload_hash")
    verified: bool
    verify_reason: str | None = None


class EntriesOut(Out):
    head_seq: int
    head_hash: str | None
    rows: list[EntryOut]


class VerifyOut(Out):
    ok: bool
    entries_checked: int
    first_seq: int | None
    last_seq: int | None
    broken_seq: int | None
    reason: str | None
    detail: str | None
    anchored: bool
    missing_seqs: int
    scheme: str
    public_key_fingerprint: str
    verified_at: datetime


class CountOut(Out):
    key: str
    count: int


class SummaryOut(Out):
    total: int
    head_seq: int
    head_hash: str | None
    by_action: list[CountOut]
    by_tier: list[CountOut]
    fingerprint: str
    scheme: str
    last_verification: VerifyOut | None


class TamperIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["edit", "delete", "reorder"]
    seq: int = Field(ge=1)
    field: str | None = Field(default=None, max_length=64)
    value: str | None = Field(default=None, max_length=200)
    other_seq: int | None = Field(default=None, ge=1)
    window_from: int | None = Field(default=None, ge=1)
    window_to: int | None = Field(default=None, ge=1)


class TamperOut(Out):
    simulated: Literal[True] = True
    real_table_changed: Literal[False] = False
    report: VerifyOut
    entries: list[EntryOut]


_last_verification: VerifyOut | None = None


def _auditor(user: CurrentUser) -> None:
    if not user.reads_all:
        raise Forbidden("the audit log is for admins and judges")


def _key() -> Ed25519PublicKey:
    try:
        return load_signing_key().public_key()
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        raise ServiceUnavailable("the audit signing key is not available") from exc


def _entry(line: dict[str, Any]) -> EntryOut:
    text = describe_entry(line["action"], line["payload"], line["decision"])
    return EntryOut(**line, text_en=text["en"], text_bn=text["bn"])


def _verify_out(report: Report) -> VerifyOut:
    data = report.as_dict()
    data.pop("problems", None)
    data.pop("contiguous", None)
    return VerifyOut(**data, verified_at=datetime.now(UTC))


def _check_deal_access(db: Session, user: CurrentUser, deal_id: uuid.UUID | None) -> None:
    """Admins and judges read everything; a buyer reads entries of a deal they can see."""
    if user.reads_all:
        return
    deal = db.get(Deal, deal_id) if deal_id else None
    if deal is None or escrow_service.require_view(user, deal) == "SUPPLIER":
        raise NotFound("audit entry not found")


@router.get("/audit/public-key", response_model=PublicKeyOut)
def public_key() -> PublicKeyOut:
    """The key that verifies every entry. Also committed at docs/submission/audit-public-key.pem."""
    pub = _key()
    pem = public_pem(pub)
    committed = PUBLIC_KEY_PATH.exists() and PUBLIC_KEY_PATH.read_text() == pem
    return PublicKeyOut(
        scheme=SCHEME,
        genesis=GENESIS_HASH,
        fingerprint=fingerprint(pub),
        key_id=fingerprint(pub)[:16],
        pem=pem,
        matches_committed_key=committed,
    )


@router.get("/audit/entries", response_model=EntriesOut)
def list_entries(
    db: Db,
    user: User,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    deal_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
) -> EntriesOut:
    """Entries with seq > `after`, oldest first (poll with the last seq you saw). Without
    `after`, the latest `limit` entries."""
    _auditor(user)
    stmt = select(AuditLog)
    if deal_id:
        stmt = stmt.where(AuditLog.deal_id == deal_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if after:
        rows = list(
            db.scalars(stmt.where(AuditLog.seq > after).order_by(AuditLog.seq).limit(limit))
        )
    else:
        rows = list(db.scalars(stmt.order_by(AuditLog.seq.desc()).limit(limit)))[::-1]
    head = db.execute(
        select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
    ).first()
    return EntriesOut(
        head_seq=head[0] if head else 0,
        head_hash=head[1] if head else None,
        rows=[_entry(line_of(r)) for r in rows],
    )


@router.get("/audit/entries/{seq}", response_model=EntryDetailOut)
def entry_detail(seq: int, db: Db, user: User) -> EntryDetailOut:
    row = db.get(AuditLog, seq)
    if row is None:
        raise NotFound("audit entry not found")
    _check_deal_access(db, user, row.deal_id)
    line = line_of(row)
    one = verify_lines([line], _key(), contiguous=False)
    from app.audit.scheme import body_of

    return EntryDetailOut(
        **_entry(line).model_dump(),
        canonical=canonical_json(body_of(line)),
        verified=one.ok,
        verify_reason=one.reason,
    )


@router.get("/audit/summary", response_model=SummaryOut)
def summary(db: Db, user: User) -> SummaryOut:
    _auditor(user)
    global _last_verification
    pub = _key()
    by_action = db.execute(
        select(AuditLog.action, func.count())
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
    ).all()
    by_tier = db.execute(
        select(AuditLog.tier, func.count()).group_by(AuditLog.tier).order_by(AuditLog.tier)
    ).all()
    head = db.execute(
        select(AuditLog.seq, AuditLog.entry_hash).order_by(AuditLog.seq.desc()).limit(1)
    ).first()
    return SummaryOut(
        total=sum(n for _, n in by_action),
        head_seq=head[0] if head else 0,
        head_hash=head[1] if head else None,
        by_action=[CountOut(key=a, count=n) for a, n in by_action],
        by_tier=[CountOut(key=f"T{t}", count=n) for t, n in by_tier],
        fingerprint=fingerprint(pub),
        scheme=SCHEME,
        last_verification=_last_verification,
    )


@router.get("/audit/verify", response_model=VerifyOut)
def verify(
    db: Db,
    user: User,
    from_: Annotated[int | None, Query(alias="from", ge=1)] = None,
    to: Annotated[int | None, Query(ge=1)] = None,
) -> VerifyOut:
    """Re-walk the chain: continuity, every hash, every signature."""
    _auditor(user)
    global _last_verification
    rows = fetch_rows(db, lo=from_, hi=to)
    anchor = None
    if rows and rows[0].seq > 1:
        anchor = db.scalar(select(AuditLog.entry_hash).where(AuditLog.seq == rows[0].seq - 1))
    report = verify_lines([line_of(r) for r in rows], _key(), anchor_prev_hash=anchor)
    out = _verify_out(report)
    if from_ is None and to is None:
        _last_verification = out
    return out


@router.get("/audit/export")
def export(
    db: Db,
    user: User,
    deal_id: uuid.UUID | None = None,
    from_: Annotated[int | None, Query(alias="from", ge=1)] = None,
    to: Annotated[int | None, Query(ge=1)] = None,
    format: Literal["jsonl"] = "jsonl",
) -> StreamingResponse:
    """The sandbox operation log: a header line, then one signed entry per line."""
    if not user.reads_all:
        if deal_id is None:
            raise Forbidden("choose a deal to export")
        _check_deal_access(db, user, deal_id)
    body = "".join(export_lines(db, deal_id=deal_id, lo=from_, hi=to))
    name = f"operation-log-{datetime.now(UTC):%Y-%m-%d}.jsonl"
    return StreamingResponse(
        iter([body]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("/audit/tamper-demo", response_model=TamperOut)
def tamper_demo(body: TamperIn, user: User) -> TamperOut:
    """Change, delete or reorder an entry of an in-memory COPY and verify it. The real table is
    only read, on a read-only connection."""
    _auditor(user)
    engine = get_engine()
    if engine is None:
        raise ServiceUnavailable("database is not configured")
    lo = body.window_from or max(1, body.seq - TAMPER_WINDOW)
    hi = min(body.window_to or body.seq + TAMPER_WINDOW, lo + MAX_PAGE)
    with (
        engine.connect().execution_options(postgresql_readonly=True) as conn,
        Session(bind=conn) as ro,
    ):
        rows = fetch_rows(ro, lo=lo, hi=hi)
        lines = [line_of(r) for r in rows]
        anchor = (
            ro.scalar(select(AuditLog.entry_hash).where(AuditLog.seq == lo - 1)) if lo > 1 else None
        )
    try:
        changed, report = tamper.run(
            lines,
            _key(),
            anchor_prev_hash=anchor,
            mode=body.mode,
            seq=body.seq,
            field=body.field,
            value=body.value,
            other_seq=body.other_seq,
        )
    except tamper.TamperError as exc:
        raise DomainError(str(exc), code="BAD_TAMPER") from exc
    return TamperOut(report=_verify_out(report), entries=[_entry(c) for c in changed])
