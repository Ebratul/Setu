"""Verify the demo seed against the key demo numbers, straight from the database.

    ./scripts/verify_seed            # re-seeds twice (idempotency check), then asserts every number
    ./scripts/verify_seed --no-reseed

Exit code 1 if any check fails.
"""

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.db.enums import ApprovalStatus, FlowDirection, FxKind, KybStatus, LedgerDirection
from app.db.models import (
    Alert,
    ApprovalRequest,
    AuditLog,
    CashflowItem,
    Deal,
    DealCost,
    Document,
    FinancingOption,
    FxRate,
    HashRegistry,
    KybCheck,
    LedgerEntry,
    Milestone,
    Party,
)
from app.db.session import batch_session
from app.domain.money import q2
from app.security.audit import AuditFields, SignedEntry, load_signing_key, verify_chain
from seed.cli import DEMO_TABLES, seed
from seed.common import default_ctx
from seed.deals import MAIN_DEAL
from seed.documents import PI_KEY
from seed.parties import HUAMENG, LENDER_A, RAHIMA

D = Decimal


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    expected: str
    actual: str
    ok: bool


def snapshot(session: Session) -> dict[str, tuple[int, str]]:
    out = {}
    for table in DEMO_TABLES:
        n, digest = session.execute(
            text(
                f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) "
                f"FROM {table} t"
            )
        ).one()
        out[table] = (n, digest)
    return out


def run_checks(session: Session) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, expected: object, actual: object, ok: bool | None = None) -> None:
        checks.append(
            Check(
                name,
                str(expected),
                str(actual),
                ok if ok is not None else str(expected) == str(actual),
            )
        )

    ctx = default_ctx()
    deal = session.scalars(select(Deal).where(Deal.reference == MAIN_DEAL)).one()
    costs = session.scalars(select(DealCost).where(DealCost.deal_id == deal.id)).all()
    landed = q2(deal.goods_value + sum((c.amount for c in costs), D(0)))
    add(f"{MAIN_DEAL} landed cost (USD)", "11200.00", landed)

    ms = session.scalars(
        select(Milestone).where(Milestone.deal_id == deal.id).order_by(Milestone.seq)
    ).all()
    add(
        "milestones 30/60/10 (USD)",
        "2880.00 / 5760.00 / 960.00",
        " / ".join(str(q2(m.amount)) for m in ms),
    )
    add(
        "milestones sum = goods value",
        "9600.00",
        q2(sum((m.amount for m in ms), D(0))),
        q2(sum((m.amount for m in ms), D(0))) == q2(deal.goods_value) == D("9600.00"),
    )

    margin = (deal.expected_sale_value - landed) / deal.expected_sale_value
    add(
        "gross margin ≈ 18%",
        "17.50% to 18.50%",
        f"{q2(margin * 100)}%",
        D("0.175") <= margin <= D("0.185"),
    )

    rahima = session.scalars(select(Party).where(Party.code == RAHIMA)).one()
    m2 = ms[1]
    flows = session.scalars(
        select(CashflowItem).where(
            CashflowItem.party_id == rahima.id,
            CashflowItem.is_projected.is_(True),
            CashflowItem.on_date >= ctx.today,
            CashflowItem.on_date < m2.due_on,
        )
    ).all()
    balance = q2(
        rahima.cash_balance
        + sum((f.amount if f.direction == FlowDirection.IN else -f.amount for f in flows), D(0))
    )
    add(f"Rahima balance on M2 date {m2.due_on}", "4200.00", balance)
    shortfall = q2(m2.amount - balance)
    add("Rahima shortfall at M2", "1560.00", shortfall)
    alert_amt = session.scalar(
        select(Alert.amount).where(
            Alert.type == "SHORTFALL", Alert.party_id == rahima.id, Alert.status == "OPEN"
        )
    )
    add("SHORTFALL alert amount", "1560.00", q2(alert_amt) if alert_amt is not None else None)

    huameng = session.scalars(select(Party).where(Party.code == HUAMENG)).one()
    reasons = session.scalars(select(KybCheck.reasons).where(KybCheck.party_id == huameng.id)).all()
    personal = any(r["code"] == "PERSONAL_ACCOUNT" and not r["ok"] for rs in reasons for r in rs)
    add("Huameng KYB status", KybStatus.WARNING.value, huameng.kyb_status.value)
    add("Huameng personal-account reason", True, personal)

    active = session.scalar(
        select(func.count()).select_from(FinancingOption).where(FinancingOption.active.is_(True))
    )
    add("active financing options", "≥ 5", active, (active or 0) >= 5)

    rows = session.execute(
        select(FxRate.base, FxRate.quote, func.count())
        .where(FxRate.kind == FxKind.HISTORY)
        .group_by(FxRate.base, FxRate.quote)
    ).all()
    per_pair = {f"{b}/{q}": n for b, q, n in rows}
    add(
        "FX history days per pair",
        "≥ 90 per pair (3 pairs)",
        per_pair,
        len(per_pair) == 3 and all(n >= 90 for n in per_pair.values()),
    )

    pending = session.execute(
        select(ApprovalRequest.tier, func.count())
        .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        .group_by(ApprovalRequest.tier)
    ).all()
    by_tier = dict(pending)
    add("pending Tier 2 approvals", 1, by_tier.get(2, 0))
    add("pending Tier 3 approvals", 1, by_tier.get(3, 0))
    t3 = session.scalars(select(ApprovalRequest).where(ApprovalRequest.tier == 3)).first()
    add(
        "Tier 3 has OTP + cooling-off",
        True,
        bool(t3 and t3.otp_required and t3.cooling_off_until is not None),
    )

    pi_sha = session.scalar(select(Document.sha256).where(Document.key == PI_KEY))
    lender_a = session.scalar(select(Party.id).where(Party.code == LENDER_A))
    hit = session.scalar(
        select(func.count())
        .select_from(HashRegistry)
        .where(HashRegistry.sha256 == pi_sha, HashRegistry.lender_party_id == lender_a)
    )
    add("PI hash pre-registered at Lender A", 1, hit)

    unbalanced = session.execute(
        select(LedgerEntry.txn_ref)
        .group_by(LedgerEntry.txn_ref)
        .having(
            func.sum(
                case(
                    (LedgerEntry.direction == LedgerDirection.DEBIT, LedgerEntry.amount),
                    else_=-LedgerEntry.amount,
                )
            )
            != 0
        )
    ).all()
    add("ledger transactions balanced", 0, len(unbalanced))

    entries = [
        SignedEntry(
            AuditFields(
                a.seq, a.ts, a.actor.value, a.action, a.tier, a.params_hash, a.result, a.prev_hash
            ),
            a.entry_hash,
            a.signature,
            a.key_id,
        )
        for a in session.scalars(select(AuditLog).order_by(AuditLog.seq))
    ]
    problems = verify_chain(load_signing_key().public_key(), entries)
    add(
        f"audit chain valid ({len(entries)} entries)",
        "no problems",
        "; ".join(problems[:3]) or "no problems",
    )
    return checks


