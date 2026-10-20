"""Execution-evidence export: the sandbox operation log as JSONL (+ a readable summary).

    python -m app.audit.export [--deal ID] [--from N] [--to N] [--out-dir DIR]

Line 1 is a header, then one signed entry per line. Verify with
`python -m app.audit.verify --file <export> --pubkey docs/submission/audit-public-key.pem`
or drop the file on /verify (runs in the browser, uploads nothing).
"""

import argparse
import json
import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import select

from app.audit.keys import PUBLIC_KEY_PATH, fingerprint, load_public_pem, load_signing_key
from app.audit.scheme import GENESIS_HASH, SCHEME, canonical_json, fmt_ts
from app.audit.timeline import describe_entry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.db.models import AuditLog

HOW_TO_VERIFY = (
    "python -m app.audit.verify --file <this file> --pubkey docs/submission/audit-public-key.pem"
    " | or open /verify and drop this file (checked in your browser, nothing is uploaded)."
    " Rules: payload_hash = sha256(canonical JSON of the entry body); entry_hash = sha256(prev_hash"
    ' + "|" + payload_hash + "|" + seq + "|" + ts); signature = Ed25519 over the 32 bytes of'
    " entry_hash; seq 1 links to the genesis hash."
)


def line_of(row: "AuditLog") -> dict[str, Any]:
    return {
        "seq": row.seq,
        "ts": fmt_ts(row.ts),
        "actor_type": row.actor.value,
        "actor_id": row.actor_id,
        "deal_id": str(row.deal_id) if row.deal_id else None,
        "action": row.action,
        "tier": row.tier,
        "decision": row.decision,
        "payload": row.payload,
        "payload_hash": row.payload_hash,
        "prev_hash": row.prev_hash,
        "entry_hash": row.entry_hash,
        "signature": row.signature,
        "key_id": row.key_id,
    }


def fetch_rows(
    db: "Session",
    *,
    deal_id: uuid.UUID | None = None,
    lo: int | None = None,
    hi: int | None = None,
) -> list["AuditLog"]:
    from app.db.models import AuditLog

    stmt = select(AuditLog).order_by(AuditLog.seq)
    if deal_id is not None:
        stmt = stmt.where(AuditLog.deal_id == deal_id)
    if lo is not None:
        stmt = stmt.where(AuditLog.seq >= lo)
    if hi is not None:
        stmt = stmt.where(AuditLog.seq <= hi)
    return list(db.scalars(stmt))


