---
id: financing-glossary
title: Financing glossary and how Setu ranks options
source_type: glossary
original_reference: "Setu mock financing catalogue (services/agent/seed/financing.py); all providers are fictional"
language: en
last_reviewed: 2026-10-17
disclaimer: "Simplified summary for demo — verify with the official source. Providers and terms are fictional."
---
# Financing glossary and how Setu ranks options

The financing gap is the money you are short for an order: order cost plus landed costs, minus available cash and expected inflows before the due date. Setu compares financing options to cover that gap. The providers below are fictional demo data.

## Supplier credit

Supplier credit means the supplier lets you pay later. In the demo catalogue, Shaoxing Huaxin offers a 60-day option: 0% interest, but goods are priced 2% higher, and you pay 60 days after shipment. There is no collateral. It requires a verified supplier and at least one completed deal with that supplier. The cost is hidden in the price, so compare it with other options.

## Bank import loan

A bank import loan is a loan from a bank to pay for imports. The demo option from Meghna Commercial Bank has 11.5% a year, a 0.5% processing fee and a 90-day tenor. The amount range is USD 2,000 to USD 50,000. Collateral is a lien on the imported goods plus a post-dated cheque. It requires a verified buyer and at least 12 months of trading.

## Escrow-backed order loan

An escrow-backed order loan is secured by the funded escrow tranches. The demo option from Setu Partner Finance has 9.0% a year plus a flat USD 40 fee. It is repaid when milestone 3 is released, up to 120 days. The amount range is USD 500 to USD 30,000. Collateral is an assignment of the funded escrow tranches. The escrow must be funded and the supplier verified.

## Export-credit-insured supplier terms

Here the supplier ships on open account, meaning you pay later, and the supplier's export-credit insurance covers non-payment. The demo option from Silk Route Cover is 90 days with about 1.2% flat cost passed on. The minimum is USD 3,000. It requires at least two completed deals with the supplier and a verified supplier. Collateral is the supplier's insurance policy.

## NBFI working-capital line

An NBFI is a non-bank financial institution. A working-capital line gives cash for day-to-day needs. The demo option from Shitalakshya Capital charges 14% a year on the drawn amount, for 30 to 120 days, with no invoice needed. The amount range is USD 1,000 to USD 25,000. Collateral is the proprietor's personal guarantee. It requires a verified buyer and at least 12 months of trading.

## Effective annual rate

Effective annual rate means the yearly cost of money so you can compare options. A flat fee or price markup is not a yearly rate. To compare, take the total extra cost, divide it by the amount financed, and scale it to a year by the number of days of credit. A shorter credit period makes the same flat percentage cost more per year. Setu calculates this in deterministic code and shows total cost in BDT as well.

## Collateral, tenor and eligibility

- Collateral is what the lender can claim if you do not repay.
- Tenor is how long the money is borrowed.
- Eligibility is the set of rules you must meet, such as verified status, trading history or a funded escrow.
- Conditions are other terms such as fees, minimum amount and repayment trigger.

An option you are not eligible for is shown as ineligible with the reason.

## How Setu ranks options

Setu ranks financing options by fixed rules in code. The AI only explains the result.

1. Eligible options come first.
2. Among eligible options, lower total cost ranks higher.
3. Then a shorter tenor ranks higher.
4. Then fewer conditions rank higher.

The ranking is a decision aid, not an offer. Real lenders decide on their own terms.