def print_table(checks: list[Check]) -> None:
    w1 = max(len(c.name) for c in checks)
    w2 = max(len(c.expected) for c in checks)
    w3 = max(len(c.actual) for c in checks)
    line = f"+-{'-' * w1}-+-{'-' * w2}-+-{'-' * w3}-+------+"
    print(line)
    print(f"| {'Check':<{w1}} | {'Expected':<{w2}} | {'Actual':<{w3}} | Pass |")
    print(line)
    for c in checks:
        verdict = "yes" if c.ok else "NO"
        print(f"| {c.name:<{w1}} | {c.expected:<{w2}} | {c.actual:<{w3}} | {verdict:<4} |")
    print(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_seed")
    parser.add_argument("--no-reseed", action="store_true", help="skip the double-seed check")
    args = parser.parse_args(argv)

    checks: list[Check] = []
    if not args.no_reseed:
        seed()
        with batch_session() as s:
            first = snapshot(s)
        seed()
        with batch_session() as s:
            second = snapshot(s)
        changed = [t for t in DEMO_TABLES if first[t] != second[t]]
        total = sum(n for n, _ in second.values())
        checks.append(
            Check(
                "db:seed twice → same rows & content",
                "0 tables changed",
                f"{len(changed)} changed ({total} rows)",
                not changed,
            )
        )
    with batch_session() as s:
        checks += run_checks(s)

    print(f"Setu seed verification · DEMO_TODAY={default_ctx().today} · simulated data")
    print_table(checks)
    failed = [c for c in checks if not c.ok]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
