"""FR-1 financing service: gap, option matching, schedule, cash-flow impact and simulated
applications. Numbers come from app/domain/financing.py; this module loads rows and shapes output.

Writes: POST applications (SUBMITTED) and simulate-approval (APPROVED + two cashflow_items + alert
recompute). Both are human HTTP endpoints only; nothing here is an LLM tool. All money is simulated.
"""

import contextlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.db.enums import (
    CashflowKind,
    DealStatus,
    FinancingApplicationStatus,
    FlowDirection,
    MilestoneTrigger,
)
from app.db.models import (
    CashflowItem,
    Deal,
    EscrowAccount,
    FinancingApplication,
    FinancingOption,
    Milestone,
    Party,
)
from app.domain.cashflow import Flow, Forecast
from app.domain.financing import (
    CLEARANCE_DAYS,
    Cost,
    Gap,
    Quote,
    Terms,
    code_rules,
    evaluate_rules,
    option_cost,
    option_tenor,
    order_gap,
    pick_sentences,
    rank,
    risk_notes,
    schedule,
    shortfall_gap,
    why_codes,
)
from app.domain.money import ZERO, Currency, Money, q2
from app.domain.narrative import bn
from app.errors import Conflict, DomainError, Forbidden, NotFound
from app.schemas.analysis import Explanation
from app.schemas.cashflow import ShortfallOut
from app.schemas.financing import (
    ApplicationList,
    ApplicationOut,
    ApplicationRequest,
    ApprovalOut,
    CheckOut,
    CostOut,
    DatedAmount,
    DealRef,
    GapOut,
    ImpactOut,
    ImpactPoint,
    ImpactRequest,
    ImpactSide,
    InstalmentOut,
    MatchOut,
    MatchRequest,
    OptionQuote,
    ScheduleOut,
    TopPick,
)
from app.services import analysis
from app.services.alerts import recompute_book
from app.services.cashflow import (
    ACTIVE,
    DEFAULT_DAYS,
    BuyerBook,
    compute,
    load_book,
    opening,
)
from app.services.scope import party, require_buyer

ACTIVE_APPS = (FinancingApplicationStatus.SUBMITTED, FinancingApplicationStatus.APPROVED)


# ---------- loading ----------


def positive(amount: str, ccy: Currency) -> Money:
    m = Money(Decimal(amount), ccy)
    if m.amount <= ZERO:
        raise DomainError("amount must be greater than 0")
    return m


def _deal_for(
    db: Session, user: CurrentUser, buyer: Party, ref: str | None, book: BuyerBook
) -> Deal:
    if ref:
        deal = analysis.find_deal(db, ref)
        if deal.buyer_id != buyer.id:
            raise Forbidden("this deal belongs to another buyer")
        return deal
    fc = compute(book, book.flows, DEFAULT_DAYS)
    first = next((d for d in fc.days if d.closing.amount < ZERO), None)
    trigger = next((f.deal_ref for f in (first.items if first else ()) if f.deal_ref), None)
    if trigger:
        return analysis.find_deal(db, trigger)
    deal = db.scalars(
        select(Deal)
        .where(Deal.buyer_id == buyer.id, Deal.status.in_(ACTIVE))
        .order_by(Deal.opened_on.desc())
    ).first()
    if deal is None:
        raise NotFound("no active deal to finance")
    return deal


def _option(db: Session, ref: str) -> FinancingOption:
    cond = FinancingOption.code == ref
    with contextlib.suppress(ValueError):
        cond = cond | (FinancingOption.id == uuid.UUID(ref))
    opt = db.scalars(select(FinancingOption).where(cond, FinancingOption.active.is_(True))).first()
    if opt is None:
        raise NotFound("financing option not found")
    return opt


def terms(o: FinancingOption) -> Terms:
    return Terms(
        code=o.code,
        kind=o.kind,
        annual_rate=o.annual_rate,
        flat_cost_rate=o.flat_cost_rate,
        price_uplift_rate=o.price_uplift_rate,
        fee_rate=o.fee_rate,
        fee_fixed=o.fee_fixed,
        tenor_days_min=o.tenor_days_min,
        tenor_days_max=o.tenor_days_max,
        tenor_rule=o.tenor_rule,
        min_amount=o.min_amount,
        max_amount=o.max_amount,
        collateral=o.collateral,
        conditions=o.conditions,
        eligibility=o.eligibility or {},
    )


