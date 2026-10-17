"""FR-5 milestone escrow: pure rules (no I/O, no LLM).

State machines (enforced in code, an illegal move raises `InvalidTransition`, HTTP 409):

  Deal       DRAFT -> PROPOSED -> CONFIRMED -> FUNDED -> IN_PRODUCTION -> SHIPPED -> ARRIVED
             -> COMPLETED, plus DISPUTED and CANCELLED from the allowed states below.
  Milestone  PROPOSED -> PENDING (the spec's LOCKED) -> READY -> PENDING_APPROVAL -> RELEASED,
             or REFUNDED. FROZEN is the dispute hold. CANCELLED is for tranches never funded.

Money: a split is `split_by_ratios` (quantized to 2 dp, the last tranche absorbs the remainder), a
posting set always balances exactly, and `funded = released + refunded + balance` is checked after
every money operation.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import (
    DealStatus,
    DocType,
    LedgerDirection,
    MilestoneStatus,
    MilestoneTrigger,
)
from app.domain.fx import FxTable
from app.domain.money import CENT, ONE, ZERO, Currency, Money, q2, split_by_ratios
from app.errors import Conflict, DomainError

DS, MS = DealStatus, MilestoneStatus
HUNDRED = Decimal("100")
MIN_MILESTONES, MAX_MILESTONES = 2, 5
TEMPLATE_30_60_10 = "30/60/10"
TEMPLATES: dict[str, tuple[Decimal, ...]] = {
    TEMPLATE_30_60_10: (Decimal("30"), Decimal("60"), Decimal("10")),
}
FX_RATE_PLACES = Decimal("0.00000001")


class InvalidTransition(Conflict):
    def __init__(self, kind: str, src: str, dst: str) -> None:
        super().__init__(f"{kind} cannot move from {src} to {dst}", "INVALID_TRANSITION")


class ScheduleInvalid(DomainError):
    status = 422
    title = "Invalid milestone schedule"

    def __init__(self, detail: str) -> None:
        super().__init__(detail, "SCHEDULE_INVALID")


class InvariantViolation(DomainError):
    status = 500
    title = "Escrow invariant violated"

    def __init__(self, detail: str) -> None:
        super().__init__(detail, "ESCROW_INVARIANT")


# --- state machines -----------------------------------------------------------------------------

DEAL_TRANSITIONS: dict[DealStatus, frozenset[DealStatus]] = {
    DS.DRAFT: frozenset({DS.PROPOSED, DS.CANCELLED}),
    DS.PROPOSED: frozenset({DS.PROPOSED, DS.CONFIRMED, DS.CANCELLED}),
    DS.CONFIRMED: frozenset({DS.PROPOSED, DS.FUNDED, DS.CANCELLED}),
    DS.FUNDED: frozenset({DS.IN_PRODUCTION, DS.DISPUTED, DS.CANCELLED}),
    DS.IN_PRODUCTION: frozenset({DS.SHIPPED, DS.DISPUTED, DS.CANCELLED}),
    DS.SHIPPED: frozenset({DS.ARRIVED, DS.DISPUTED, DS.CANCELLED}),
    DS.ARRIVED: frozenset({DS.COMPLETED, DS.DISPUTED, DS.CANCELLED}),
    DS.DISPUTED: frozenset({DS.IN_PRODUCTION, DS.SHIPPED, DS.ARRIVED, DS.COMPLETED, DS.CANCELLED}),
    DS.COMPLETED: frozenset(),
    DS.CANCELLED: frozenset(),
}
MILESTONE_TRANSITIONS: dict[MilestoneStatus, frozenset[MilestoneStatus]] = {
    MS.PROPOSED: frozenset({MS.PENDING, MS.CANCELLED}),
    MS.PENDING: frozenset({MS.READY, MS.FROZEN, MS.CANCELLED}),
    MS.READY: frozenset({MS.PENDING_APPROVAL, MS.RELEASED, MS.REFUNDED, MS.FROZEN}),
    MS.PENDING_APPROVAL: frozenset({MS.READY, MS.RELEASED, MS.REFUNDED, MS.FROZEN}),
    MS.FROZEN: frozenset({MS.READY, MS.REFUNDED, MS.CANCELLED}),
    MS.RELEASED: frozenset(),
    MS.REFUNDED: frozenset(),
    MS.CANCELLED: frozenset(),
}
SETTLED = frozenset({MS.RELEASED, MS.REFUNDED, MS.CANCELLED})
# Deal statuses in which escrow money may be held, released or refunded.
LIVE_DEAL = frozenset({DS.FUNDED, DS.IN_PRODUCTION, DS.SHIPPED, DS.ARRIVED})
FUNDABLE_DEAL = frozenset({DS.CONFIRMED}) | LIVE_DEAL
REFUNDABLE_DEAL = LIVE_DEAL | {DS.DISPUTED}
# Forward path a release walks along (each hop is validated against DEAL_TRANSITIONS).
LINEAR: tuple[DealStatus, ...] = (DS.FUNDED, DS.IN_PRODUCTION, DS.SHIPPED, DS.ARRIVED, DS.COMPLETED)
TRIGGER_STATUS: dict[MilestoneTrigger, DealStatus] = {
    MilestoneTrigger.PRODUCTION_START: DS.IN_PRODUCTION,
    MilestoneTrigger.SHIPMENT: DS.SHIPPED,
    MilestoneTrigger.ARRIVAL: DS.ARRIVED,
}


def check_deal_transition(src: DealStatus, dst: DealStatus) -> None:
    if dst not in DEAL_TRANSITIONS[src]:
        raise InvalidTransition("deal", src.value, dst.value)


def check_milestone_transition(src: MilestoneStatus, dst: MilestoneStatus) -> None:
    if dst not in MILESTONE_TRANSITIONS[src]:
        raise InvalidTransition("milestone", src.value, dst.value)


def release_path(
    current: DealStatus, trigger: MilestoneTrigger, all_settled: bool
) -> list[DealStatus]:
    """Deal statuses to walk through after a tranche is released (empty = no change).
    First tranche (production start) -> IN_PRODUCTION; shipment -> SHIPPED; arrival -> ARRIVED;
    when no tranche is left unsettled the deal also completes (ARRIVED -> COMPLETED). A deal never
    moves backwards, and a dispute is left alone."""
    target = DS.COMPLETED if all_settled else TRIGGER_STATUS[trigger]
    if current not in LINEAR or LINEAR.index(target) <= LINEAR.index(current):
        return []
    return list(LINEAR[LINEAR.index(current) + 1 : LINEAR.index(target) + 1])


# --- schedule -------------------------------------------------------------------------------------

EVIDENCE: dict[MilestoneTrigger, tuple[DocType, ...]] = {
    MilestoneTrigger.PRODUCTION_START: (DocType.PROFORMA_INVOICE, DocType.PRODUCTION_PHOTO),
    MilestoneTrigger.SHIPMENT: (
        DocType.BILL_OF_LADING,
        DocType.PACKING_LIST,
        DocType.COMMERCIAL_INVOICE,
    ),
    MilestoneTrigger.ARRIVAL: (DocType.BILL_OF_ENTRY,),
}
CONDITIONS: dict[MilestoneTrigger, str] = {
    MilestoneTrigger.PRODUCTION_START: (
        "Supplier has started production: proforma invoice and production photos are verified."
    ),
    MilestoneTrigger.SHIPMENT: (
        "Goods are shipped: bill of lading, packing list and commercial invoice are verified."
    ),
    MilestoneTrigger.ARRIVAL: "Goods arrived at the port of discharge: bill of entry is verified.",
}
DEFAULT_OFFSETS_3 = (7, 35, 60)
FIRST_DUE_DAYS, LAST_DUE_DAYS = 7, 60


def trigger_for(position: int, count: int) -> MilestoneTrigger:
    """First tranche = production start, last = arrival, anything in between = shipment."""
    if position == 0:
        return MilestoneTrigger.PRODUCTION_START
    if position == count - 1:
        return MilestoneTrigger.ARRIVAL
    return MilestoneTrigger.SHIPMENT


def due_offsets(count: int) -> list[int]:
    """Days after the proposal date: 7, 35, 60 for three tranches, otherwise evenly spread."""
    if count == 3:
        return list(DEFAULT_OFFSETS_3)
    span = LAST_DUE_DAYS - FIRST_DUE_DAYS
    return [FIRST_DUE_DAYS + (span * i) // (count - 1) for i in range(count)]


@dataclass(frozen=True, slots=True)
class PlannedMilestone:
    seq: int
    trigger: MilestoneTrigger
    percent: Decimal  # fraction, 0.30 = 30 %
    amount: Money
    condition_text: str
    required_evidence: tuple[DocType, ...]
    due_offset_days: int


def parse_percents(percents: Sequence[Decimal]) -> tuple[Decimal, ...]:
    """Percentages (30 = 30 %): 2 to 5 tranches, each > 0, at most 2 decimals, summing to 100."""
    if not MIN_MILESTONES <= len(percents) <= MAX_MILESTONES:
        raise ScheduleInvalid(f"a schedule needs {MIN_MILESTONES} to {MAX_MILESTONES} milestones")
    for p in percents:
        if not isinstance(p, Decimal):
            raise TypeError("percents must be Decimal")
        if p <= ZERO:
            raise ScheduleInvalid("every milestone percent must be greater than 0")
        if p != p.quantize(CENT):
            raise ScheduleInvalid("percents may have at most 2 decimal places")
    if sum(percents, ZERO) != HUNDRED:
        raise ScheduleInvalid("milestone percents must sum to exactly 100")
    return tuple(percents)


def plan_milestones(goods: Money, percents: Sequence[Decimal]) -> list[PlannedMilestone]:
    """Split the goods value by `percents`. The parts sum exactly to the goods value
    (9,600.00 at 30/60/10 -> 2,880.00 / 5,760.00 / 960.00); the last absorbs any rounding."""
    clean = parse_percents(percents)
    fractions = [p / HUNDRED for p in clean]
    if sum(fractions, ZERO) != ONE:
        raise ScheduleInvalid("milestone percents must sum to exactly 100")
    amounts = split_by_ratios(goods, fractions)
    if any(a.amount <= ZERO for a in amounts):
        raise ScheduleInvalid("the goods value is too small to split into these milestones")
    offsets = due_offsets(len(clean))
    out = []
    for i, (fraction, amount) in enumerate(zip(fractions, amounts, strict=True)):
        trigger = trigger_for(i, len(clean))
        out.append(
            PlannedMilestone(
                seq=i + 1,
                trigger=trigger,
                percent=fraction,
                amount=amount,
                condition_text=CONDITIONS[trigger],
                required_evidence=EVIDENCE[trigger],
                due_offset_days=offsets[i],
            )
        )
    return out


def next_reference(last: str | None, year: int) -> str:
    """SETU-<year>-NNNN: the highest existing number of that year plus one."""
    n = int(last.rsplit("-", 1)[1]) if last else 0
    return f"SETU-{year}-{n + 1:04d}"


# --- funding, readiness ---------------------------------------------------------------------------


def ready_seq(
    milestones: Sequence[tuple[int, Decimal, MilestoneStatus]], funded_total: Decimal
) -> int | None:
    """The tranche that should be READY: the first unsettled one, if everything up to and including
    it is covered by the money deposited so far. (seq, amount, status) in seq order."""
    cumulative = ZERO
    for seq, amount, status in milestones:
        cumulative += amount
        if status in SETTLED:
            continue
        return seq if cumulative <= funded_total else None
    return None


def default_deposit(
    milestones: Sequence[tuple[Decimal, MilestoneStatus]], funded_total: Decimal
) -> Decimal:
    """Money needed to cover the next not-yet-covered tranche (0 when all are covered)."""
    cumulative = ZERO
    for amount, status in milestones:
        cumulative += amount
        if status in SETTLED:
            continue
        if cumulative > funded_total:
            return cumulative - funded_total
    return ZERO


def over_advance_limit(funded_usd: Decimal, limit_usd: Decimal) -> bool:
    """True when money held in escrow ahead of release is strictly above the limit."""
    return funded_usd > limit_usd


# --- postings -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Posting:
    account: str
    direction: LedgerDirection
    amount: Money


def buyer_cash(code: str) -> str:
    return f"buyer:{code}:cash"


def escrow_account(ref: str) -> str:
    return f"escrow:{ref}"


def supplier_settlement(code: str) -> str:
    return f"supplier:{code}:settlement"


def _pair(debit: str, credit: str, amount: Money) -> list[Posting]:
    if amount.amount <= ZERO:
        raise ValueError("postings need a positive amount")
    posts = [
        Posting(debit, LedgerDirection.DEBIT, amount),
        Posting(credit, LedgerDirection.CREDIT, amount),
    ]
    assert_balanced(posts)
    return posts


def fund_postings(ref: str, buyer_code: str, amount: Money) -> list[Posting]:
    return _pair(escrow_account(ref), buyer_cash(buyer_code), amount)


def release_postings(ref: str, supplier_code: str, amount: Money) -> list[Posting]:
    return _pair(supplier_settlement(supplier_code), escrow_account(ref), amount)


def refund_postings(ref: str, buyer_code: str, amount: Money) -> list[Posting]:
    return _pair(buyer_cash(buyer_code), escrow_account(ref), amount)


def assert_balanced(postings: Sequence[Posting]) -> None:
    debit = sum((p.amount.amount for p in postings if p.direction == LedgerDirection.DEBIT), ZERO)
    credit = sum((p.amount.amount for p in postings if p.direction == LedgerDirection.CREDIT), ZERO)
    if debit != credit:
        raise InvariantViolation("ledger posting does not balance")


# --- FX at release --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Settlement:
    """What the supplier's account receives. `rate` is None when no conversion is needed."""

    currency: Currency
    rate: Decimal | None
    counter: Money | None
    facts: tuple[str, ...]


