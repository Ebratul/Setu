"""FR-4 supplier KYB orchestration: loads rows, runs the pure checks in app/domain/kyb.py, and (for
`verify`) persists the result, writes signed audit rows and syncs KYB alerts.

`evaluate()` never writes (the agent tool uses it). `verify()` is the only writer. The invoice-name
check is per deal; shared state is based on party and account facts only:
- Party.kyb_status (BLOCKED -> FAILED), the KybCheck row per account (updated in place) and
  BankAccount.verified come from the assessment WITHOUT the invoice name.
- A new KybRun history row per run keeps the full, deal-specific result (readable only by buyers
  of that deal), and a deal-level alert carries the invoice-name problem.
- An account is retired (ACTIVE/PENDING_CHANGE -> RETIRED) only when its party/licence/holder
  assessment is BLOCKED (sanctions). A sanctions hit on the invoice name alone is a hold: the
  deal run is WARNING, nothing is retired.
- Audit: KYB_CHECKED per run (with retired_account_ids / verified_changes), plus
  DOC_INSTRUCTION_DETECTED (tier 3) when the seller name looked like an instruction.
- Alerts: supplier-level for every buyer with open deals, deal-level for the run's deal.
"""

import contextlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, can_read_party
from app.config import get_settings
from app.db.enums import AccountStatus, DealStatus, DocType, KybStatus, PartyKind
from app.db.models import BankAccount, Deal, Document, KybCheck, KybRun, Party
from app.domain import kyb as engine
from app.errors import NotFound, ServiceUnavailable
from app.schemas.kyb import (
    AccountSummary,
    KybCheckOut,
    KybHistoryItem,
    KybResult,
    KybStatusOut,
    KybThresholds,
    PendingAccountResult,
)
from app.security.audit import write_audit
from app.security.injection import detect_instructions
from app.services import alerts as alert_service
from app.services.scope import demo_today

log = structlog.get_logger("setu.kyb")

PARTY_STATUS: dict[str, KybStatus] = {
    "VERIFIED": KybStatus.VERIFIED,
    "WARNING": KybStatus.WARNING,
    "BLOCKED": KybStatus.FAILED,
}
HISTORY_LIMIT = 50
NAME_MAX = 200


# --- inputs -----------------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _read_sanctions(path: str, mtime_ns: int) -> tuple[engine.SanctionEntry, ...]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = data.get("entries") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or not data.get("version")
        or not isinstance(raw, list)
        or not raw
    ):
        raise ValueError("sanctions list needs a version and a non-empty entries list")
    entries = []
    for e in raw:
        names = e.get("names")
        if not isinstance(names, list) or not names or not e.get("id"):
            raise ValueError("every sanctions entry needs an id and names")
        entries.append(
            engine.SanctionEntry(
                str(e["id"]), tuple(str(n) for n in names), str(e.get("reason", ""))
            )
        )
    return tuple(entries)


def load_sanctions(path: Path | None = None) -> tuple[engine.SanctionEntry, ...]:
    """The mock sanctions list (settings.kyb_sanctions_path, relative to the repo root).
    Fails closed: a missing, empty or malformed list stops the check instead of passing it."""
    file = path or get_settings().kyb_sanctions_file
    try:
        return _read_sanctions(str(file), file.stat().st_mtime_ns)
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        log.error("sanctions_list_unusable", error=type(exc).__name__)
        raise ServiceUnavailable("the sanctions list is unavailable; KYB cannot run") from exc


def thresholds() -> engine.Thresholds:
    s = get_settings()
    return engine.Thresholds(s.kyb_match_threshold, s.kyb_partial_threshold)


def mask_account(number: str) -> str:
    tail = "".join(c for c in number if c.isalnum())[-4:]
    return f"****{tail}"


def clean_name(value: str) -> str:
    """Document-derived text is data: drop control characters and cap the length."""
    return "".join(c for c in value if c.isprintable()).strip()[:NAME_MAX]


