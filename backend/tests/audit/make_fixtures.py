"""Write the browser-verifier fixtures: a small deterministic chain signed with a TEST key (never
the real audit key), a tampered copy per failure mode, and the Python verdict for each.

    uv run --directory backend python -m tests.audit.make_fixtures

The web unit test and the Playwright test must agree with `expected.json`.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.audit.export import line_of_dict, make_header_for
from app.audit.keys import public_pem
from app.audit.scheme import canonical_json
from app.audit.tamper import apply_tamper
from app.audit.verify import verify_lines
from app.audit.writer import PendingEntry, build_chain

OUT = Path(__file__).resolve().parents[3] / "frontend" / "e2e" / "fixtures" / "audit"
KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
T0 = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
DEAL = "5c0b8a52-0d3e-5f64-9c7f-3d2a4b1e6f10"

STEPS: list[tuple[str, int, str, dict[str, object]]] = [
    ("DEAL_CREATED", 0, "OK", {"deal_ref": "SETU-2026-0001"}),
    ("MILESTONES_CONFIRMED", 2, "OK", {"deal_ref": "SETU-2026-0001"}),
    (
        "ESCROW_FUNDED",
        1,
        "SIMULATED_OK",
        {"amount": "5760.00", "currency": "USD", "milestone_seq": 1},
    ),
    ("DOC_UPLOADED", 0, "UPLOADED", {"doc": "proforma_invoice.pdf"}),
    ("KYB_CHECKED", 0, "WARNING", {"supplier": "Huameng Trading", "score": "62"}),
    (
        "RISK_DECISION",
        2,
        "REQUIRE_APPROVAL",
        {"reason_codes": ["FX_RATE_LOCK"], "milestone_seq": 1},
    ),
    ("APPROVAL_REQUESTED", 2, "PENDING", {"milestone_seq": 1}),
    ("APPROVAL_APPROVED", 2, "APPROVED", {"milestone_seq": 1}),
    ("FX_LOCKED", 2, "LOCKED", {"rate": "7.1500", "pair": "USD/CNY"}),
    (
        "TRANCHE_RELEASED",
        2,
        "RELEASED",
        {"amount": "5760.00", "currency": "USD", "milestone_seq": 1},
    ),
    ("DOC_CHECK_FAILED", 3, "BLOCKED", {"doc": "bill_of_lading.pdf", "rule": "HIDDEN_TEXT"}),
    ("INJECTION_DETECTED", 3, "FLAGGED", {"source": "document", "rules": ["IGNORE_PREVIOUS"]}),
]


def build() -> list[dict[str, object]]:
    pending = [
        PendingEntry(
            ts=T0 + timedelta(minutes=7 * i),
            actor_type="system" if i % 2 else "user",
            actor_id="system" if i % 2 else "demo-buyer",
            deal_id=None if i == 0 else __import__("uuid").UUID(DEAL),
            action=action,
            tier=tier,
            decision=decision,
            payload=payload,  # type: ignore[arg-type]
        )
        for i, (action, tier, decision, payload) in enumerate(STEPS)
    ]
    return [line_of_dict(r) for r in build_chain(KEY, pending)]


def write_jsonl(path: Path, lines: list[dict[str, object]], *, contiguous: bool = True) -> None:
    header = make_header_for(lines, KEY.public_key(), contiguous=contiguous)
    header["generated_at"] = "2026-10-20T00:00:00.000000Z"
    path.write_text("".join(canonical_json(x) + "\n" for x in [header, *lines]), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    good = build()
    release = next(ln["seq"] for ln in good if ln["action"] == "TRANCHE_RELEASED")
    cases = {
        "good": good,
        "tampered-amount": apply_tamper(
            good,
            mode="edit",
            seq=int(release),
            field="amount",
            value="57600.00",  # type: ignore[arg-type]
        ),
        "tampered-missing": apply_tamper(good, mode="delete", seq=5),  # type: ignore[arg-type]
        "tampered-reordered": apply_tamper(good, mode="reorder", seq=3, other_seq=4),  # type: ignore[arg-type]
    }
    expected: dict[str, object] = {"release_seq": release}
    for name, lines in cases.items():
        write_jsonl(OUT / f"{name}.jsonl", lines)  # type: ignore[arg-type]
        report = verify_lines(lines, KEY.public_key())  # type: ignore[arg-type]
        expected[name] = {
            "ok": report.ok,
            "broken_seq": report.broken_seq,
            "reason": report.reason,
            "entries_checked": report.entries_checked,
        }
    (OUT / "test-public-key.pem").write_text(public_pem(KEY.public_key()))
    (OUT / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