def milestone3_release(db: Session, deal: Deal) -> date | None:
    arrival = db.scalar(
        select(Milestone.due_on).where(
            Milestone.deal_id == deal.id, Milestone.trigger == MilestoneTrigger.ARRIVAL
        )
    )
    return arrival + timedelta(days=CLEARANCE_DAYS) if arrival else None


def escrow_funded(db: Session, deal: Deal) -> bool:
    e = db.scalar(select(EscrowAccount).where(EscrowAccount.deal_id == deal.id))
    return bool(e and e.funded_total > ZERO)


def facts_for(db: Session, buyer: Party, deal: Deal, amount: Money, book: BuyerBook) -> dict:
    supplier = party(db, deal.supplier_id)

    def completed(*extra: object) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(Deal)
                .where(Deal.buyer_id == buyer.id, Deal.status == DealStatus.COMPLETED, *extra)
            )
            or 0
        )

    months = (book.today.year - buyer.first_seen_on.year) * 12 + (
        book.today.month - buyer.first_seen_on.month
    )
    return {
        "supplier_code": supplier.code,
        "supplier_kyb_status": supplier.kyb_status,
        "buyer_kyb_status": buyer.kyb_status,
        "completed_deals_with_supplier": completed(Deal.supplier_id == supplier.id),
        "completed_deals_total": completed(),
        "escrow_funded": escrow_funded(db, deal),
        "amount_usd": f"{q2(book.fx.convert(amount, 'USD').amount)}",
        "months_trading": months,
    }


# ---------- gap ----------


def compute_gap(db: Session, book: BuyerBook, deal: Deal, mode: str) -> Gap | None:
    ccy = book.currency
    if mode == "order":
        lc, _ = analysis.deal_figures(db, deal, book.fx, ccy)
        release = milestone3_release(db, deal) or book.today + timedelta(days=DEFAULT_DAYS)
        return order_gap(lc.total, opening(book), book.today, release)
    fc = compute(book, book.flows, DEFAULT_DAYS)
    return shortfall_gap(fc, Money(ZERO, ccy))


def deal_ref(db: Session, deal: Deal) -> DealRef:
    return DealRef(
        reference=deal.reference,
        title=deal.title,
        supplier_name=party(db, deal.supplier_id).legal_name,
    )


def _gap_sentences(g: Gap | None, landed: Money | None, cash: Money | None) -> list[Explanation]:
    if g is None or g.amount.amount <= ZERO:
        return [
            Explanation(
                code="NO_FINANCING_NEEDED",
                en="Your projected balance covers every payment; no financing is needed.",
                bn="আপনার আনুমানিক ব্যালেন্সে সব পরিশোধ হয়ে যায়; অর্থায়নের প্রয়োজন নেই।",
            )
        ]
    amt, on, days = g.amount.format(), g.needed_by.isoformat(), g.needed_for_days
    if g.mode == "order":
        return [
            Explanation(
                code="ORDER_GAP",
                en=f"Landed cost {landed.format() if landed else ''} minus available cash "
                f"{cash.format() if cash else ''} leaves {amt} to finance for about {days} days, "
                f"until milestone 3 is released.",
                bn=bn(
                    f"ল্যান্ডেড খরচ {landed.format() if landed else ''} থেকে হাতে থাকা নগদ "
                    f"{cash.format() if cash else ''} বাদ দিলে {amt} অর্থায়ন লাগবে, প্রায় {days} "
                    f"দিনের জন্য (মাইলস্টোন ৩ ছাড় পর্যন্ত)।"
                ),
            )
        ]
    rec = g.recover_on.isoformat() if g.recover_on else None
    out = [
        Explanation(
            code="SHORTFALL_GAP",
            en=f"You need {amt} on {on}"
            + (f"; your balance recovers on {rec} ({days} days)." if rec else "."),
            bn=bn(
                f"{on} তারিখে আপনার {amt} লাগবে"
                + (f"; {rec} তারিখে ব্যালেন্স আবার ঠিক হয় ({days} দিন)।" if rec else "।")
            ),
        )
    ]
    if g.peak.amount > g.amount.amount:
        peak = g.peak.format()
        out.append(
            Explanation(
                code="DIP_DEEPENS",
                en=f"The dip deepens to {peak} before it recovers; covering only {amt} leaves "
                f"a smaller shortfall on later days.",
                bn=bn(
                    f"ব্যালেন্স ঠিক হওয়ার আগে ঘাটতি {peak} পর্যন্ত বাড়ে; শুধু {amt} নিলে পরের "
                    f"দিনগুলোতে ছোট ঘাটতি থেকে যায়।"
                ),
            )
        )
    return out


