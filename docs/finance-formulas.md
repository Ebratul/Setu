# Finance formulas (FR-3)

Deterministic Python in `services/agent/app/domain/`. No LLM touches these numbers. Money is `Decimal`
(`app/domain/money.py`), full precision inside a calculation, quantized only at the API boundary with
`ROUND_HALF_UP`. Percent fields in the API are percent strings with 2 dp (`"18.01"`). Domain code keeps
fractions (`0.1801`).

## Landed cost: `landed_cost.py`
```
landed_cost   = goods_value + Σ extra lines (FREIGHT, INSURANCE, DUTY, BANK_CHARGES, OTHER)
share(line)   = line / landed_cost
cost_per_unit = landed_cost / quantity
```
- All lines must be in the goods currency. The service converts them first with `fx.FxTable`.
- Seeded deals carry duty as one `DUTY` line. HS-code duty (CD/RD/SD/VAT/AIT/AT) from `seed/hs_duty.json`
  is not built yet.

## Margin: `margin.py`
```
gross_profit       = revenue − landed_cost
gross_margin       = gross_profit / revenue        (None when revenue = 0)
markup             = gross_profit / landed_cost    (None when cost = 0)
break_even_price   = landed_cost / quantity
price_for_margin(m)= break_even_price / (1 − m),   0 ≤ m < 1
```
- **Band:** decided on the margin rounded to 2 dp in percent, so the colour always matches the number shown.
  healthy ≥ 15.00%, thin ≥ 8.00%, otherwise low.

## FX: `fx.py`
- A quote is `1 base = rate quote` (`fx_rates`, source `MOCK`). `rate(a, b)` tries, in order: identity,
  the direct quote, the inverse quote (1/rate), then a cross through USD.
- The service uses the latest `HISTORY` (not `FORECAST`) row per pair on or before DEMO_TODAY. Every response
  lists the quotes it used (`fx[]` with `as_of`).
- Each amount in a response is converted on its own from the full-precision value and then quantized.
  So converted lines can differ from the converted total by 0.01.

## Monthly summary: `summary.py`
- A deal counts in the month it was **opened**. DRAFT and CANCELLED deals are excluded.
- Report currency is the buyer's cash currency (USD for both demo buyers).
```
purchases          = Σ goods value
landed             = Σ landed cost
average_margin     = Σ gross profit / Σ expected revenue     (revenue-weighted)
top_cost_driver    = extra-cost kind with the largest Σ; share = Σ kind / Σ all extras
purchases_change   = purchases(m) − purchases(m−1); ratio = change / purchases(m−1) (None if 0)
margin_change_pts  = average_margin(m) − average_margin(m−1)
history            = the 6 months ending at m, oldest first
```

## Supplier scorecard: `scorecard.py`
Window: the last 6 monthly `supplier_scores` rows, which are network-wide. The monthly score formula is in
`seed/scores.py`.
```
on_time_rate = Σ(on_time_rate_m × deals_m) / Σ deals_m
defect_rate  = Σ(defect_rate_m × deals_m) / Σ deals_m
dispute_rate = Σ disputes_m / Σ deals_m
score        = latest monthly score (0–100)
price_index  = 100 × Σ landed cost / Σ goods value over committed deals (USD); 100 = no extra costs
```
- A supplier is **weak** when any flag is set: `KYB_NOT_VERIFIED` (KYB ≠ VERIFIED), `LOW_SCORE` (< 70),
  `HIGH_DISPUTE_RATE` (> 10%) or `LOW_ON_TIME` (< 80%).

## Explanations: `narrative.py`
- Deterministic EN + BN templates with stable `code`s:
  - Order: `LARGEST_EXTRA_COST`, `EXTRA_COSTS_TOTAL`, `GROSS_MARGIN` / `NO_SELLING_PRICE`, `BREAK_EVEN`, `FX_RATES_USED`.
  - Monthly: `MONTH_VOLUME`, `MONTH_CHANGE`, `MONTH_MARGIN_DRIVER`.
  - Supplier: `FLAG_*`, `SUPPLIER_OK`.
- BN text uses Bengali digits. Shares are shown with 1 dp and margins with 2 dp. The agent (Phase 3.x) may
  rephrase these sentences but never recompute the numbers.

## Worked example: SETU-2026-0001 (DEMO_TODAY 2026-10-20)
| Item | Value |
|---|---|
| Goods | 8,000 m × USD 1.20 = 9,600.00 (85.71%) |
| Extras | freight 600.00 (5.36%) · insurance 50.00 (0.45%) · duty 800.00 (7.14%) · bank 150.00 (1.34%) = 1,600.00 |
| Landed cost | **11,200.00** = BDT 1,373,008.00 at USD/BDT 122.59 = CNY 79,508.80 at USD/CNY 7.099 |
| Cost per unit / break-even | **1.40** |
| Expected revenue | 13,660.00 (1.7075 per m) |
| Gross margin | 2,460.00 = **18.01%** (healthy) · markup 21.96% |
| Price for a 20% margin | 1.40 / 0.80 = 1.75 per m |

## Cash-flow forecast: `cashflow.py` (FR-2)
```
closing(d)   = opening(d) + inflows(d) − outflows(d)
opening(d+1) = closing(d);   opening(today) = buyer cash_balance
```
- The window is today … today + 90, inclusive (91 days). Weekly buckets are 7-day blocks starting today.
- The balance *available* for a payment on day D is `opening(D)`, as in the seed rule (`seed/cashflow.py`).
- `running_balance(opening, deltas)` is the reference implementation, and tests compare the API against it.
- **Sources** (`app/services/cashflow.py`), all converted to the buyer's cash currency:
  - Unlinked `cashflow_items` dated today or later.
  - Tranches of FUNDED, IN_PRODUCTION and SHIPPED deals that are beyond `escrow.funded_total` and not
    RELEASED, REFUNDED or CANCELLED, on their due date.
  - `deal_costs` on their due date.
  - The seed's linked `cashflow_items` copies of the last two are skipped.
