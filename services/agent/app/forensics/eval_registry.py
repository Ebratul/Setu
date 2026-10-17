"""Dev-split catch rate of the hash registry on the synthetic DUPLICATE_INVOICE packs.

Each duplicate's source pack is registered as financing collateral at Lender A in a scratch
transaction; the duplicate's commercial invoice is then checked as Lender B would (no deal). A
byte-identical copy must be EXACT_DUPLICATE, a re-saved copy (other bytes, same invoice identity)
NEAR_DUPLICATE. Nothing is committed. Run: `uv run python -m app.forensics.eval_registry`."""

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DocType, RegistryPurpose
from app.db.models import Party
from app.forensics.analyze import analyze_pdf
from app.forensics.pack_loader import GENERATED, manifest
from app.services import hash_registry as hr

LENDER_A, LENDER_B = "meghna-commercial-bank", "setu-partner-finance"


def _subject(data: bytes) -> hr.Subject:
    view = analyze_pdf(data, "COMMERCIAL_INVOICE").view
    f = view.fields
    semantic = None
    if f is not None and f.invoice_no and f.seller and f.total is not None:  # type: ignore[union-attr]
        semantic = hr.invoice_semantic(
            f.seller,  # type: ignore[union-attr]
            f.invoice_no,  # type: ignore[union-attr]
            str(f.total),  # type: ignore[union-attr]
            getattr(f, "currency", None) or "USD",
        )
    return hr.Subject(hashlib.sha256(data).hexdigest(), DocType.COMMERCIAL_INVOICE, semantic)


def _ci(entry: dict[str, Any], root: Path) -> bytes:
    doc = next(d for d in entry["documents"] if d["type"] == "COMMERCIAL_INVOICE")
    return (root / doc["path"]).read_bytes()


def run(db: Session, root: Path = GENERATED, split: str = "dev") -> dict[str, Any]:
    entries = {e["pack_id"]: e for e in manifest(root)}
    lender_a = db.scalar(select(Party.id).where(Party.code == LENDER_A))
    lender_b = db.scalar(select(Party.id).where(Party.code == LENDER_B))
    assert lender_a and lender_b, "seed the lenders first"
    stats: dict[str, list[bool]] = defaultdict(list)
    missed: list[str] = []
    registered: set[str] = set()
    try:
        for e in entries.values():
            if e["split"] != split or not e.get("duplicate_of"):
                continue
            src = entries[e["duplicate_of"]]
            if src["pack_id"] not in registered:
                hr.register(
                    db,
                    _subject(_ci(src, root)),
                    hr.Context(RegistryPurpose.FINANCING_COLLATERAL, lender_id=lender_a),
                    external_ref=src["pack_id"],
                )
                registered.add(src["pack_id"])
            dup, orig = _subject(_ci(e, root)), _subject(_ci(src, root))
            kind = "exact" if dup.sha256 == orig.sha256 else "near"
            want = hr.EXACT_DUPLICATE if kind == "exact" else hr.NEAR_DUPLICATE
            got = hr.evaluate(
                db, dup, hr.Context(RegistryPurpose.FINANCING_COLLATERAL, lender_id=lender_b)
            ).result
            stats[kind].append(got == want)
            stats["any"].append(got in hr.DUPLICATES)
            if got not in hr.DUPLICATES:
                missed.append(e["pack_id"])
    finally:
        db.rollback()
    return {"stats": stats, "missed": missed}


def render(r: dict[str, Any]) -> str:
    rows = ["| variant | packs | classified correctly |", "|---|---|---|"]
    for k in ("exact", "near", "any"):
        v = r["stats"].get(k, [])
        label = {
            "exact": "byte-identical (EXACT)",
            "near": "re-saved (NEAR)",
            "any": "caught either way",
        }[k]
        rows.append(
            f"| {label} | {len(v)} | {sum(v)} ({sum(v) / len(v):.0%}) |"
            if v
            else f"| {label} | 0 | n/a |"
        )
    if r["missed"]:
        rows.append(f"\nmissed: {', '.join(r['missed'])}")
    return "\n".join(rows)


if __name__ == "__main__":
    from app.db.session import batch_session

    with batch_session() as session:
        print(render(run(session)))