def get_gap(
    db: Session, user: CurrentUser, party_id: uuid.UUID | None, deal_id: str | None, mode: str
) -> GapOut:
    buyer = require_buyer(db, user, party_id)
    book = load_book(db, buyer)
    deal = _deal_for(db, user, buyer, deal_id, book)
    g = compute_gap(db, book, deal, mode)
    fx, ccy = book.fx, book.currency
    landed = cash = None
    if mode == "order":
        landed = analysis.deal_figures(db, deal, fx, ccy)[0].total
        cash = opening(book)
    zero = Money(ZERO, ccy)
    none_needed = g is None or g.amount.amount <= ZERO
    return GapOut(
        party_id=buyer.id,
        deal=deal_ref(db, deal),
        mode=mode,  # type: ignore[arg-type]
        currency=ccy,
        no_financing_needed=none_needed,
        amount=analysis.amounts(g.amount if g else zero, fx),
        needed_by=g.needed_by if g else book.today,
        needed_for_days=g.needed_for_days if g else 0,
        recover_on=g.recover_on if g else None,
        peak_amount=analysis.amounts(g.peak if g else zero, fx),
        landed_cost=analysis.amounts(landed, fx) if landed else None,
        available_cash=analysis.amounts(cash, fx) if cash else None,
        explanations=_gap_sentences(g, landed, cash),
        facts=list(g.facts) if g else [],
    )


# ---------- matching ----------


def cost_out(c: Cost, book: BuyerBook) -> CostOut:
    fx = book.fx
    return CostOut(
        interest=analysis.amounts(c.interest, fx),
        fees=analysis.amounts(c.fees, fx),
        uplift=analysis.amounts(c.uplift, fx),
        flat=analysis.amounts(c.flat, fx),
        total=analysis.amounts(c.total, fx),
        per_30_days=analysis.amounts(c.per_30_days, fx),
        effective_annual_rate_pct=f"{q2(c.effective_annual_rate * 100)}",
    )


def quote_all(
    db: Session,
    book: BuyerBook,
    deal: Deal,
    amount: Money,
    start: date,
    needed_days: int,
) -> list[tuple[FinancingOption, Quote]]:
    funded = escrow_funded(db, deal)
    release = milestone3_release(db, deal)
    facts = facts_for(db, book.buyer, deal, amount, book)
    out = []
    for o in db.scalars(
        select(FinancingOption)
        .where(FinancingOption.active.is_(True))
        .order_by(FinancingOption.code)
    ).all():
        t = terms(o)
        tenor = option_tenor(t, start, release)
        checks = (
            *evaluate_rules(t.eligibility, {**facts, "tenor_days": tenor}),
            *code_rules(t, amount, tenor, needed_days, funded),
        )
        out.append((o, Quote(t, option_cost(t, amount, tenor), checks, start)))
    order = {q.terms.code: i for i, q in enumerate(rank([q for _, q in out]))}
    return sorted(out, key=lambda oq: order[oq[1].terms.code])