def find_supplier(db: Session, user: CurrentUser, ref: uuid.UUID | str) -> Party:
    """A supplier the caller may see: admin/judge any; a buyer only suppliers it has deals with.
    Anything else looks missing (no existence oracle)."""
    supplier: Party | None = None
    if isinstance(ref, uuid.UUID):
        supplier = db.get(Party, ref)
    else:
        with contextlib.suppress(ValueError):
            supplier = db.get(Party, uuid.UUID(ref))
        if supplier is None:
            supplier = db.scalar(select(Party).where(Party.code == ref))
    if supplier is None or supplier.kind != PartyKind.SUPPLIER:
        raise NotFound("supplier not found")
    if not user.reads_all:
        has_deal = db.scalar(
            select(func.count())
            .select_from(Deal)
            .where(Deal.supplier_id == supplier.id, Deal.buyer_id == user.party_id)
        )
        if user.party_id is None or not has_deal:
            raise NotFound("supplier not found")
    return supplier


def find_deal(db: Session, user: CurrentUser, supplier: Party, ref: str) -> Deal:
    cond = Deal.reference == ref
    with contextlib.suppress(ValueError):
        cond = cond | (Deal.id == uuid.UUID(ref))
    deal = db.scalars(select(Deal).where(cond)).first()
    if deal is None or deal.supplier_id != supplier.id or not can_read_party(user, deal.buyer_id):
        raise NotFound("deal not found")
    return deal


def invoice_name_for(
    db: Session, supplier: Party, deal: Deal | None, override: str | None
) -> tuple[str, str, list[str]]:
    """(name, source, flags): explicit override, else the seller on the deal's proforma invoice,
    else the supplier's legal name. Document text is untrusted: if the detector finds
    instruction-like text in it, the legal name is used and the finding codes are returned."""
    name, source = supplier.legal_name, "legal_name"
    if override and override.strip():
        name, source = clean_name(override), "override"
    elif deal is not None:
        docs = db.scalars(
            select(Document)
            .where(
                Document.deal_id == deal.id,
                Document.doc_type == DocType.PROFORMA_INVOICE,
                Document.extracted_json.is_not(None),
            )
            .order_by(Document.uploaded_at.desc().nulls_last(), Document.key)
        ).all()
        for doc in docs:
            seller = (doc.extracted_json or {}).get("seller")
            if isinstance(seller, str) and clean_name(seller):
                name, source = clean_name(seller), "proforma"
                break
    flags = sorted({f.code for f in detect_instructions(name)})
    if flags:
        return supplier.legal_name, "legal_name", flags
    return name, source, []


def history_facts(db: Session, supplier: Party) -> engine.HistoryFacts:
    deals = db.scalars(select(Deal).where(Deal.supplier_id == supplier.id)).all()
    not_started = (
        DealStatus.DRAFT,
        DealStatus.PROPOSED,
        DealStatus.CONFIRMED,
        DealStatus.CANCELLED,
    )
    counted = [d for d in deals if d.status not in not_started]
    previous = db.execute(
        select(KybRun.checked_at, KybRun.status)
        .where(KybRun.party_id == supplier.id)
        .order_by(KybRun.checked_at.desc())
        .limit(3)
    ).all()
    return engine.HistoryFacts(
        total_deals=len(counted),
        completed_deals=sum(d.status == DealStatus.COMPLETED for d in counted),
        disputed_deals=sum(d.status == DealStatus.DISPUTED or d.dispute_count > 0 for d in counted),
        previous=tuple((at.isoformat(), st) for at, st in previous),
    )


# --- evaluation (no writes) ---------------------------------------------------------------------


def account_summary(a: BankAccount, today: date) -> AccountSummary:
    return AccountSummary(
        account_id=a.id,
        bank_name=a.bank_name,
        masked_number=mask_account(a.account_number),
        holder_name=a.holder_name,
        account_type=a.account_type.value,  # type: ignore[arg-type]
        status=a.status.value,  # type: ignore[arg-type]
        currency=a.currency,
        bank_country=a.bank_country,
        first_seen_on=a.first_seen_on,
        age_days=(today - a.first_seen_on).days,
        verified=a.verified,
    )


