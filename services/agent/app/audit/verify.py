"""Verify an audit chain with nothing but the public key.

    python -m app.audit.verify --file operation-log.jsonl \\
        --pubkey docs/submission/audit-public-key.pem
    python -m app.audit.verify --from 10 --to 40    # the database, signing key's public half

Reports OK or the first broken seq and why. The browser verifier (apps/web/src/lib/audit/verify.ts)
follows the same rules and must give the same answer.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.audit.keys import PUBLIC_KEY_PATH, fingerprint, load_public_pem, verify_signature
from app.audit.scheme import (
    BODY_FIELDS,
    GENESIS_HASH,
    LINE_FIELDS,
    SCHEME,
    body_of,
    compute_entry_hash,
    compute_payload_hash,
)

HASH_MISMATCH = "hash_mismatch"
BAD_SIGNATURE = "bad_signature"
MISSING_SEQ = "missing_seq"
REORDERED = "reordered"
BROKEN_LINK = "broken_link"
MALFORMED = "malformed"


@dataclass(slots=True)
class Report:
    ok: bool
    entries_checked: int
    first_seq: int | None
    last_seq: int | None
    broken_seq: int | None = None
    reason: str | None = None
    detail: str | None = None
    anchored: bool = False  # the first entry is seq 1 and links to the genesis hash
    contiguous: bool = True
    missing_seqs: int = 0  # gaps tolerated in a partial export: completeness is NOT proven
    scheme: str = SCHEME
    public_key_fingerprint: str = ""
    problems: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_hex(value: Any, n: int) -> bool:
    return (
        isinstance(value, str) and len(value) == n and all(c in "0123456789abcdef" for c in value)
    )


def _well_formed(line: dict[str, Any]) -> str | None:
    missing = [f for f in LINE_FIELDS if f not in line]
    if missing:
        return f"missing field {missing[0]}"
    if not isinstance(line["seq"], int) or isinstance(line["seq"], bool):
        return "seq is not an integer"
    if not isinstance(line["ts"], str) or not isinstance(line["payload"], dict):
        return "ts or payload has the wrong type"
    for f in ("payload_hash", "prev_hash", "entry_hash"):
        if not _is_hex(line[f], 64):
            return f"{f} is not a sha256 hex digest"
    if not _is_hex(line["signature"], 128):
        return "signature is not 64 bytes of hex"
    return None


def verify_lines(
    lines: Sequence[dict[str, Any]],
    public_key: Ed25519PublicKey,
    *,
    contiguous: bool = True,
    anchor_prev_hash: str | None = None,
) -> Report:
    """Check order, continuity, every hash and every signature. `contiguous=False` is for
    filtered exports (one deal): seq gaps are then expected and only direct neighbours link.
    `anchor_prev_hash` is the trusted entry_hash just before the first line (range checks)."""
    report = Report(
        ok=True,
        entries_checked=0,
        first_seq=lines[0].get("seq") if lines else None,
        last_seq=lines[-1].get("seq") if lines else None,
        contiguous=contiguous,
        public_key_fingerprint=fingerprint(public_key),
    )

    def fail(seq: int | None, reason: str, detail: str) -> Report:
        report.ok = False
        report.broken_seq = seq
        report.reason = reason
        report.detail = detail
        return report

    prev: dict[str, Any] | None = None
    later = {ln.get("seq") for ln in lines}
    for index, line in enumerate(lines):
        bad = _well_formed(line)
        if bad:
            return fail(
                line.get("seq") if isinstance(line.get("seq"), int) else None, MALFORMED, bad
            )
        seq = line["seq"]
        if prev is not None:
            expected = prev["seq"] + 1
            if contiguous and seq != expected:
                if expected in later:
                    return fail(
                        expected, REORDERED, f"seq {seq} appears where seq {expected} belongs"
                    )
                return fail(expected, MISSING_SEQ, f"seq {expected} is missing (found {seq})")
            if seq <= prev["seq"]:
                return fail(seq, REORDERED, f"seq {seq} follows seq {prev['seq']}")
        try:
            recomputed = compute_payload_hash(body_of(line))
        except (TypeError, ValueError):
            return fail(seq, MALFORMED, "entry holds a value the scheme cannot canonicalise")
        if recomputed != line["payload_hash"]:
            return fail(seq, HASH_MISMATCH, "payload_hash does not match the entry contents")
        entry_hash = compute_entry_hash(line["prev_hash"], line["payload_hash"], seq, line["ts"])
        if entry_hash != line["entry_hash"]:
            return fail(seq, HASH_MISMATCH, "entry_hash does not match prev_hash, payload, seq, ts")
        if not verify_signature(public_key, line["entry_hash"], line["signature"]):
            return fail(seq, BAD_SIGNATURE, "Ed25519 signature does not verify against the key")
        if prev is not None and seq == prev["seq"] + 1 and line["prev_hash"] != prev["entry_hash"]:
            return fail(seq, BROKEN_LINK, f"prev_hash does not equal entry_hash of seq {seq - 1}")
        if index == 0:
            if seq == 1:
                if line["prev_hash"] != GENESIS_HASH:
                    return fail(seq, BROKEN_LINK, "seq 1 must link to the genesis hash")
                report.anchored = True
            elif anchor_prev_hash is not None and line["prev_hash"] != anchor_prev_hash:
                return fail(
                    seq, BROKEN_LINK, f"prev_hash does not equal entry_hash of seq {seq - 1}"
                )
        prev = line
        report.entries_checked += 1
    if not contiguous:
        report.anchored = False
        if report.entries_checked:
            report.missing_seqs = (lines[-1]["seq"] - lines[0]["seq"] + 1) - report.entries_checked
    return report


def read_export(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(header, entries) of a JSONL export. A bare list of entries (no header) is accepted."""
    header: dict[str, Any] | None = None
    entries: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {number} is not JSON: {exc.msg}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"line {number} is not a JSON object")
        if "seq" not in obj and "scheme" in obj and header is None and not entries:
            header = obj
        else:
            entries.append(obj)
    return header, entries


