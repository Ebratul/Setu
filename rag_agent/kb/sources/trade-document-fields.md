---
id: trade-document-fields
title: Trade document fields and cross-checks
source_type: glossary
original_reference: "Setu's own summary of common import trade documents; no single official source. Check customs and AD bank requirements."
language: en
last_reviewed: 2026-10-17
disclaimer: "Simplified summary for demo — verify with the official source."
---
# Trade document fields and cross-checks

An import deal produces several documents. Setu reads them and checks that key facts agree. This page explains what each document usually contains.

## Proforma invoice

A proforma invoice is the supplier's offer before the order is final. It usually shows the seller and buyer names, goods description, quantity, unit price, total value and currency, Incoterm, payment terms, expected shipment date and bank details of the supplier. The importer often uses it to open a payment, apply for financing or ask the bank for approval.

## Commercial invoice

The commercial invoice is the bill for the goods actually shipped. It shows seller, buyer (consignee), invoice number and date, goods description, HS code, quantity, unit price, total value, currency, Incoterm and country of origin. Customs uses it to assess duty, so it must be accurate.

## Packing list

The packing list describes how goods are packed. It shows packages, quantity per package, net weight, gross weight, volume and marks and numbers (the labels on cartons). Net weight is goods only. Gross weight includes packing.

## Bill of lading

The bill of lading (B/L) is issued by the shipping line or its agent. It is a receipt for the cargo, a contract of carriage and, if negotiable, a document of title. It shows shipper, consignee, notify party, vessel and voyage, B/L number, port of loading, port of discharge, description, packages, gross weight, container number and the on-board date. In Setu, the bill of lading is key evidence for releasing the shipment milestone.

## Certificate of origin

The certificate of origin states the country where goods were made. It is issued by an authorised body in the exporting country. It shows exporter, consignee, goods description, HS code or description, quantity and origin. It may support duty treatment.

## Bill of entry

The bill of entry is the import declaration filed with Bangladesh Customs. It lists importer, goods, HS code, value, quantity, weight and duty. Importers use it to match advance payments with goods imported through the AD bank.

## Fields that must match across documents

Setu compares these fields across documents:

- Party names: seller, buyer and consignee must be the same legal entities.
- Quantity: pieces or units must agree.
- Gross and net weight: must agree between packing list and bill of lading.
- Value and currency: invoice total and currency must agree with the order and payment.
- HS code: the product classification code must agree.
- Goods description: must describe the same goods.
- Vessel, voyage and B/L number: must agree wherever they appear.
- Ports of loading and discharge: must agree.
- Dates: invoice date, shipment date and on-board date must be in a sensible order.
- Marks and numbers: carton labels and container numbers must agree.

Small formatting differences are normal. A real difference in a key field needs review.

## Common red flags

- Name mismatch, for example consignee on the bill of lading differs from the buyer on the invoice.
- Weight or quantity mismatch between invoice, packing list and bill of lading.
- Altered dates, such as an on-board date after the claimed arrival.
- Duplicate documents: the same invoice or bill of lading used to get financing from two lenders. Setu keeps a hash registry to detect this.
- Hidden text, such as white or tiny text in a PDF, that a reader cannot see.
- Instructions inside documents: text that tells the reader to pay, to move money, or to set earlier rules aside.

## How Setu treats document text

Setu treats text in a document or email as data, never as instructions. If a document contains an instruction-like phrase, Setu does not follow it. The finding is logged and the action is escalated to Tier 3, which needs a one-time password (OTP) and a 10-minute cooling-off. A human then decides.
