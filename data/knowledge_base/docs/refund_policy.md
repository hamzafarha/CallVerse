---
doc_id: refund_policy
title: Refund Policy
doc_type: policy
version: 1
intents: [request_refund, refund_status]
---

# Refund Policy

Synthetic policy for the CallVerse store. Payment methods are those found in the Olist
data (credit card, boleto, voucher, debit card); refund timings are explicit assumptions.

## When a customer is entitled to a refund
<!-- intents: request_refund -->

- Order canceled before shipping, by the customer, the store or the seller.
- Product returned within the 7-day right of withdrawal.
- Product defective, damaged, wrong or missing, when the customer prefers a refund to a replacement.
- Parcel confirmed lost by the carrier.

Refunds cover the product price. Shipping is also refunded when the order is canceled, lost,
or when the problem is the store's or seller's fault (defect, damage, wrong item).

## How to request a refund
<!-- intents: request_refund -->

1. Canceled orders are refunded automatically; no request is needed.
2. For returns, the customer starts a return in "My orders". The refund is approved when the seller receives and checks the product, within 3 business days of receipt.
3. For damaged, wrong or missing items, the advisor can approve the refund directly from the photos and the order record (see Damaged, Wrong or Missing Items).

## Refund timing by payment method
<!-- intents: refund_status, request_refund -->

Counted from the day the refund is approved:

| Payment method | How the money comes back | Time |
|---|---|---|
| Credit card | Reversal on the card | Shows on the next 1 or 2 card statements |
| Card in installments | All installments are reversed, including future ones | Next 1 or 2 statements |
| Debit card | Back to the bank account linked to the card | 5 to 10 business days |
| Boleto | Bank transfer to an account in the customer's name | Up to 10 business days after the customer gives their bank details |
| Voucher | A new voucher with the same value | Within 2 business days |

Orders paid with several methods (for example voucher plus card) are refunded to each method
in proportion to what was paid with it.

## Checking the status of a refund
<!-- intents: refund_status -->

- The refund status is shown in "My orders": "refund requested", "refund approved" or "refund paid".
- Once approved, the customer gets an e-mail with the amount and the expected date.
- For credit cards, the reversal may appear as a separate credit line rather than reducing the original charge. Ask the customer to check the next statements before escalating.
- If the expected date has passed, the advisor checks the refund record, sends the customer the transaction reference and escalates to the payments team.

## Refunds for boleto payments
<!-- intents: refund_status, request_refund -->

A boleto cannot be reversed. The customer must provide the bank, branch, account number and
the account holder's CPF; the account must be in the name of the person who placed the
order. Refunds wait until these details are complete, so ask for them in the same contact.