def describe(report: Report) -> str:
    if report.ok:
        span = f"seq {report.first_seq}..{report.last_seq}" if report.entries_checked else "empty"
        note = "" if report.anchored else " (not anchored at genesis)"
        if report.missing_seqs:
            note = (
                f" (PARTIAL: {report.missing_seqs} seqs absent; a partial export cannot prove"
                " nothing was left out)"
            )
        return f"OK: {report.entries_checked} entries verified, {span}{note}"
    return f"BROKEN at seq {report.broken_seq}: {report.reason}: {report.detail}"


def _db_lines(lo: int | None, hi: int | None) -> tuple[list[dict[str, Any]], str | None]:
    from sqlalchemy import select

    from app.audit.export import line_of
    from app.db import session as db_session
    from app.db.models import AuditLog

    with db_session.batch_session() as db:
        stmt = select(AuditLog).order_by(AuditLog.seq)
        if lo is not None:
            stmt = stmt.where(AuditLog.seq >= lo)
        if hi is not None:
            stmt = stmt.where(AuditLog.seq <= hi)
        rows = [line_of(r) for r in db.scalars(stmt)]
        anchor = None
        if rows and rows[0]["seq"] > 1:
            anchor = db.scalar(
                select(AuditLog.entry_hash).where(AuditLog.seq == rows[0]["seq"] - 1)
            )
    return rows, anchor


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.audit.verify", description=__doc__)
    parser.add_argument("--file", type=Path, help="JSONL export (default: the database)")
    parser.add_argument("--pubkey", type=Path, default=PUBLIC_KEY_PATH, help="Ed25519 public PEM")
    parser.add_argument("--from", dest="lo", type=int)
    parser.add_argument("--to", dest="hi", type=int)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        public_key = load_public_pem(args.pubkey)
    except (OSError, ValueError) as exc:
        print(f"cannot read public key {args.pubkey}: {exc}", file=sys.stderr)
        return 2
    anchor: str | None = None
    contiguous = True
    if args.file:
        try:
            header, lines = read_export(args.file)
        except (OSError, ValueError) as exc:
            print(f"cannot read {args.file}: {exc}", file=sys.stderr)
            return 2
        if header is not None:
            contiguous = bool(header.get("contiguous", True))
        lines = [
            ln
            for ln in lines
            if (args.lo is None or ln.get("seq", 0) >= args.lo)
            and (args.hi is None or ln.get("seq", 0) <= args.hi)
        ]
    else:
        lines, anchor = _db_lines(args.lo, args.hi)
    report = verify_lines(lines, public_key, contiguous=contiguous, anchor_prev_hash=anchor)
    print(json.dumps(report.as_dict(), indent=2) if args.json else describe(report))
    return 0 if report.ok else 1


__all__ = ["BODY_FIELDS", "Report", "describe", "main", "read_export", "verify_lines"]

if __name__ == "__main__":
    raise SystemExit(main())