def _facts(a: BankAccount) -> engine.AccountFacts:
    return engine.AccountFacts(
        holder_name=a.holder_name,
        account_type=a.account_type.value,
        first_seen_on=a.first_seen_on,
        bank_country=a.bank_country,
        currency=a.currency,
        pending=a.status == AccountStatus.PENDING_CHANGE,
        change_requested_via=a.change_requested_via,
    )


def _checks_out(a: engine.Assessment) -> dict[str, Any]:
    return {
        "status": a.status,
        "score": a.score,
        "checks": [
            KybCheckOut(
                code=c.code,
                status=c.status,
                weight=c.weight,
                detail_en=c.detail_en,
                detail_bn=c.detail_bn,
                evidence=c.evidence,
            )
            for c in a.checks
        ],
        "reason_codes": list(a.reason_codes),
        "explanation_en": a.explanation_en,
        "explanation_bn": a.explanation_bn,
    }


def active_account(accounts: list[BankAccount], deal: Deal | None) -> BankAccount | None:
    active = sorted(
        (a for a in accounts if a.status == AccountStatus.ACTIVE),
        key=lambda a: (a.first_seen_on, str(a.id)),
        reverse=True,
    )
    if deal is not None and deal.beneficiary_account_id is not None:
        for a in active:
            if a.id == deal.beneficiary_account_id:
                return a
    return active[0] if active else None


@dataclass(frozen=True, slots=True)
class Run:
    """One evaluation: the deal-specific `result`, plus the party/account-only assessments that
    persistent state (Party.kyb_status, BankAccount.verified, retirement) is based on."""

    result: KybResult
    base: engine.Assessment
    base_accounts: dict[uuid.UUID, engine.Assessment]
    invoice_flags: list[str]


def run_checks(
    db: Session,
    supplier: Party,
    *,
    deal: Deal | None = None,
    invoice_name: str | None = None,
    sanctions: tuple[engine.SanctionEntry, ...] | list[engine.SanctionEntry] | None = None,
    now: datetime | None = None,
) -> Run:
    today = demo_today(db)
    th = thresholds()
    listed = tuple(sanctions) if sanctions is not None else load_sanctions()
    name, source, flags = invoice_name_for(db, supplier, deal, invoice_name)
    party = engine.PartyFacts(supplier.legal_name, supplier.license_name, supplier.country)
    history = history_facts(db, supplier)
    accounts = list(
        db.scalars(
            select(BankAccount)
            .where(BankAccount.party_id == supplier.id)
            .order_by(BankAccount.first_seen_on, BankAccount.id)
        ).all()
    )

    def run(account: BankAccount | None, invoice: str | None) -> engine.Assessment:
        return engine.assess(
            party=party,
            invoice_name=invoice,
            account=_facts(account) if account else None,
            history=history,
            sanctions=listed,
            today=today,
            thresholds=th,
            invoice_flags=flags,
        )

    active = active_account(accounts, deal)
    pending_accounts = [a for a in accounts if a.status == AccountStatus.PENDING_CHANGE]
    base = run(active, None)
    base_accounts = {a.id: run(a, None) for a in pending_accounts}
    if active is not None:
        base_accounts[active.id] = base
    main = run(active, name)
    pending = [
        PendingAccountResult(**_checks_out(run(a, name)), account=account_summary(a, today))
        for a in pending_accounts
    ]
    result = KybResult(
        **_checks_out(main),
        supplier_id=supplier.id,
        supplier_code=supplier.code,
        supplier_name=supplier.legal_name,
        deal_ref=deal.reference if deal else None,
        invoice_name=name,
        invoice_name_source=source,  # type: ignore[arg-type]
        account=account_summary(active, today) if active else None,
        pending_accounts=pending,
        has_pending_change=bool(pending),
        checked_at=now or datetime.now(UTC),
        thresholds=KybThresholds(
            match=th.match,
            partial=th.partial,
            account_age_warn_days=engine.AGE_WARN_DAYS,
            account_age_fail_days=engine.AGE_FAIL_DAYS,
        ),
        persisted=False,
        route=f"/app/suppliers/{supplier.id}",
        party_status=base.status,  # type: ignore[arg-type]
        party_score=base.score,
        invoice_flags=flags,
    )
    return Run(result, base, base_accounts, flags)


