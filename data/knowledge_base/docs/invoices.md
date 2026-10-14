---
doc_id: invoices
title: Invoices (Nota Fiscal Eletrônica)
doc_type: policy
version: 1
intents: [request_invoice]
---

# Invoices (Nota Fiscal Eletrônica)

Synthetic policy for the CallVerse store. The "invoiced" status comes from the Olist order
lifecycle; the procedures are assumptions.

## When the invoice is issued
<!-- intents: request_invoice -->

Each seller issues an electronic invoice (NF-e) for its items before handing the parcel to
the carrier; the order status then changes to "invoiced". Orders from several sellers have
one invoice per seller.

## How to download the invoice
<!-- intents: request_invoice -->

1. Sign in and open "My orders", then select the order.
2. Choose "Invoice". Download the PDF (DANFE) or the XML file.
3. A copy is also attached to the "order shipped" e-mail.

## Invoice missing
<!-- intents: request_invoice -->

- If the order is not yet "invoiced", the invoice does not exist yet. It will be available when the order ships.
- If the order is "shipped" or "delivered" and no invoice is shown, the advisor asks the seller to send it. The seller has 2 business days. The advisor tells the customer it will arrive by e-mail.
- Canceled orders before invoicing have no invoice.

## Correcting an invoice or invoicing a company
<!-- intents: request_invoice -->

- The invoice is issued to the name and CPF (or CNPJ) given at checkout.
- Name or CPF/CNPJ cannot be changed after the invoice is issued. A company (CNPJ) invoice for an order placed with a CPF is not possible; the customer must order with the company account next time.
- Spelling errors in the address can be corrected by the seller with a correction letter (carta de correção) within 30 days.
