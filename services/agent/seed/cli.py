"""Seed entry point.

    pnpm run db:seed        # idempotent upsert of all demo data
    pnpm run db:reset-demo  # wipe demo rows, then seed
    (= uv run --directory services/agent python -m seed.cli seed|reset-demo)

All companies, people, accounts and amounts are fictional (simulated data).
"""

import argparse
import sys
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.enums import PartyKind
from app.db.models import DemoState, Party
from app.db.session import batch_session, database_url, is_local_url
from seed import (
    alerts_approvals,
    audit,
    cashflow,
    chat,
    deals,
    documents,
    financing,
    fx,
    parties,
    scores,
    users,
)
from seed.common import Ctx, Rows, default_ctx

# FK-safe order. Each module returns pure rows; only this file talks to the database.
MODULES: tuple[Callable[[Ctx], Rows], ...] = (
    parties.build,
    users.build,
    deals.build,
    scores.build,
    cashflow.build,
    fx.build,
    financing.build,
    documents.build,
    alerts_approvals.build,
    audit.build,
    chat.build,
)

# Everything the demo owns. kb_chunks and llm_cache are not demo data and survive a reset.
DEMO_TABLES = (
    "chat_messages",
    "chat_threads",
    "audit_log",
    "alerts",
    "financing_applications",
    "approval_requests",
    "hash_registry",
    "forensic_findings",
    "documents",
    "fx_locks",
    "fx_rates",
    "financing_options",
    "cashflow_items",
    "credit_records",
    "supplier_scores",
    "ledger_entries",
    "escrow_accounts",
    "milestones",
    "deal_costs",
    "deals",
    "kyb_checks",
    "users",
    "bank_accounts",
    "parties",
    "demo_state",
)
BATCH = 500
# Append-only / human-decided rows: re-seeding never rewrites them (only reset-demo does).
INSERT_ONLY = frozenset({"audit_log", "approval_requests"})


class SeedError(RuntimeError):
    pass


def build_all(ctx: Ctx) -> Rows:
    rows: Rows = []
    for build in MODULES:
        rows += build(ctx)
    rows.append((DemoState, [{"id": 1, "step": 0, "anchor_date": ctx.today}]))
    return rows


def upsert(session: Session, rows: Rows) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model, items in rows:
        table = model.__table__
        pk = [c.name for c in table.primary_key.columns]
        for start in range(0, len(items), BATCH):
            chunk = items[start : start + BATCH]
            stmt = insert(model).values(chunk)
            if table.name in INSERT_ONLY:
                stmt = stmt.on_conflict_do_nothing(index_elements=pk)
            else:
                cols = [c for c in chunk[0] if c not in pk]
                stmt = stmt.on_conflict_do_update(
                    index_elements=pk, set_={c: stmt.excluded[c] for c in cols}
                )
            session.execute(stmt)
        counts[table.name] = counts.get(table.name, 0) + len(items)
    return counts


def wipe(session: Session) -> None:
    session.execute(text(f"TRUNCATE TABLE {', '.join(DEMO_TABLES)} CASCADE"))


def seed(
    ctx: Ctx | None = None, *, reset: bool = False, allow_remote: bool = False
) -> dict[str, int]:
    """Upsert all demo rows. `reset` wipes demo tables first; on a non-local database that also
    needs `allow_remote` (it truncates the audit log)."""
    if reset and not allow_remote and not is_local_url(database_url()):
        raise SeedError("refusing to wipe a non-local database; pass --allow-remote")
    ctx = ctx or default_ctx()
    rows = build_all(ctx)
    with batch_session() as session:
        stored = session.scalar(select(DemoState.anchor_date).where(DemoState.id == 1))
        if not reset and stored is not None and stored != ctx.today:
            raise SeedError(
                f"DEMO_TODAY changed ({stored} -> {ctx.today}); run `pnpm run db:reset-demo`"
            )
        if reset:
            wipe(session)
        counts = upsert(session, rows)
        counts["alerts (engine)"] = recompute_alerts(session)
        return counts


def recompute_alerts(session: Session) -> int:
    """Run the FR-2 alert engine for every buyer so the demo opens with live alerts."""
    from app.services.alerts import recompute_book
    from app.services.cashflow import load_book

    total = 0
    for buyer in session.scalars(select(Party).where(Party.kind == PartyKind.BUYER)).all():
        out = recompute_book(session, load_book(session, buyer))
        total += out.created + out.updated + out.reopened
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed", description="Setu demo seed (simulated data)")
    parser.add_argument("command", choices=["seed", "reset-demo"])
    parser.add_argument(
        "--allow-remote", action="store_true", help="allow reset-demo on a non-local database"
    )
    args = parser.parse_args(argv)
    ctx = default_ctx()
    try:
        counts = seed(ctx, reset=args.command == "reset-demo", allow_remote=args.allow_remote)
    except SeedError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 2
    print(f"{args.command}: DEMO_TODAY={ctx.today} · {sum(counts.values())} rows upserted")
    for name, n in counts.items():
        print(f"  {name:<20} {n:>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
