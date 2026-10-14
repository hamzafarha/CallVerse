---
doc_id: cancellations_and_order_changes
title: Cancellations and Order Changes
doc_type: policy
version: 1
intents: [cancel_order, change_order]
---

# Cancellations and Order Changes

Synthetic policy for the CallVerse store. Statuses follow the Olist order lifecycle; time
limits are explicit assumptions.

## When an order can be canceled
<!-- intents: cancel_order -->

| Order status | Can the customer cancel? | How |
|---|---|---|
| created, approved, processing | Yes, free of charge | "Cancel order" button in "My orders", or ask an advisor |
| invoiced | Yes, through an advisor only | The advisor asks the seller to stop the shipment; not guaranteed |
| shipped | No | Refuse the delivery, or return it after receipt (see Returns and Exchanges) |
| delivered | No | Use the 7-day right of withdrawal (see Returns and Exchanges) |

## What happens after a cancellation
<!-- intents: cancel_order -->

- The customer receives a cancellation e-mail.
- Unpaid boleto: nothing to refund; the boleto simply expires.
- Paid orders: the refund starts automatically. Timing depends on the payment method (see the Refund Policy).
- If only some items of a multi-seller order are canceled, only those items are refunded.

## Orders canceled by the store or the seller
<!-- intents: cancel_order -->

An order can be canceled without the customer asking, when:

- the boleto was not paid within 3 days;
- the card payment was declined or failed the fraud check;
- the seller has no stock (status "unavailable").

The customer is informed by e-mail and receives a full refund of anything paid. If the
customer still wants the product, they must place a new order.

## Changing the delivery address
<!-- intents: change_order -->

- Possible while the order is "created", "approved" or "processing". The advisor updates the address after verifying the customer's identity.
- Not possible once the order is "invoiced" or later, because the invoice and shipping label carry the address. The customer can cancel (if allowed) and order again.

## Changing products, size, colour or quantity
<!-- intents: change_order -->

Items in a placed order cannot be swapped or added. The customer should cancel the order
(if the status allows it) and place a new one. If the order is already shipped, the
customer can receive it and request an exchange (see Returns and Exchanges).

## Changing the payment method
<!-- intents: change_order -->

The payment method cannot be changed after the order is placed. If a boleto has not been
paid, the customer can let it expire (the order is canceled after 3 days) and order again
with another payment method.
