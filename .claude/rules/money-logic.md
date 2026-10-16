---
paths:
  - "services/agent/app/domain/**"
  - "services/agent/app/services/**"
  - "services/agent/**/*money*"
  - "services/agent/**/*fx*"
  - "services/agent/seed/**"
---

# Money logic rules

- **All money math is deterministic Python in `app/domain/`.** The LLM never calculates; it only explains returned numbers.
- **No floats for money.** Use `decimal.Decimal` constructed from strings (`Decimal("12.50")`, never `Decimal(12.5)`).
  Set context once in `app/domain/money.py` (`getcontext().prec = 28`).
- Represent amounts as `Money(amount: Decimal, currency: Literal["BDT","USD","CNY"])` (frozen pydantic model / dataclass).
  Adding different currencies raises; convert explicitly via `fx.convert(money, to, rate)`.
- Storage: Postgres `NUMERIC(20,4)` for amounts, `NUMERIC(20,8)` for FX rates; currency in a separate `CHAR(3)` column.
- API: amounts serialised as strings (`"12500.00"`), with currency; the frontend formats but never computes.
- Rounding: keep full precision through a calculation; quantize only at boundaries (display, ledger posting) with
  `ROUND_HALF_UP` — BDT/USD/CNY to 2 dp. Ledger postings must balance exactly (sum of debits == sum of credits).
- Rates: `FxRate(base, quote, rate, source, as_of)`; always record which rate (and timestamp) a result used. Mock data
  in `seed/fx.py` (rows in `fx_rates`, source `MOCK`). Spread/fees are explicit line items, never baked into the rate.
- Interest/financing: total cost = interest + fees + FX cost + opportunity cost if specified; effective annual rate via
  `(1 + period_cost/principal) ** (365/days) - 1` computed with Decimal (`Decimal.__pow__` with integer-ish exponents, or
  `ln/exp` from Decimal). Tenor in days. Document every formula in the function docstring.
- Duty/tax: rates per HS code from `seed/hs_duty.json` (CD, RD, SD, VAT, AIT, AT) with a "simplified, for demo" note.
- Percentages are `Decimal` fractions (`Decimal("0.30")`), displayed ×100.
- Milestone splits must sum to exactly 1.00; last tranche absorbs rounding remainder.
- Every function returns its explanation facts (`list[str]` of the inputs and formula used) for the explainer.
- Tests: property tests (Hypothesis) for conservation (splits sum, ledger balances), golden tests for one worked example per function.
