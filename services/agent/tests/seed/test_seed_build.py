"""Pure tests of the seed builders (no database)."""

from datetime import date
from decimal import Decimal

import pytest

from app.db.enums import FxKind
from seed import cashflow, fx
from seed.alerts_approvals import approvals, shortfall_facts
from seed.cli import build_all
from seed.common import Ctx
from seed.deals import DEALS, DEALS_BY_REF, MAIN_DEAL
from seed.documents import build as build_documents
from seed.parties import kyb_rows

ANCHORS = [date(2026, 10, 20), date(2027, 2, 14), date(2026, 12, 31)]


@pytest.fixture
def ctx() -> Ctx:
    return Ctx(today=date(2026, 10, 20))


def test_main_deal_numbers_reconcile() -> None:
    main = DEALS_BY_REF[MAIN_DEAL]
    assert main.goods_value.amount == Decimal("9600.00")
    assert [m.amount for m in main.milestone_amounts()] == [
        Decimal("2880.00"),
        Decimal("5760.00"),
        Decimal("960.00"),
    ]
    assert main.landed_cost().amount == Decimal("11200.00")
    margin = (main.expected_sale - main.landed_cost().amount) / main.expected_sale
    assert Decimal("0.175") <= margin <= Decimal("0.185")


@pytest.mark.parametrize("today", ANCHORS)
def test_shortfall_holds_for_any_anchor(today: date) -> None:
    sf = shortfall_facts(Ctx(today=today))
    assert sf["balance"] == Decimal("4200.00")
    assert sf["due"] == Decimal("5760.00")
    assert sf["shortfall"] == Decimal("1560.00")


def test_build_is_deterministic(audit_key: None, ctx: Ctx) -> None:
    assert build_all(ctx) == build_all(ctx)


def test_ids_unique_and_money_never_float(audit_key: None, ctx: Ctx) -> None:
    for model, rows in build_all(ctx):
        pk = next(iter(model.__table__.primary_key.columns)).name
        ids = [r[pk] for r in rows]
        assert len(ids) == len(set(ids)), model.__tablename__
        for r in rows:
            assert not any(isinstance(v, float) for v in r.values()), model.__tablename__


def test_fx_history_and_good_cny_day(ctx: Ctx) -> None:
    series = fx.series(ctx)
    assert set(series) == {("USD", "BDT"), ("USD", "CNY"), ("CNY", "BDT")}
    for points in series.values():
        assert sum(1 for p in points if p.kind == FxKind.HISTORY) >= 90
    good = fx.good_cny_day(ctx)
    assert good.on == date(2026, 10, 22)
    assert good.change <= Decimal("-0.015")
    usd_bdt = [p.rate for p in series[("USD", "BDT")]]
    assert all(Decimal("115") < r < Decimal("130") for r in usd_bdt)


def test_cashflow_covers_90_days_and_flags_projection(ctx: Ctx) -> None:
    rows = cashflow.build_rows(ctx)
    projected = [r for r in rows if r["is_projected"]]
    assert max(r["on_date"] for r in projected) >= ctx.day(85)
    assert all(r["on_date"] >= ctx.today for r in projected)
    assert all(r["on_date"] < ctx.today for r in rows if not r["is_projected"])
    assert all(r["amount"] > 0 for r in rows)


def test_huameng_kyb_warning_has_personal_account_reason(ctx: Ctx) -> None:
    huameng = next(
        r
        for r in kyb_rows(ctx)
        if r["status"] == "WARNING" and any(x["code"] == "PERSONAL_ACCOUNT" for x in r["reasons"])
    )
    assert huameng["score"] < Decimal("0.5")


def test_one_pending_tier2_and_tier3(ctx: Ctx) -> None:
    rows = approvals(ctx)
    assert sorted(r["tier"] for r in rows) == [2, 3]
    t3 = next(r for r in rows if r["tier"] == 3)
    assert t3["otp_required"] is True
    assert (t3["cooling_off_until"] - t3["created_at"]).total_seconds() == 600


def test_registry_hash_matches_pi_document(ctx: Ctx) -> None:
    (_, docs), _, (_, registry) = build_documents(ctx)
    pi = next(d for d in docs if d["doc_type"] == "PROFORMA_INVOICE")
    assert registry[0]["sha256"] == pi["sha256"]
    assert registry[0]["canonical_hash"] == pi["canonical_hash"]


def test_all_deal_statuses_present() -> None:
    assert {d.status.value for d in DEALS} == {
        "DRAFT",
        "FUNDED",
        "IN_PRODUCTION",
        "SHIPPED",
        "COMPLETED",
        "DISPUTED",
        "CANCELLED",
    }
