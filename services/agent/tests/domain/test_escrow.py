"""FR-5 pure escrow rules: split, schedule validation, state machines, postings, FX, invariant."""

from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.db.enums import DealStatus as DS
from app.db.enums import DocType, LedgerDirection, MilestoneTrigger
from app.db.enums import MilestoneStatus as MS
from app.domain import escrow as rules
from app.domain.fx import FxQuote, FxTable
from app.domain.money import D, Money, q2
from app.errors import Conflict

T = rules.TEMPLATES[rules.TEMPLATE_30_60_10]


def amounts(total: str, percents: tuple[Decimal, ...] = T) -> list[Decimal]:
    return [p.amount.amount for p in rules.plan_milestones(Money.of(total, "USD"), percents)]


def test_golden_split_30_60_10() -> None:
    assert amounts("9600.00") == [D("2880.00"), D("5760.00"), D("960.00")]


def test_template_evidence_and_triggers() -> None:
    m1, m2, m3 = rules.plan_milestones(Money.of("9600.00", "USD"), T)
    assert [m.trigger for m in (m1, m2, m3)] == [
        MilestoneTrigger.PRODUCTION_START,
        MilestoneTrigger.SHIPMENT,
        MilestoneTrigger.ARRIVAL,
    ]
    assert m1.required_evidence == (DocType.PROFORMA_INVOICE, DocType.PRODUCTION_PHOTO)
    assert m2.required_evidence == (
        DocType.BILL_OF_LADING,
        DocType.PACKING_LIST,
        DocType.COMMERCIAL_INVOICE,
    )
    assert m3.required_evidence == (DocType.BILL_OF_ENTRY,)
    assert all(m.condition_text for m in (m1, m2, m3))
    assert [m.percent for m in (m1, m2, m3)] == [D("0.3"), D("0.6"), D("0.1")]
    assert [m.due_offset_days for m in (m1, m2, m3)] == [7, 35, 60]


@pytest.mark.parametrize("count", [2, 3, 4, 5])
def test_custom_schedule_positions(count: int) -> None:
    each = D(100) / D(count)
    percents = [q2(each)] * (count - 1)
    percents.append(D(100) - sum(percents, D(0)))
    plan = rules.plan_milestones(Money.of("1000.00", "USD"), percents)
    assert plan[0].trigger == MilestoneTrigger.PRODUCTION_START
    assert plan[-1].trigger == MilestoneTrigger.ARRIVAL
    assert all(p.trigger == MilestoneTrigger.SHIPMENT for p in plan[1:-1])
    offsets = [p.due_offset_days for p in plan]
    assert offsets == sorted(offsets) and offsets[0] == 7 and len(set(offsets)) == count


@pytest.mark.parametrize(
    "percents",
    [
        [D(100)],  # too few
        [D(20)] * 6,  # too many
        [D(50), D(40)],  # does not sum to 100
        [D(50), D(60)],  # sums to 110
        [D(100), D(0)],  # zero
        [D(110), D(-10)],  # negative
        [D("33.333"), D("33.333"), D("33.334")],  # more than 2 dp
    ],
)
def test_invalid_schedules_are_rejected(percents: list[Decimal]) -> None:
    with pytest.raises(rules.ScheduleInvalid):
        rules.plan_milestones(Money.of("9600.00", "USD"), percents)


def test_tiny_goods_value_cannot_make_a_zero_tranche() -> None:
    with pytest.raises(rules.ScheduleInvalid):
        rules.plan_milestones(Money.of("0.01", "USD"), [D(50), D(50)])


@given(
    cents=st.integers(min_value=1, max_value=10**12),
    cuts=st.lists(st.integers(min_value=1, max_value=9999), min_size=1, max_size=4, unique=True),
)
def test_random_splits_always_sum_exactly(cents: int, cuts: list[int]) -> None:
    total = Money(D(cents) / 100, "USD")
    edges = [0, *sorted(cuts), 10000]
    percents = [D(b - a) / 100 for a, b in pairwise(edges)]
    try:
        plan = rules.plan_milestones(total, percents)
    except rules.ScheduleInvalid:
        # Only legitimate refusal: a part rounded to zero on a tiny total.
        assert cents < 10**4
        return
    assert sum((p.amount.amount for p in plan), D(0)) == q2(total.amount)
    assert sum((p.percent for p in plan), D(0)) == 1
    assert all(p.amount.amount > 0 for p in plan)


# --- state machines ---------------------------------------------------------------------------