def settle(amount: Money, settlement_currency: Currency, fx: FxTable) -> Settlement:
    """Convert a released tranche to the beneficiary account currency with the recorded rate:
    counter = round_half_up(amount x rate); the rate is stored to 8 dp so it can be re-derived."""
    if settlement_currency == amount.currency:
        return Settlement(
            settlement_currency, None, None, (f"paid in {amount.currency}, no conversion",)
        )
    rate = fx.rate(amount.currency, settlement_currency).quantize(FX_RATE_PLACES)
    counter = Money(q2(amount.amount * rate), settlement_currency)
    quotes = [q.fact() for q in fx.path(amount.currency, settlement_currency)]
    return Settlement(
        settlement_currency,
        rate,
        counter,
        (f"{amount.format()} x {rate} = {counter.format()}", *quotes),
    )


# --- invariant ------------------------------------------------------------------------------------


def check_invariant(
    funded: Decimal, released: Decimal, refunded: Decimal, balance: Decimal
) -> None:
    """funded = released + refunded + balance, and none of them negative."""
    if min(funded, released, refunded, balance) < ZERO:
        raise InvariantViolation("escrow totals must not be negative")
    if funded != released + refunded + balance:
        raise InvariantViolation(
            f"funded {funded} != released {released} + refunded {refunded} + balance {balance}"
        )