def line_of_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Export line of a row dict as `build_chain` returns it."""
    return {
        "seq": row["seq"],
        "ts": fmt_ts(row["ts"]),
        "actor_type": row["actor"],
        "actor_id": row["actor_id"],
        "deal_id": str(row["deal_id"]) if row["deal_id"] else None,
        "action": row["action"],
        "tier": row["tier"],
        "decision": row["decision"],
        "payload": row["payload"],
        "payload_hash": row["payload_hash"],
        "prev_hash": row["prev_hash"],
        "entry_hash": row["entry_hash"],
        "signature": row["signature"],
        "key_id": row["key_id"],
    }


def make_header_for(
    lines: Sequence[dict[str, Any]], public_key: Ed25519PublicKey, *, contiguous: bool
) -> dict[str, Any]:
    return {
        "scheme": SCHEME,
        "genesis": GENESIS_HASH,
        "public_key_fingerprint": fingerprint(public_key),
        "generated_at": fmt_ts(datetime.now(UTC)),
        "entry_count": len(lines),
        "first_seq": lines[0]["seq"] if lines else None,
        "last_seq": lines[-1]["seq"] if lines else None,
        "contiguous": contiguous,
        "how_to_verify": HOW_TO_VERIFY,
    }


def make_header(lines: Sequence[dict[str, Any]], *, contiguous: bool) -> dict[str, Any]:
    return make_header_for(lines, load_signing_key().public_key(), contiguous=contiguous)


def export_lines(
    db: "Session",
    *,
    deal_id: uuid.UUID | None = None,
    lo: int | None = None,
    hi: int | None = None,
) -> Iterator[str]:
    """Header line then one entry per line, canonical JSON (one object per line)."""
    lines = [line_of(r) for r in fetch_rows(db, deal_id=deal_id, lo=lo, hi=hi)]
    contiguous = deal_id is None
    yield canonical_json(make_header(lines, contiguous=contiguous)) + "\n"
    for line in lines:
        yield canonical_json(line) + "\n"


def summary_markdown(lines: Sequence[dict[str, Any]], header: dict[str, Any]) -> str:
    """Per deal: actions, tiers, decisions, timestamps. Written for a competition judge."""
    out = [
        "# Setu sandbox operation log (simulated)",
        "",
        "Every row below is a signed, hash-chained entry from the audit log. No real money moved.",
        "",
        f"- Scheme: `{header['scheme']}`",
        f"- Public key fingerprint (sha256): `{header['public_key_fingerprint']}`",
        f"- Entries: {header['entry_count']} (seq {header['first_seq']} to {header['last_seq']})",
        f"- Generated: {header['generated_at']}",
        "",
        "Verify: `python -m app.audit.verify --file <operation-log.jsonl>"
        " --pubkey docs/submission/audit-public-key.pem`, or drop the JSONL on `/verify`.",
        "",
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for ln in lines:
        groups.setdefault(ln["deal_id"] or "(no deal)", []).append(ln)
    tiers = {0: 0, 1: 0, 2: 0, 3: 0}
    for ln in lines:
        tiers[ln["tier"]] = tiers.get(ln["tier"], 0) + 1
    out += [
        "## Totals by tier",
        "",
        "| Tier | Entries |",
        "|---|---|",
        *[f"| {t} | {n} |" for t, n in sorted(tiers.items())],
        "",
    ]
    for deal, rows in groups.items():
        out += [
            f"## Deal {deal}",
            "",
            "| Seq | Time (UTC) | Action | Tier | Decision | Actor | What happened |",
            "|---|---|---|---|---|---|---|",
        ]
        for ln in rows:
            text = describe_entry(ln["action"], ln["payload"], ln["decision"])["en"]
            out.append(
                f"| {ln['seq']} | {ln['ts'][:19]} | {ln['action']} | {ln['tier']} | "
                f"{ln['decision']} | {ln['actor_type']}:{ln['actor_id'][:8]} | "
                f"{text.replace('|', '/')} |"
            )
        out.append("")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    from app.db import session as db_session

    parser = argparse.ArgumentParser(prog="python -m app.audit.export", description=__doc__)
    parser.add_argument("--deal", type=uuid.UUID)
    parser.add_argument("--from", dest="lo", type=int)
    parser.add_argument("--to", dest="hi", type=int)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PUBLIC_KEY_PATH.parent / "execution-evidence",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    with db_session.batch_session() as db:
        text = "".join(export_lines(db, deal_id=args.deal, lo=args.lo, hi=args.hi))
    rows = [json.loads(s) for s in text.splitlines()]
    header, lines = rows[0], rows[1:]
    stamp = date.today().isoformat()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = args.out_dir / f"operation-log-{stamp}.jsonl"
    jsonl.write_text(text, encoding="utf-8")
    md = args.out_dir / f"operation-log-{stamp}.md"
    md.write_text(summary_markdown(lines, header), encoding="utf-8")
    print(f"wrote {jsonl} ({len(lines)} entries)")
    print(f"wrote {md}")
    if PUBLIC_KEY_PATH.exists():
        from app.audit.verify import describe, verify_lines

        report = verify_lines(
            lines, load_public_pem(PUBLIC_KEY_PATH), contiguous=bool(header["contiguous"])
        )
        print(describe(report))
        return 0 if report.ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