def quote_out(
    db: Session, o: FinancingOption, q: Quote, i: int, recommended: bool, book: BuyerBook
) -> OptionQuote:
    provider = party(db, o.provider_party_id).legal_name if o.provider_party_id else None
    return OptionQuote(
        option_id=o.id,
        code=o.code,
        name=o.name,
        kind=o.kind,
        provider_name=provider,
        rank=i,
        recommended=recommended,
        eligible=q.eligible,
        tenor_days=q.cost.days,
        start_on=q.start,
        maturity_on=q.maturity,
        principal=analysis.amounts(q.cost.principal, book.fx),
        cost=cost_out(q.cost, book),
        collateral=o.collateral,
        conditions=o.conditions,
        condition_count=q.terms.condition_count,
        checks=[
            CheckOut(code=c.code, ok=c.ok, en=c.en, bn=c.bn, params=c.params) for c in q.checks
        ],
        why_not=[
            CheckOut(code=c.code, ok=c.ok, en=c.en, bn=c.bn, params=c.params) for c in q.failed
        ],
        risk_notes=[Explanation(code=c, en=en, bn=b) for c, en, b in risk_notes(q)],
        facts=list(q.cost.facts),
    )


def match(db: Session, user: CurrentUser, req: MatchRequest) -> MatchOut:
    buyer = require_buyer(db, user, req.party_id)
    book = load_book(db, buyer)
    deal = _deal_for(db, user, buyer, req.deal_id, book)
    g = compute_gap(db, book, deal, req.mode)
    ccy = book.currency
    amount = (
        Money(Decimal(req.amount), ccy)
        if req.amount is not None
        else (g.amount if g else Money(ZERO, ccy))
    )
    start = g.needed_by if g else book.today
    needed = req.days or (g.needed_for_days if g else 1)
    none_needed = amount.amount <= ZERO
    options: list[OptionQuote] = []
    pick = None
    if not none_needed:
        pairs = quote_all(db, book, deal, amount, start, needed)
        eligible = [(o, q) for o, q in pairs if q.eligible]
        for i, (o, q) in enumerate(pairs, start=1):
            options.append(quote_out(db, o, q, i, bool(eligible) and o is eligible[0][0], book))
        if eligible:
            (po, pq), nxt = eligible[0], (eligible[1][1] if len(eligible) > 1 else None)
            pick = TopPick(
                option_id=po.id,
                code=po.code,
                total_cost=analysis.amounts(pq.cost.total, book.fx),
                saving_vs_next=analysis.amounts(nxt.cost.total - pq.cost.total, book.fx)
                if nxt
                else None,
                key_conditions=[po.collateral, po.conditions],
                why_codes=why_codes(pq, nxt),
                sentences=[
                    Explanation(code=c, en=en, bn=b)
                    for c, en, b in pick_sentences(pq, nxt, po.name)
                ],
            )
    return MatchOut(
        party_id=buyer.id,
        deal=deal_ref(db, deal),
        mode=req.mode,
        currency=ccy,
        no_financing_needed=none_needed,
        amount=analysis.amounts(amount, book.fx),
        needed_by=start,
        needed_for_days=needed,
        options=options,
        top_pick=pick,
        fx=analysis.fx_out(analysis.used_quotes(book.fx, ccy)),
    )


# ---------- schedule ----------


def instalments_out(q: Quote, book: BuyerBook) -> list[InstalmentOut]:
    return [
        InstalmentOut(
            due_on=i.due_on,
            principal=analysis.amounts(i.principal, book.fx),
            cost=analysis.amounts(i.cost, book.fx),
            total=analysis.amounts(i.total, book.fx),
        )
        for i in schedule(q.cost, q.start)
    ]


def get_schedule(
    db: Session,
    user: CurrentUser,
    option_ref: str,
    amount: str,
    start: date | None,
    party_id: uuid.UUID | None,
    deal_id: str | None,
) -> ScheduleOut:
    buyer = require_buyer(db, user, party_id)
    book = load_book(db, buyer)
    deal = _deal_for(db, user, buyer, deal_id, book)
    o = _option(db, option_ref)
    t = terms(o)
    begin = start or book.today
    tenor = option_tenor(t, begin, milestone3_release(db, deal))
    money = positive(amount, book.currency)
    q = Quote(t, option_cost(t, money, tenor), (), begin)
    return ScheduleOut(
        option_id=o.id,
        code=o.code,
        amount=analysis.amounts(money, book.fx),
        start_on=begin,
        tenor_days=tenor,
        maturity_on=q.maturity,
        cost=cost_out(q.cost, book),
        instalments=instalments_out(q, book),
    )


# ---------- impact ----------