DEAL_OK = [
    (DS.DRAFT, DS.PROPOSED),
    (DS.PROPOSED, DS.PROPOSED),
    (DS.PROPOSED, DS.CONFIRMED),
    (DS.CONFIRMED, DS.PROPOSED),
    (DS.CONFIRMED, DS.FUNDED),
    (DS.FUNDED, DS.IN_PRODUCTION),
    (DS.IN_PRODUCTION, DS.SHIPPED),
    (DS.SHIPPED, DS.ARRIVED),
    (DS.ARRIVED, DS.COMPLETED),
    (DS.FUNDED, DS.DISPUTED),
    (DS.SHIPPED, DS.DISPUTED),
    (DS.DISPUTED, DS.CANCELLED),
    (DS.DRAFT, DS.CANCELLED),
    (DS.FUNDED, DS.CANCELLED),
]
DEAL_BAD = [
    (DS.DRAFT, DS.CONFIRMED),
    (DS.DRAFT, DS.FUNDED),
    (DS.PROPOSED, DS.FUNDED),
    (DS.CONFIRMED, DS.IN_PRODUCTION),
    (DS.FUNDED, DS.SHIPPED),
    (DS.IN_PRODUCTION, DS.COMPLETED),
    (DS.SHIPPED, DS.IN_PRODUCTION),
    (DS.COMPLETED, DS.DISPUTED),
    (DS.COMPLETED, DS.CANCELLED),
    (DS.CANCELLED, DS.DRAFT),
    (DS.CANCELLED, DS.FUNDED),
    (DS.DRAFT, DS.DISPUTED),
    (DS.CONFIRMED, DS.DISPUTED),
]


@pytest.mark.parametrize(("src", "dst"), DEAL_OK)
def test_deal_transitions_allowed(src: DS, dst: DS) -> None:
    rules.check_deal_transition(src, dst)


@pytest.mark.parametrize(("src", "dst"), DEAL_BAD)
def test_deal_transitions_refused_with_409(src: DS, dst: DS) -> None:
    with pytest.raises(rules.InvalidTransition) as exc:
        rules.check_deal_transition(src, dst)
    assert isinstance(exc.value, Conflict) and exc.value.status == 409


MS_OK = [
    (MS.PROPOSED, MS.PENDING),
    (MS.PENDING, MS.READY),
    (MS.READY, MS.PENDING_APPROVAL),
    (MS.READY, MS.RELEASED),
    (MS.PENDING_APPROVAL, MS.RELEASED),
    (MS.PENDING_APPROVAL, MS.READY),
    (MS.READY, MS.REFUNDED),
    (MS.FROZEN, MS.REFUNDED),
    (MS.PENDING, MS.CANCELLED),
]
MS_BAD = [
    (MS.PENDING, MS.RELEASED),
    (MS.PENDING, MS.PENDING_APPROVAL),
    (MS.PROPOSED, MS.READY),
    (MS.PROPOSED, MS.RELEASED),
    (MS.RELEASED, MS.READY),
    (MS.RELEASED, MS.REFUNDED),
    (MS.REFUNDED, MS.RELEASED),
    (MS.CANCELLED, MS.READY),
    (MS.PENDING, MS.REFUNDED),
]


@pytest.mark.parametrize(("src", "dst"), MS_OK)
def test_milestone_transitions_allowed(src: MS, dst: MS) -> None:
    rules.check_milestone_transition(src, dst)


@pytest.mark.parametrize(("src", "dst"), MS_BAD)
def test_milestone_transitions_refused(src: MS, dst: MS) -> None:
    with pytest.raises(rules.InvalidTransition):
        rules.check_milestone_transition(src, dst)


def test_every_status_has_a_transition_row() -> None:
    assert set(rules.DEAL_TRANSITIONS) == set(DS)
    assert set(rules.MILESTONE_TRANSITIONS) == set(MS)


@pytest.mark.parametrize(
    ("current", "trigger", "settled", "path"),
    [
        (DS.FUNDED, MilestoneTrigger.PRODUCTION_START, False, [DS.IN_PRODUCTION]),
        (DS.IN_PRODUCTION, MilestoneTrigger.SHIPMENT, False, [DS.SHIPPED]),
        (DS.SHIPPED, MilestoneTrigger.ARRIVAL, False, [DS.ARRIVED]),
        (DS.SHIPPED, MilestoneTrigger.ARRIVAL, True, [DS.ARRIVED, DS.COMPLETED]),
        (DS.IN_PRODUCTION, MilestoneTrigger.ARRIVAL, True, [DS.SHIPPED, DS.ARRIVED, DS.COMPLETED]),
        (DS.IN_PRODUCTION, MilestoneTrigger.PRODUCTION_START, False, []),  # never backwards
        (DS.SHIPPED, MilestoneTrigger.PRODUCTION_START, False, []),
        (DS.DISPUTED, MilestoneTrigger.SHIPMENT, False, []),
    ],
)
def test_release_path(
    current: DS, trigger: MilestoneTrigger, settled: bool, path: list[DS]
) -> None:
    walked = rules.release_path(current, trigger, settled)
    assert walked == path
    state = current
    for step in walked:
        rules.check_deal_transition(state, step)
        state = step