def evaluate(db: Session, supplier: Party, **kw: Any) -> KybResult:
    """Run every check for the supplier's active account and each pending account. Read-only."""
    return run_checks(db, supplier, **kw).result


# --- verify (the writer) -----------------------------------------------------------------------


def _reasons(checks: Sequence[engine.Check]) -> list[dict[str, Any]]:
    return [
        {"code": c.code, "ok": c.status == "PASS", "status": c.status, "message": c.detail_en}
        for c in checks
    ]


def _store_check(
    db: Session,
    supplier: Party,
    account_id: uuid.UUID | None,
    a: engine.Assessment,
    at: datetime,
) -> None:
    row = db.scalars(
        select(KybCheck)
        .where(KybCheck.party_id == supplier.id, KybCheck.bank_account_id == account_id)
        .order_by(KybCheck.checked_at.desc())
    ).first()
    values: dict[str, Any] = {
        "status": PARTY_STATUS[a.status],
        "score": Decimal(a.score) / Decimal(100),
        "reasons": _reasons(a.checks),
        "checked_at": at,
    }
    if row is None:
        db.add(
            KybCheck(id=uuid.uuid4(), party_id=supplier.id, bank_account_id=account_id, **values)
        )
    else:
        for k, v in values.items():
            setattr(row, k, v)


def verify(
    db: Session,
    user: CurrentUser,
    supplier_id: uuid.UUID | str,
    deal_ref: str | None = None,
    *,
    invoice_name: str | None = None,
    sanctions: tuple[engine.SanctionEntry, ...] | list[engine.SanctionEntry] | None = None,
    now: datetime | None = None,
) -> KybResult:
    """Persisted state (Party.kyb_status, KybCheck, BankAccount.verified/status) comes only from
    party and account facts; the invoice-name result stays on this deal's KybRun and alert."""
    supplier = find_supplier(db, user, supplier_id)
    deal = find_deal(db, user, supplier, deal_ref) if deal_ref else None
    at = now or datetime.now(UTC)
    run = run_checks(
        db, supplier, deal=deal, invoice_name=invoice_name, sanctions=sanctions, now=at
    )
    result = run.result.model_copy(update={"persisted": True})

    supplier.kyb_status = PARTY_STATUS[run.base.status]
    active_id = result.account.account_id if result.account else None
    _store_check(db, supplier, active_id, run.base, at)
    retired: list[str] = []
    verified_changes: list[dict[str, Any]] = []
    for account_id, a in run.base_accounts.items():
        if account_id != active_id:
            _store_check(db, supplier, account_id, a, at)
        account = db.get(BankAccount, account_id)
        if account is None:
            continue
        verified = a.status == "VERIFIED"
        if account.verified != verified:
            verified_changes.append(
                {"account_id": str(account_id), "from": account.verified, "to": verified}
            )
            account.verified = verified
        # Retire only on a blocking sanctions hit against party, licence or holder names.
        if a.status == "BLOCKED" and account.status != AccountStatus.RETIRED:
            account.status = AccountStatus.RETIRED
            retired.append(str(account_id))

    deal_id = str(deal.id) if deal else None
    seq = write_audit(
        db,
        actor="user",
        action="KYB_CHECKED",
        tier=0,
        params={
            "supplier_id": str(supplier.id),
            "deal_id": deal_id,
            "requested_by": str(user.id),
            "status": result.status,
            "score": result.score,
            "party_status": run.base.status,
            "reasons": result.reason_codes,
            "pending_accounts": [str(p.account.account_id) for p in result.pending_accounts],
            "retired_account_ids": retired,
            "verified_changes": verified_changes,
        },
        result=result.status,
        ts=at,
        deal_id=deal.id if deal else None,
    )
    if run.invoice_flags:
        write_audit(
            db,
            actor="system",
            action="DOC_INSTRUCTION_DETECTED",
            tier=3,
            params={
                "supplier_id": str(supplier.id),
                "deal_id": deal_id,
                "source": "invoice_seller_name",
                "codes": run.invoice_flags,
            },
            result="FLAGGED",
            ts=at,
            deal_id=deal.id if deal else None,
        )
    db.add(
        KybRun(
            id=uuid.uuid4(),
            party_id=supplier.id,
            deal_id=deal.id if deal else None,
            requested_by=user.id,
            status=result.status,
            score=result.score,
            reason_codes=list(result.reason_codes),
            result=result.model_dump(mode="json"),
            audit_seq=seq,
            checked_at=at,
        )
    )
    alert_service.sync_kyb_alerts(
        db,
        supplier,
        base_status=run.base.status,
        base_score=run.base.score,
        base_reasons=run.base.reason_codes,
        deal=deal,
        deal_codes=[c for c in result.reason_codes if c not in run.base.reason_codes],
        scope=None if user.reads_all else {user.party_id} if user.party_id else set(),
    )
    db.commit()
    log.info("kyb_verified", supplier_id=str(supplier.id), status=result.status, audit_seq=seq)
    return result


