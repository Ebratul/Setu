"""Privacy evaluation hook for P24: masking ON vs OFF on the synthetic packs (and on a numeric
chat set when a database session is given).

Per document: identifiers that reach the model payload (ground truth from the document's own
parsed fields plus everything the detectors can still find), masked counts by type, and *utility*:
for every field the label parser reads, "the model copies the field from what it was sent" must
round-trip through the vault to the exact printed value. Dev split only unless told otherwise;
the test split is reserved for the final report. `uv run python -m app.privacy.eval`."""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.forensics.pack_loader import GENERATED, manifest
from app.forensics.parse_fields import parse_document
from app.privacy.detectors import NAME
from app.privacy.gateway import PrivacyGateway
from app.privacy.vault import TOKEN
from app.services.documents.extract_text import extract_text

COPY_FIELDS = ("bank_account", "bank_holder", "bank_swift", "invoice_no", "seller", "total")
IDENTIFIER_FIELDS = ("bank_account", "bank_holder", "bank_swift")
CHAT_CASES: list[tuple[str, list[str]]] = [
    ("Order SETU-2026-0001-এর landed cost কত?", ["11,200"]),
    ("What is my cash shortfall?", ["1,560"]),
    ("আমার supplier-এর account নম্বর 6222 0021 4455 7788-এ কি টাকা যাবে? cash shortfall কত?", ["1,560"]),
]


def _norm(s: str) -> str:
    return "".join(ch for ch in s if ch.isalnum()).casefold()


def _present(value: str, payload: str) -> bool:
    return _norm(value) in _norm(payload)


def mask_with_spans(gw: PrivacyGateway, text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Masked text plus (start, end, token) for each hit, in original coordinates."""
    hits = gw.hits(text)
    tokens = [gw.token_of(h, text) for h in hits] if gw.enabled else []
    out, pos = [], 0
    for h, t in zip(hits, tokens, strict=False):
        out.append(text[pos : h.start] + t)
        pos = h.end
    out.append(text[pos:])
    return "".join(out), [(h.start, h.end, t) for h, t in zip(hits, tokens, strict=False)]


def copy_roundtrip(gw: PrivacyGateway, text: str, value: str) -> bool | None:
    """Would a model that copies `value` from the masked text hand back exactly `value` after
    unmasking? None when the value is not printed verbatim in the text."""
    start = text.find(value)
    if start == -1:
        return None
    end = start + len(value)
    masked, spans = mask_with_spans(gw, text)
    pieces, pos = [], start
    for s, e, token in spans:
        if e <= start or s >= end:
            continue
        if s < start or e > end:  # a protected value straddles the field edge: the copy breaks
            return False
        pieces.append(text[pos:s] + token)
        pos = e
    pieces.append(text[pos:end])
    copied = "".join(pieces)
    return gw.unmask(copied) == value and copied in masked


def _gateway(enabled: bool, holder: str | None) -> PrivacyGateway:
    return PrivacyGateway(enabled=enabled, mask_amounts=True, known={NAME: {holder or ""}})


def run_documents(split: str = "dev", root: Path = GENERATED, limit: int | None = None) -> dict:
    result: dict[str, Any] = {
        mode: {
            "documents": 0,
            "ground_truth_identifiers": 0,
            "ground_truth_leaked": 0,
            "detected_leaked": 0,
            "masked_by_type": Counter(),
            "fields_checked": 0,
            "fields_ok": 0,
        }
        for mode in ("on", "off")
    }
    packs = [e for e in manifest(root) if e["split"] == split]
    for entry in packs[:limit]:
        deal = json.loads((root / entry["deal_path"]).read_text())
        holder = deal["registered_bank"]["holder_name"]
        for d in entry["documents"]:
            if not d["path"].endswith(".pdf"):
                continue
            pdf = extract_text((root / d["path"]).read_bytes(), "application/pdf")
            if pdf is None or not pdf.visible_text.strip():
                continue
            text = pdf.visible_text
            try:
                fields = parse_document(text, d["type"]).fields.model_dump()
            except ValueError:
                continue
            for mode, enabled in (("on", True), ("off", False)):
                gw = _gateway(enabled, holder)
                payload, _ = gw.protect_text(text, node="eval", sent=False)
                r = result[mode]
                r["documents"] += 1
                for f in IDENTIFIER_FIELDS:
                    if fields.get(f):
                        r["ground_truth_identifiers"] += 1
                        r["ground_truth_leaked"] += int(_present(str(fields[f]), payload))
                r["detected_leaked"] += gw.scan(payload) if enabled else len(gw.hits(payload))
                r["masked_by_type"].update(
                    t[1:-1].rsplit("_", 1)[0] for t in {m.group(0) for m in TOKEN.finditer(payload)}
                )
                for f in COPY_FIELDS:
                    if fields.get(f) is None:
                        continue
                    ok = copy_roundtrip(gw, text, str(fields[f]))
                    if ok is not None:
                        r["fields_checked"] += 1
                        r["fields_ok"] += int(ok)
    for mode in result:
        r = result[mode]
        r["masked_by_type"] = dict(sorted(r["masked_by_type"].items()))
        r["field_accuracy"] = (
            round(r["fields_ok"] / r["fields_checked"], 4) if r["fields_checked"] else None
        )
    return {"split": split, "packs": len(packs[:limit]), **result}


def run_chat(db: Session, email: str = "rahima@demo.setu") -> dict:
    """Numeric chat answers with masking on and off (mock model; real tools and seed data)."""
    from sqlalchemy import select

    from app.agent.runner import chat
    from app.auth.deps import to_current
    from app.config import get_settings
    from app.db.models import User
    from app.schemas.chat import ChatRequest

    user = to_current(db.scalars(select(User).where(User.email == email)).one())
    out: dict[str, Any] = {}
    settings = get_settings()
    original = settings.privacy_enabled
    try:
        for mode, enabled in (("on", True), ("off", False)):
            settings.privacy_enabled = enabled
            ok = 0
            for question, expected in CHAT_CASES:
                answer = chat(db, user, ChatRequest(message=question)).answer
                ok += int(all(e in answer for e in expected))
            out[mode] = {"cases": len(CHAT_CASES), "correct": ok}
    finally:
        settings.privacy_enabled = original
    return out


def run_privacy_eval(split: str = "dev", db: Session | None = None, **kw: Any) -> dict:
    result = run_documents(split, **kw)
    if db is not None:
        result["chat"] = run_chat(db)
    return result


def main(argv: list[str] | None = None) -> int:
    split = (argv or sys.argv[1:] or ["dev"])[0]
    print(json.dumps(run_privacy_eval(split), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