def loan_flows(q: Quote, ref: str, label: str) -> list[Flow]:
    repay = schedule(q.cost, q.start)[0]
    return [
        Flow(
            f"financing:{ref}:in", q.start, "IN", q.cost.principal, "LOAN", f"{label} (simulated)"
        ),
        Flow(
            f"financing:{ref}:repay",
            repay.due_on,
            "OUT",
            repay.total,
            "LOAN_REPAYMENT",
            f"{label} repayment (simulated)",
        ),
    ]


def _side(fc: Forecast) -> ImpactSide:
    first = next((d for d in fc.days if d.closing.amount < ZERO), None)
    low = fc.lowest
    return ImpactSide(
        first_shortfall=ShortfallOut(on=first.on, amount=analysis.fmt(-first.closing.amount))
        if first
        else None,
        lowest_balance=analysis.fmt(low.closing.amount),
        lowest_on=low.on,
    )


def impact(db: Session, user: CurrentUser, req: ImpactRequest) -> ImpactOut:
    buyer = require_buyer(db, user, req.party_id)
    book = load_book(db, buyer)
    deal = _deal_for(db, user, buyer, req.deal_id, book)
    o = _option(db, req.option_id)
    g = compute_gap(db, book, deal, req.mode)
    amount = positive(req.amount, book.currency)
    start = g.needed_by if g else book.today
    t = terms(o)
    tenor = option_tenor(t, start, milestone3_release(db, deal))
    q = Quote(t, option_cost(t, amount, tenor), (), start)
    before = compute(book, book.flows, DEFAULT_DAYS)
    after = compute(book, [*book.flows, *loan_flows(q, o.code, o.name)], DEFAULT_DAYS)
    b, a = _side(before), _side(after)
    original = b.first_shortfall
    covered = True
    if original is not None:
        day = after.day(original.on)
        covered = day is not None and day.closing.amount >= ZERO
    new = []
    prev_below = False
    for bd, ad in zip(before.days, after.days, strict=True):
        below = ad.closing.amount < ZERO
        if below and not prev_below and bd.closing.amount >= ZERO:
            new.append(ShortfallOut(on=ad.on, amount=analysis.fmt(-ad.closing.amount)))
        prev_below = below
    repay = schedule(q.cost, q.start)[0]
    in_window = repay.due_on <= before.days[-1].on
    sentences = []
    if original is not None:
        on = original.on.isoformat()
        sentences.append(
            Explanation(
                code="ORIGINAL_COVERED" if covered else "ORIGINAL_NOT_COVERED",
                en=f"The shortfall on {on} is covered."
                if covered
                else f"The shortfall on {on} is still there.",
                bn=bn(f"{on} তারিখের ঘাটতি পূরণ হয়।" if covered else f"{on} তারিখের ঘাটতি থেকে যায়।"),
            )
        )
    for s in new:
        amt = Money(Decimal(s.amount), book.currency).format()
        sentences.append(
            Explanation(
                code="NEW_SHORTFALL",
                en=f"New shortfall of {amt} on {s.on.isoformat()}.",
                bn=bn(f"{s.on.isoformat()} তারিখে নতুন ঘাটতি {amt}।"),
            )
        )
    if a.first_shortfall is not None and not any(n.on == a.first_shortfall.on for n in new):
        left = a.first_shortfall
        amt = Money(Decimal(left.amount), book.currency).format()
        sentences.append(
            Explanation(
                code="SHORTFALL_REMAINS",
                en=f"A shortfall of {amt} remains on {left.on.isoformat()}.",
                bn=bn(f"{left.on.isoformat()} তারিখে {amt} ঘাটতি থেকে যায়।"),
            )
        )
    if not in_window:
        sentences.append(
            Explanation(
                code="REPAYMENT_AFTER_WINDOW",
                en=f"Repayment on {repay.due_on.isoformat()} is after the 90-day forecast.",
                bn=bn(f"{repay.due_on.isoformat()} তারিখের পরিশোধ ৯০ দিনের পূর্বাভাসের পরে।"),
            )
        )
    return ImpactOut(
        currency=book.currency,
        option_code=o.code,
        before=b,
        after=a,
        original_shortfall=original,
        original_covered=covered,
        new_shortfalls=new,
        inflow=DatedAmount(on=q.start, amount=analysis.fmt(amount.amount)),
        repayment=DatedAmount(on=repay.due_on, amount=analysis.fmt(repay.total.amount)),
        repayment_in_window=in_window,
        series=[
            ImpactPoint(
                on=bd.on,
                before=analysis.fmt(bd.closing.amount),
                after=analysis.fmt(ad.closing.amount),
            )
            for bd, ad in zip(before.days, after.days, strict=True)
        ],
        explanations=sentences,
    )


