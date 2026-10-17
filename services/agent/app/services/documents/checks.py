"""Step 3: cross-checks. Builds the pure inputs (deal context, one view per stored document) from
DB rows, runs `app.forensics.checks.run_checks` and stores one ForensicFinding per
(document, check_code). Pack-level checks run against whatever siblings exist; missing ones are
SKIPPED, and the pipeline re-runs the siblings when a new document arrives."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.enums import AccountStatus, CheckStatus, DocStatus, DocType, Severity
from app.db.models import BankAccount, Deal, Document, ForensicFinding, Party
from app.forensics.checks import PRICE_BANDS, Outcome, run_checks
from app.forensics.context import (
    DealContext,
    DocView,
    Pack,
    RegisteredAccount,
    Tolerances,
)
from app.forensics.fields import EXTRACTOR_VERSION, FIELD_MODELS
from app.forensics.names import GROUND_TRUTH, LABELS
from app.forensics.pdf_text import HiddenSpan
from app.services import hash_registry

FORENSICS_KEY = "_forensics"
STATUS_TO_DB = {
    "PASS": CheckStatus.PASSED,
    "WARN": CheckStatus.WARNING,
    "FAIL": CheckStatus.FAILED,
    "SKIPPED": CheckStatus.NOT_RUN,
}
STATUS_FROM_DB = {v: k for k, v in STATUS_TO_DB.items()} | {CheckStatus.PENDING: "SKIPPED"}
SEVERITY = {"PASS": Severity.INFO, "SKIPPED": Severity.INFO, "WARN": Severity.WARNING,
            "FAIL": Severity.CRITICAL}  # fmt: skip


def tolerances() -> Tolerances:
    s = get_settings()
    return Tolerances(
        quantity_pct=s.forensics_quantity_tolerance_pct,
        money=s.forensics_money_tolerance,
        min_transit_days=s.forensics_min_transit_days,
    )


def registered_account(db: Session, deal: Deal) -> BankAccount | None:
    """The supplier's ACTIVE receiving account: the deal's beneficiary if active, else newest."""
    if deal.beneficiary_account_id is not None:
        acct = db.get(BankAccount, deal.beneficiary_account_id)
        if acct is not None and acct.status == AccountStatus.ACTIVE:
            return acct
    return db.scalars(
        select(BankAccount)
        .where(BankAccount.party_id == deal.supplier_id, BankAccount.status == AccountStatus.ACTIVE)
        .order_by(BankAccount.first_seen_on.desc(), BankAccount.id)
    ).first()


def build_context(db: Session, deal: Deal) -> DealContext:
    supplier = db.get(Party, deal.supplier_id)
    acct = registered_account(db, deal)
    band = PRICE_BANDS.get(deal.hs_code)
    return DealContext(
        reference=deal.reference,
        supplier_license_name=(supplier.license_name or supplier.legal_name) if supplier else None,
        registered_account=(
            RegisteredAccount(acct.bank_name, acct.holder_name, acct.account_number)
            if acct
            else None
        ),
        hs_code=deal.hs_code,
        quantity=deal.quantity,
        unit=deal.unit,
        unit_price=deal.unit_price,
        goods_value=deal.goods_value,
        currency=deal.currency,
        incoterm=deal.incoterm,
        port_of_loading=deal.port_of_loading,
        port_of_discharge=deal.port_of_discharge,
        price_band=(band[0], band[1]) if band and band[2] == deal.currency else None,
    )


def view_from_row(doc: Document) -> DocView | None:
    """The stored extraction as a DocView, or None when it must be (re-)extracted."""
    ej = doc.extracted_json or {}
    meta = ej.get(FORENSICS_KEY)
    if not isinstance(meta, dict) or meta.get("extractor_version") != EXTRACTOR_VERSION:
        return None
    if doc.sha256 is None or meta.get("sha256") != doc.sha256:
        return None
    if doc.doc_type == DocType.PRODUCTION_PHOTO:
        colour = meta.get("photo_colour")
        return DocView(
            doc_type=doc.doc_type.value,
            is_pdf=False,
            sha256=doc.sha256,
            photo_colour=(
                (colour["name"], tuple(colour["rgb"]), int(colour["distance"]))  # type: ignore[arg-type]
                if colour
                else None
            ),
            warnings=list(meta.get("warnings", [])),
        )
    model = FIELD_MODELS.get(doc.doc_type.value)
    if model is None and doc.doc_type != DocType.OTHER:
        return None
    try:
        fields = (
            model.model_validate({k: v for k, v in ej.items() if k != FORENSICS_KEY})
            if model is not None
            else None
        )
        spans = [
            HiddenSpan(
                s["text"], s["page"], tuple(s["bbox"]), tuple(s["colour"]) if s["colour"] else None,
                s["size"], s["reason"], s.get("page_width", 0.0), s.get("page_height", 0.0),
            )  # type: ignore[arg-type]
            for s in meta.get("hidden_spans", [])
        ]  # fmt: skip
    except (ValueError, KeyError, TypeError):
        return None
    return DocView(
        doc_type=doc.doc_type.value,
        fields=fields,  # type: ignore[arg-type]
        llm_fields=list(meta.get("llm_fields", [])),
        hidden_spans=spans,
        is_pdf=meta.get("kind") != "image",
        instruction_codes={k: list(v) for k, v in meta.get("instruction_codes", {}).items()},
        metadata=dict(meta.get("metadata", {})),
        created=_dt(meta.get("created")),
        modified=_dt(meta.get("modified")),
        sha256=doc.sha256,
        missing=list(meta.get("missing", [])),
        warnings=list(meta.get("warnings", [])),
    )


def _dt(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def is_accepted(doc: Document) -> bool:
    """A buyer (or admin) accepted this proforma invoice as the reference."""
    return bool(((doc.extracted_json or {}).get(FORENSICS_KEY) or {}).get("accepted"))


def build_pack(rows: list[tuple[Document, DocView]]) -> Pack:
    """Latest document per type (photos: all). The PROFORMA_INVOICE slot is the pinned reference:
    the first PASSED or buyer-accepted proforma invoice by upload time, never the latest upload,
    so replacing a PI later cannot move the booking, dates or bank baseline."""
    ordered = sorted(
        rows, key=lambda r: (r[0].uploaded_at or datetime.min.replace(tzinfo=UTC), r[0].key)
    )
    pack = Pack()
    for doc, view in ordered:
        if doc.doc_type == DocType.PRODUCTION_PHOTO:
            pack.photos.append(view)
        elif doc.doc_type == DocType.PROFORMA_INVOICE:
            if pack.reference is None and (
                doc.check_status == CheckStatus.PASSED or is_accepted(doc)
            ):
                pack.reference = view
                pack.docs[doc.doc_type.value] = view
        elif doc.doc_type != DocType.OTHER:
            pack.docs[doc.doc_type.value] = view
    return pack


def with_reference_booking(ctx: DealContext, pack: Pack) -> DealContext:
    """Booking and key dates come from the pinned proforma invoice, once, for every check."""
    ref = pack.reference
    if ref is None or ref.fields is None:
        return ctx
    f = ref.fields
    return replace(
        ctx,
        booked_vessel=ctx.booked_vessel or getattr(f, "booked_vessel", None),
        booked_voyage=ctx.booked_voyage or getattr(f, "booked_voyage", None),
        production_complete=ctx.production_complete or getattr(f, "production_complete", None),
        eta=ctx.eta or getattr(f, "eta", None),
    )


def platform_duplicate(db: Session, doc: Document) -> dict[str, Any] | None:
    """The same invoice identity (seller, number, total, currency) already stored on ANOTHER deal
    of this platform. Cross-lender duplicates are the hash registry's job (Phase 15)."""
    if doc.canonical_hash is None:
        return None
    other = db.scalars(
        select(Document.id).where(
            Document.canonical_hash == doc.canonical_hash,
            Document.id != doc.id,
            Document.deal_id != doc.deal_id,
            Document.status == DocStatus.UPLOADED,
        )
    ).first()
    return {"scope": "platform"} if other is not None else None