- **What-if:** `apply_scenario` moves or removes flows by `ref` and adds loan inflows, each with an
  optional repayment. It never saves. `cover_amount = max(0, min_buffer − lowest closing)`.

## Alert rules: `alerts.py` (FR-2)
| Type | Trigger | Severity | Amount |
|---|---|---|---|
| SHORTFALL | first day `closing(d) < min_buffer` (default 0) | CRITICAL if ≤ 7 days away, else WARNING | `min_buffer − closing(d)` |
| DEADLINE: milestone | unfunded tranche; action window 14 days, notice window 30 days | CRITICAL ≤ 1 day · WARNING ≤ action window · INFO ≤ notice window | tranche |
| DEADLINE: customs duty | DUTY cost; windows 7 / 60 | as above | duty |
| DEADLINE: bill of entry | arrival milestone + 1 day; windows 7 / 60 | as above | — |
| DEADLINE: loan instalment | LOAN_REPAYMENT item; windows 7 / 7 | as above | instalment |
| FX_OPPORTUNITY | next tranche of each deal paid into a non-BDT, non-cash-currency account: the cheapest `<ccy>/BDT` day before it (history today plus mock forecast) is more than 1% below the 30-day mean | INFO | saving ≈ payment × (mean − rate), in BDT |

- **Keys:** `alert:<party>:<type>:<reference>:<date>`, with id = uuid5 of the key.
- **Upsert:** a re-run inserts new keys and updates changed rows only. A milestone DEADLINE alert is
  dropped when the SHORTFALL alert is about that same payment.
- **Auto-resolve:** an engine alert whose key is no longer produced becomes RESOLVED (`resolved_by=engine`).
  It reopens if the condition returns. A user-resolved alert stays closed.
- **Golden (Rahima):** SHORTFALL on 2026-11-07 for **1,560.00**. The balance is 4,200.00 against milestone 2
  of 5,760.00, so it is WARNING (18 days away). FX: CNY/BDT 16.9682 on 2026-10-22 against a mean of
  17.2865 (−1.8%) gives a saving of ≈ BDT 13,014.68 on milestone 2.

## Financing: `financing.py` (FR-1)
**Gap**
- **Shortfall mode:** amount = `min_buffer − closing` on the first day below the buffer, i.e. the P06
  forecast shortfall. `needed_by` is that day. `recover_on` is the next day the closing balance is at or
  above the buffer, and `needed_for_days` = recover_on − needed_by. `peak` is the deepest deficit before
  recovery. Demo: 1,560.00 on 2026-11-07, recovering 2026-11-19 (12 days), peak 2,160.00 on 2026-11-08
  (freight).
- **Order mode:** amount = `max(0, landed cost − available cash)`, needed from today until milestone 3 is
  released. Release = arrival milestone + `CLEARANCE_DAYS` (5), matching duty due 5 days after arrival.
  Demo: 11,200 − 6,000 = **5,200.00** for 45 days.

**Tenor**
- A fixed tenor uses that tenor.
- `UNTIL_MILESTONE_3` runs from the start to the milestone-3 release, capped at `tenor_days_max`.
- A ranged line (min < max) is **priced at its maximum tenor** (product rule chosen for TC-09).

**Cost on principal P over d days**
- interest = P × annual_rate × d/365
- fees = P × fee_rate + fee_fixed
- uplift = P × price_uplift_rate
- flat = P × flat_cost_rate
- total = interest + fees + uplift + flat
- per 30 days = total × 30/d
- effective annual rate = (1 + total/P)^(365/d) − 1, capped at 999,900%

**Eligibility**
- The option's JSON rule tree (`eq`, `gte`, `lte`, `in` over the facts listed in `seed/financing.py`).
- Plus code rules: `MIN_AMOUNT`, `MAX_AMOUNT`, `TENOR_FITS` (tenor ≥ needed days), and
  `NOT_WITH_FUNDED_ESCROW`. That last rule means insured open-account terms replace escrow, so they are
  not offered once the deal's escrow is funded (product rule chosen for TC-09).

**Ranking:** eligible first, then lowest total cost, then shorter tenor, then fewer conditions (rules + 1
if there is collateral), then code.

**Top pick:** `why_codes` from `LOWEST_COST`, `NO_COLLATERAL`, `USES_ESCROW`, `NO_INTEREST` and
`MATCHES_DEAL_TIMELINE`; `saving_vs_next` = total of the next eligible option − total of the pick.

**Schedule:** one bullet repayment of P + total at start + d.

**Impact:** the P06 forecast with the loan inflow on the start day and the repayment at maturity. It
reports whether the original shortfall is covered, any shortfall that remains, and new shortfalls on days
that were ≥ 0 before.

| Option | Order mode: 5,200 | Shortfall mode: 1,560 |
|---|---|---|
| Escrow-backed loan (9%, USD 40, until milestone 3) | **97.70** (45 d), rank 1 | 50.39 (27 d), rank 2 |
| Supplier credit (2% uplift, 60 d) | **104.00**, rank 2 | **31.20**, rank 1 |
| Bank import loan (11.5%, 0.5% fee, 90 d, min 2,000) | **173.45**, rank 3 | ineligible (min amount) |
| NBFI line (14%, 30–120 d, priced at 120) | 239.34, rank 4 | 71.80, rank 3 |
| Insured terms (1.2% flat, 90 d, min 3,000) | ineligible (escrow funded) | ineligible (min amount, escrow funded) |