# --- funding and readiness --------------------------------------------------------------------


def test_ready_seq_follows_deposits() -> None:
    ms = [(1, D("2880"), MS.PENDING), (2, D("5760"), MS.PENDING), (3, D("960"), MS.PENDING)]
    assert rules.ready_seq(ms, D("0")) is None
    assert rules.ready_seq(ms, D("2879.99")) is None
    assert rules.ready_seq(ms, D("2880")) == 1
    assert rules.ready_seq(ms, D("9600")) == 1  # only the first unsettled one is READY
    settled = [(1, D("2880"), MS.RELEASED), *ms[1:]]
    assert rules.ready_seq(settled, D("2880")) is None
    assert rules.ready_seq(settled, D("8640")) == 2


def test_default_deposit_is_the_next_uncovered_tranche() -> None:
    ms = [(D("2880"), MS.PENDING), (D("5760"), MS.PENDING), (D("960"), MS.PENDING)]
    assert rules.default_deposit(ms, D("0")) == D("2880")
    assert rules.default_deposit(ms, D("2880")) == D("5760")
    assert rules.default_deposit(ms, D("3000")) == D("5640")
    assert rules.default_deposit(ms, D("9600")) == D("0")


def test_advance_limit_boundary_is_strict() -> None:
    limit = D("20000")
    assert not rules.over_advance_limit(D("20000"), limit)
    assert rules.over_advance_limit(D("20000.01"), limit)


def test_next_reference() -> None:
    assert rules.next_reference(None, 2026) == "SETU-2026-0001"
    assert rules.next_reference("SETU-2026-0006", 2026) == "SETU-2026-0007"
    assert rules.next_reference("SETU-2026-0999", 2026) == "SETU-2026-1000"


# --- postings, fx, invariant ------------------------------------------------------------------


def test_postings_balance_and_use_seed_account_names() -> None:
    amt = Money.of("2880.00", "USD")
    fund = rules.fund_postings("SETU-2026-0007", "rahima", amt)
    assert [(p.account, p.direction) for p in fund] == [
        ("escrow:SETU-2026-0007", LedgerDirection.DEBIT),
        ("buyer:rahima:cash", LedgerDirection.CREDIT),
    ]
    rel = rules.release_postings("SETU-2026-0007", "huaxin", amt)
    assert rel[0].account == "supplier:huaxin:settlement" and rel[0].direction.value == "DEBIT"
    assert rel[1].account == "escrow:SETU-2026-0007"
    ref = rules.refund_postings("SETU-2026-0007", "rahima", amt)
    assert ref[0].account == "buyer:rahima:cash"
    rules.assert_balanced(fund + rel + ref)
    with pytest.raises(ValueError):
        rules.fund_postings("X", "y", Money.of("0", "USD"))
    with pytest.raises(rules.InvariantViolation):
        rules.assert_balanced([fund[0]])


FX = FxTable(
    [
        FxQuote("USD", "CNY", D("7.099"), date(2026, 10, 20), "MOCK"),
        FxQuote("USD", "BDT", D("122.59"), date(2026, 10, 20), "MOCK"),
    ]
)


def test_settle_cny_records_rate_and_counter_amount() -> None:
    s = rules.settle(Money.of("2880.00", "USD"), "CNY", FX)
    assert s.rate == D("7.09900000") and s.counter == Money.of("20445.12", "CNY")
    assert any("USD" in f and "CNY" in f for f in s.facts)


def test_settle_same_currency_has_no_conversion() -> None:
    s = rules.settle(Money.of("2880.00", "USD"), "USD", FX)
    assert s.rate is None and s.counter is None


@given(cents=st.integers(min_value=1, max_value=10**11))
def test_counter_amount_is_reproducible_from_the_stored_rate(cents: int) -> None:
    amount = Money(D(cents) / 100, "USD")
    s = rules.settle(amount, "CNY", FX)
    assert s.rate is not None and s.counter is not None
    assert s.counter.amount == q2(amount.amount * s.rate)


def test_invariant() -> None:
    rules.check_invariant(D("100"), D("30"), D("20"), D("50"))
    rules.check_invariant(D("0"), D("0"), D("0"), D("0"))
    for bad in [
        (D("100"), D("30"), D("20"), D("49.99")),
        (D("100"), D("30"), D("20"), D("51")),
        (D("-1"), D("0"), D("0"), D("-1")),
        (D("0"), D("10"), D("-10"), D("0")),
    ]:
        with pytest.raises(rules.InvariantViolation):
            rules.check_invariant(*bad)