# ---------- applications ----------


def app_out(db: Session, a: FinancingApplication, book: BuyerBook) -> ApplicationOut:
    o = db.get(FinancingOption, a.option_id)
    ref = db.scalar(select(Deal.reference).where(Deal.id == a.deal_id)) or ""
    ccy = cast(Currency, a.currency)

    def amt(x: str | Decimal) -> object:
        return analysis.amounts(Money(Decimal(x), ccy), book.fx)

    return ApplicationOut(
        id=a.id,
        reference=a.reference,
        deal_ref=ref,
        option_code=o.code if o else "",
        option_name=o.name if o else "",
        mode=a.mode,  # type: ignore[arg-type]
        currency=ccy,
        amount=amt(a.amount),  # type: ignore[arg-type]
        tenor_days=a.tenor_days,
        start_on=a.start_on,
        maturity_on=a.maturity_on,
        total_cost=amt(a.total_cost),  # type: ignore[arg-type]
        schedule=[
            InstalmentOut(
                due_on=date.fromisoformat(s["due_on"]),
                principal=amt(s["principal"]),  # type: ignore[arg-type]
                cost=amt(s["cost"]),  # type: ignore[arg-type]
                total=amt(s["total"]),  # type: ignore[arg-type]
            )
            for s in a.schedule
        ],
        status=a.status,  # type: ignore[arg-type]
        submitted_at=a.submitted_at,
        decided_at=a.decided_at,
    )


def _next_reference(db: Session, today: date) -> str:
    last = db.scalar(
        select(func.max(FinancingApplication.reference)).where(
            FinancingApplication.reference.like(f"FA-{today.year}-%")
        )
    )
    n = int(last.rsplit("-", 1)[1]) if last else 0
    return f"FA-{today.year}-{n + 1:04d}"


def apply(db: Session, user: CurrentUser, req: ApplicationRequest) -> ApplicationOut:
    buyer = require_buyer(db, user, req.party_id)
    book = load_book(db, buyer)
    deal = _deal_for(db, user, buyer, req.deal_id, book)
    o = _option(db, req.option_id)
    existing = db.scalars(
        select(FinancingApplication).where(
            FinancingApplication.party_id == buyer.id,
            FinancingApplication.deal_id == deal.id,
            FinancingApplication.option_id == o.id,
            FinancingApplication.mode == req.mode,
            FinancingApplication.status.in_(ACTIVE_APPS),
        )
    ).first()
    if existing is not None:
        if q2(existing.amount) != q2(Decimal(req.amount)):
            raise Conflict(
                f"application {existing.reference} for this option is already active "
                f"with amount {q2(existing.amount)}"
            )
        return app_out(db, existing, book)
    g = compute_gap(db, book, deal, req.mode)
    amount = positive(req.amount, book.currency)
    start = g.needed_by if g else book.today
    needed = g.needed_for_days if g else 1
    quote = next(q for opt, q in quote_all(db, book, deal, amount, start, needed) if opt.id == o.id)
    if not quote.eligible:
        raise DomainError(f"option {o.code} is not eligible: {quote.failed[0].en}")
    inst = schedule(quote.cost, quote.start)
    a = FinancingApplication(
        id=uuid.uuid4(),
        reference=_next_reference(db, book.today),
        party_id=buyer.id,
        deal_id=deal.id,
        option_id=o.id,
        mode=req.mode,
        amount=amount.amount,
        currency=amount.currency,
        tenor_days=quote.cost.days,
        start_on=quote.start,
        maturity_on=quote.maturity,
        total_cost=q2(quote.cost.total.amount),
        schedule=[
            {
                "due_on": i.due_on.isoformat(),
                "principal": f"{q2(i.principal.amount)}",
                "cost": f"{q2(i.cost.amount)}",
                "total": f"{q2(i.total.amount)}",
            }
            for i in inst
        ],
        status=FinancingApplicationStatus.SUBMITTED,
        simulated=True,
        submitted_at=datetime.now(UTC),
    )
    db.add(a)
    db.commit()
    return app_out(db, a, book)


