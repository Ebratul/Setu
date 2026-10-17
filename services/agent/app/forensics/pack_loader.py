"""Synthetic packs (data/generated) as pure inputs: `deal.json` becomes a DealContext and the PDFs
and photos are analysed in memory. Used by the dev-split evaluation and its tests; the production
path builds the same objects from DB rows."""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT
from app.forensics.analyze import Analysis, analyze_pdf, analyze_photo
from app.forensics.context import DealContext, DocView, Pack, RegisteredAccount
from app.forensics.parse_fields import DateOrder

GENERATED = REPO_ROOT / "data" / "generated"


@dataclass(slots=True)
class LoadedPack:
    pack_id: str
    split: str
    expected: dict[str, str]
    fraud_types: list[str]
    difficulty: str | None
    ctx: DealContext
    pack: Pack
    sha256: dict[str, str] = field(default_factory=dict)
    canonical_key: str | None = None


def deal_context(deal: dict[str, Any]) -> DealContext:
    bank = deal["registered_bank"]
    lo, hi = deal["price_band"]
    return DealContext(
        reference=deal["order_ref"],
        supplier_license_name=deal["supplier_license_name"],
        registered_account=RegisteredAccount(
            bank["bank_name"], bank["holder_name"], bank["account_masked"]
        ),
        hs_code=deal["hs_code"],
        unit=deal["unit"],
        currency=deal.get("currency", "USD"),
        incoterm=deal["incoterm"],
        port_of_loading=deal["port_of_loading"],
        port_of_discharge=deal["port_of_discharge"],
        booked_vessel=deal["booked_vessel"],
        booked_voyage=deal["booked_voyage"],
        production_complete=_d(deal["production_complete"]),
        eta=_d(deal["eta"]),
        price_band=(Decimal(lo), Decimal(hi)),
    )


def _d(value: str):  # type: ignore[no-untyped-def]
    from datetime import date

    return date.fromisoformat(value)


def manifest(root: Path = GENERATED) -> Iterator[dict[str, Any]]:
    with (root / "manifest.jsonl").open() as fh:
        for line in fh:
            yield json.loads(line)


def canonical_key(view: DocView) -> str | None:
    f = view.fields
    if f is None or getattr(f, "invoice_no", None) is None:
        return None
    name = " ".join((getattr(f, "seller", "") or "").casefold().split())
    return f"{name}|{f.invoice_no}|{getattr(f, 'total', None)}|{getattr(f, 'currency', None)}"  # type: ignore[union-attr]


def load_pack(entry: dict[str, Any], root: Path = GENERATED) -> LoadedPack:
    deal = json.loads((root / entry["deal_path"]).read_text())
    analyses: dict[str, Analysis] = {}
    photos: list[DocView] = []
    shas: dict[str, str] = {}
    raw: dict[str, bytes] = {}
    for d in entry["documents"]:
        data = (root / d["path"]).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if d["type"] == "PRODUCTION_PHOTO":
            photos.append(analyze_photo(data, sha).view)
            continue
        raw[d["type"]] = data
        shas[d["type"]] = sha
        analyses[d["type"]] = analyze_pdf(data, d["type"])
    # day-first is only an assumption for dd/mm/yyyy: reuse a sibling's evidence when it has any
    hint: DateOrder | None = next(
        (
            a.parsed.date_order
            for a in analyses.values()
            if a.parsed is not None and not a.parsed.date_order_assumed
        ),
        None,
    )
    if hint is not None:
        for t, a in list(analyses.items()):
            if a.parsed is not None and a.parsed.date_order_assumed and hint != "DMY":
                analyses[t] = analyze_pdf(raw[t], t, date_order_hint=hint)
    pack = Pack(docs={t: a.view for t, a in analyses.items()}, photos=photos)
    for t, view in pack.docs.items():
        view.sha256 = shas[t]
    ci = pack.docs.get("COMMERCIAL_INVOICE")
    return LoadedPack(
        pack_id=entry["pack_id"],
        split=entry["split"],
        expected=entry["expected_checks"],
        fraud_types=entry["fraud_types"],
        difficulty=entry["difficulty"],
        ctx=deal_context(deal),
        pack=pack,
        sha256=shas,
        canonical_key=canonical_key(ci) if ci else None,
    )
