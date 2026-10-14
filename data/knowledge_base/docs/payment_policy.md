---
doc_id: payment_policy
title: Payments and Payment Problems
doc_type: policy
version: 1
intents: [payment_issue]
---

# Payments and Payment Problems

Synthetic policy for the CallVerse store. Payment methods, installment limits and approval
times are measured on the Olist payments data; the procedures are assumptions.

## Accepted payment methods
<!-- intents: payment_issue -->

| Method | Installments | Payment confirmation |
|---|---|---|
| Credit card | 1 to 24 installments | Usually within minutes; up to 24 hours if under review |
| Boleto bancário | Single payment only | 1 to 3 business days after the customer pays it |
| Debit card | Single payment only | Usually within an hour |
| Voucher | Can be combined with another method | Immediate |

In the Olist data, card payments are approved in about 20 minutes (median), while boletos
take about 29 hours after the order.

## Card payment declined
<!-- intents: payment_issue -->

- The order stays in "created" and the customer receives an e-mail asking to pay again.
- Common causes: insufficient limit, wrong card details, or the bank blocking an online purchase. The customer should contact their bank; the store does not see the bank's reason.
- The customer can retry within 24 hours from "My orders". After that, the order is canceled and nothing is charged.

## Charged twice or charged for a canceled order
<!-- intents: payment_issue -->

- A declined or canceled card payment can leave a pre-authorisation on the card. It is not a charge and disappears within 5 business days.
- If two real charges appear, the advisor checks the payment record. A confirmed duplicate charge is refunded within 2 business days of confirmation, then follows the card refund timing.
- Ask the customer for a screenshot of the statement line (amount, date, merchant name).

## Boleto problems
<!-- intents: payment_issue -->

- The boleto is valid for 3 days. After that it cannot be paid and the order is canceled automatically.
- If the customer paid but the order still shows "created" after 3 business days, ask for the payment receipt and escalate to the payments team.
- A paid boleto that arrives after the order was canceled is refunded by bank transfer (see the Refund Policy).

## Amount charged differs from the order total
<!-- intents: payment_issue -->

- Check whether the customer paid in installments (the statement shows one installment, not the total) or combined a voucher with a card.
- Installment plans may include interest, shown at checkout.
- If the amount is still different, collect the statement line and the order number and escalate to the payments team.

## Vouchers
<!-- intents: payment_issue -->

Vouchers can be used alone or with another payment method, cannot be exchanged for cash, and
show their expiry date in the customer account. An expired voucher cannot be reactivated,
except when it was issued as compensation and expired within the last 30 days.