def sync_all_alerts(db: Session) -> int:
    """Seed hook: evaluate every supplier (read-only, no audit row, no Party update) and sync the
    supplier-level KYB alerts. Returns created + updated + reopened + resolved."""
    total = 0
    for supplier in db.scalars(select(Party).where(Party.kind == PartyKind.SUPPLIER)).all():
        run = run_checks(db, supplier)
        counts = alert_service.sync_kyb_alerts(
            db,
            supplier,
            base_status=run.base.status,
            base_score=run.base.score,
            base_reasons=run.base.reason_codes,
            deal=None,
            deal_codes=[],
            scope=None,
        )
        total += sum(counts.values())
    return total


# --- reads -------------------------------------------------------------------------------------


def _readable_runs(user: CurrentUser, supplier: Party) -> Select[tuple[KybRun, str | None]]:
    """Runs the caller may see: all for admin/judge; for a buyer, no-deal runs and runs on its
    own deals (another buyer's run carries that deal's invoice name)."""
    stmt = (
        select(KybRun, Deal.reference)
        .outerjoin(Deal, Deal.id == KybRun.deal_id)
        .where(KybRun.party_id == supplier.id)
    )
    if not user.reads_all:
        stmt = stmt.where(or_(KybRun.deal_id.is_(None), Deal.buyer_id == user.party_id))
    return stmt.order_by(KybRun.checked_at.desc())


def history_items(db: Session, user: CurrentUser, supplier: Party) -> list[KybHistoryItem]:
    rows = db.execute(_readable_runs(user, supplier).limit(HISTORY_LIMIT)).all()
    return [
        KybHistoryItem(
            id=run.id,
            checked_at=run.checked_at,
            status=run.status,  # type: ignore[arg-type]
            score=run.score,
            reason_codes=list(run.reason_codes),
            deal_ref=ref,
        )
        for run, ref in rows
    ]


def latest_result(db: Session, user: CurrentUser, supplier: Party) -> tuple[KybResult, str]:
    """(result, 'stored'|'live'): the caller's own newest readable stored run, else a read-only
    live evaluation. Never another buyer's run."""
    for run, _ in db.execute(_readable_runs(user, supplier).limit(10)).all():
        try:
            return KybResult.model_validate(run.result), "stored"
        except ValueError:
            continue
    return evaluate(db, supplier), "live"


def status_of(db: Session, user: CurrentUser, supplier_id: uuid.UUID) -> KybStatusOut:
    supplier = find_supplier(db, user, supplier_id)
    latest, source = latest_result(db, user, supplier)
    return KybStatusOut(
        supplier_id=supplier.id,
        source=source,  # type: ignore[arg-type]
        latest=latest,
        history=history_items(db, user, supplier),
    )
