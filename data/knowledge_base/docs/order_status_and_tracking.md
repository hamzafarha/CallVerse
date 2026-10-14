---
doc_id: order_status_and_tracking
title: Order Status and Tracking
doc_type: policy
version: 1
intents: [track_order, track_delivery]
---

# Order Status and Tracking

Synthetic policy for the CallVerse store. Status names and typical durations come from
the Olist order data; everything else is an explicit assumption.

## What each order status means
<!-- intents: track_order -->

Every order moves through the same statuses. The customer sees them in "My orders".

| Status | Meaning | What the customer should expect |
|---|---|---|
| created | Order placed, payment not yet confirmed | Card payments confirm within minutes; boleto within 1 to 3 business days |
| approved | Payment confirmed | The seller starts preparing the order |
| processing | The seller is preparing the parcel | Usually 1 to 4 days |
| invoiced | The electronic invoice (NF-e) has been issued | The parcel is about to be handed to the carrier |
| shipped | The carrier has the parcel | A tracking code is available |
| delivered | The carrier confirmed delivery | Problems can be reported from this point |
| canceled | The order was canceled | Any payment taken is refunded (see the Refund Policy) |
| unavailable | The seller could not fulfil the order | Treated as a cancellation; full refund |

## How a customer can check where their order is
<!-- intents: track_order, track_delivery -->

1. Sign in and open "My orders", then select the order.
2. The page shows the current status and the estimated delivery date given at checkout.
3. Once the status is "shipped", a tracking code and a link to the carrier's tracking page appear.
4. Tracking events can take up to 24 hours to appear after the carrier picks up the parcel.

The customer also receives an e-mail at each status change: payment approved, invoice issued,
order shipped (with tracking code) and order delivered.

## Tracking code not working or not updating
<!-- intents: track_delivery -->

- A new tracking code may show "not found" for up to 24 hours after shipping. Ask the customer to try again the next day.
- If the code shows no movement for more than 5 business days, the advisor opens a carrier investigation (see Delivery Times and Delays).
- If the customer has no tracking code although the status is "shipped", the advisor can resend the shipping e-mail from the order screen.

## Order stuck in an early status
<!-- intents: track_order -->

- "created" for more than 3 business days with boleto: the boleto was probably not paid. Boletos expire 3 days after the order; the order is then canceled automatically and nothing is charged.
- "created" for more than 24 hours with a card: the payment may be under fraud review or declined. See the Payment Policy.
- "approved" or "processing" for more than 5 business days: the seller is late handing over the parcel. The advisor contacts the seller and tells the customer the new expected date. In the Olist data, about 9% of orders reached the carrier after the seller's shipping deadline.

## Orders with several parcels
<!-- intents: track_order, track_delivery -->

An order with items from more than one seller ships in separate parcels, each with its own
tracking code and possibly a different delivery date. "My orders" lists the parcels one by one.
The order is marked "delivered" only when every parcel has arrived.