def run_for_document(
    db: Session, doc: Document, view: DocView, pack: Pack, ctx: DealContext
) -> list[Outcome]:
    status, detail = "NEW", {}
    if doc.sha256:
        res = hash_registry.check(db, doc.sha256, doc.canonical_hash, doc.doc_type.value)
        status, detail = res.status, dict(res.detail)
        local = platform_duplicate(db, doc)
        if status == "NEW" and local:
            status, detail = "DUPLICATE", local
    s = get_settings()
    return run_checks(
        view,
        pack,
        ctx,
        tol=tolerances(),
        name_match_threshold=s.kyb_match_threshold,
        name_partial_threshold=s.kyb_partial_threshold,
        registry_status=status,
        registry_detail=detail,
    )


def store_findings(
    db: Session, doc: Document, outcomes: list[Outcome], now: datetime
) -> list[ForensicFinding]:
    """Replace the document's findings with this run's (UNIQUE(document_id, check_code))."""
    db.execute(delete(ForensicFinding).where(ForensicFinding.document_id == doc.id))
    rows = [
        ForensicFinding(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:finding:{doc.id}:{o.code}"),
            document_id=doc.id,
            check_code=o.code,
            status=STATUS_TO_DB[o.status],
            severity=SEVERITY[o.status],
            detail=_json(o.detail),
            checked_at=now,
        )
        for o in outcomes
    ]
    db.add_all(rows)
    db.flush()
    return rows


def _json(value: Any) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(value, default=str))


def label_of(code: str, lang: str = "en") -> str:
    en, bn = LABELS.get(code, (code, code))
    return bn if lang == "bn" else en


def ground_truth_of(code: str) -> str | None:
    return GROUND_TRUTH.get(code)