def _own_app(db: Session, user: CurrentUser, app_id: uuid.UUID) -> FinancingApplication:
    a = db.get(FinancingApplication, app_id)
    if a is None or not (user.reads_all or a.party_id == user.party_id):
        raise NotFound("application not found")
    return a


def _recheck(db: Session, a: FinancingApplication, buyer: Party) -> str | None:
    """Re-run eligibility and terms at execution time (never trust the submit-time quote)."""
    book = load_book(db, buyer)
    if a.start_on < book.today:
        return "the start date has passed"
    o = db.get(FinancingOption, a.option_id)
    deal = db.get(Deal, a.deal_id)
    if o is None or not o.active or deal is None or deal.status not in ACTIVE:
        return "the option or the deal is no longer active"
    money = Money(a.amount, cast(Currency, a.currency))
    g = compute_gap(db, book, deal, a.mode)
    needed = g.needed_for_days if g else 1
    quote = next(
        q for opt, q in quote_all(db, book, deal, money, a.start_on, needed) if opt.id == o.id
    )
    if not quote.eligible:
        return quote.failed[0].en
    if q2(quote.cost.total.amount) != q2(a.total_cost) or quote.cost.days != a.tenor_days:
        return "the terms changed since submission"
    return None


def simulate_approval(db: Session, user: CurrentUser, app_id: uuid.UUID) -> ApprovalOut:
    """Simulated lender approval: APPROVED + disbursement inflow + repayment outflow + alerts."""
    _own_app(db, user, app_id)
    a = db.get(FinancingApplication, app_id, with_for_update=True)
    assert a is not None
    buyer = party(db, a.party_id)
    if a.status not in ACTIVE_APPS:
        raise Conflict(f"application {a.reference} is {a.status}")
    if a.status == FinancingApplicationStatus.SUBMITTED:
        reason = _recheck(db, a, buyer)
        if reason:
            a.status = FinancingApplicationStatus.REJECTED
            a.decided_at = datetime.now(UTC)
            db.commit()
            raise Conflict(f"application {a.reference} rejected: {reason}")
        o = db.get(FinancingOption, a.option_id)
        name = o.name if o else "Financing"
        a.status = FinancingApplicationStatus.APPROVED
        a.decided_at = datetime.now(UTC)
        repay = a.schedule[0]
        for suffix, on, kind, direction, amount, label in (
            ("in", a.start_on, CashflowKind.OTHER, FlowDirection.IN, a.amount, "disbursement"),
            (
                "repay",
                date.fromisoformat(repay["due_on"]),
                CashflowKind.LOAN_REPAYMENT,
                FlowDirection.OUT,
                Decimal(repay["total"]),
                "repayment",
            ),
        ):
            db.add(
                CashflowItem(
                    id=uuid.uuid5(uuid.NAMESPACE_URL, f"setu:fin:{a.reference}:{suffix}"),
                    key=f"fin:{a.reference}:{suffix}",
                    party_id=a.party_id,
                    on_date=on,
                    kind=kind,
                    direction=direction,
                    amount=amount,
                    currency=a.currency,
                    description=f"{name} {label} · {a.reference} (simulated)"[:200],
                    is_projected=True,
                    deal_id=a.deal_id,
                )
            )
        db.flush()
    book = load_book(db, buyer)
    counts = recompute_book(db, book)
    db.commit()
    return ApprovalOut(application=app_out(db, a, book), alerts=counts)


def list_applications(
    db: Session, user: CurrentUser, party_id: uuid.UUID | None
) -> ApplicationList:
    buyer = require_buyer(db, user, party_id)
    book = load_book(db, buyer)
    rows = db.scalars(
        select(FinancingApplication)
        .where(FinancingApplication.party_id == buyer.id)
        .order_by(FinancingApplication.submitted_at.desc())
    ).all()
    return ApplicationList(party_id=buyer.id, applications=[app_out(db, a, book) for a in rows])
