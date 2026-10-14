---
doc_id: delivery_times_and_delays
title: Delivery Times and Delays
doc_type: policy
version: 1
intents: [delivery_time, delivery_issue, track_delivery]
---

# Delivery Times and Delays

Synthetic policy for the CallVerse store. Delivery durations are measured on the Olist
orders; compensation rules are explicit assumptions.

## How the estimated delivery date is set
<!-- intents: delivery_time -->

The estimated delivery date is shown at checkout and in the order confirmation e-mail. It
depends on the seller's location, the customer's address and the carrier. The estimate is
deliberately cautious: in the Olist data the promised time is about 24 days (median), while
half of all orders actually arrive within about 10 days and 9 in 10 within about 23 days.
Only about 7% of orders arrive after the estimated date.

Advisors must quote the estimated date shown on the order. They must not promise an earlier
date, even if most orders arrive early.

## Can delivery be sped up or scheduled?
<!-- intents: delivery_time -->

- Delivery cannot be upgraded to express after the order is placed.
- Carriers do not offer a chosen delivery day or time slot.
- If the customer will be away, they can ask a neighbour or building reception to receive the parcel, or wait for the carrier's second attempt (see "Failed delivery attempt").

## Order late: estimated date has passed
<!-- intents: delivery_time, delivery_issue, track_delivery -->

When the estimated delivery date has passed and the order is not delivered:

1. Check the tracking events. If the parcel moved in the last 3 business days, it is on its way: apologise, give the latest tracking event and ask the customer to wait 3 more business days.
2. If there is no tracking movement for 5 business days, or the delay is more than 7 days, open a carrier investigation. The investigation takes up to 5 business days.
3. If the carrier confirms the parcel is lost, offer the customer the choice of a free re-shipment or a full refund (product and shipping).

When late orders arrive, the median delay in the Olist data is about 7 days; 1 in 4 late orders
is more than 13 days late.

## Compensation for late delivery
<!-- intents: delivery_issue, delivery_time -->

- Delivered more than 7 days after the estimated date: the customer may receive a voucher equal to the shipping fee paid, on request.
- Never delivered and confirmed lost: full refund or free re-shipment, at the customer's choice.
- Advisors may issue vouchers up to R$ 30 themselves. Larger amounts need a supervisor (see the Advisor Playbook).

## Failed delivery attempt or wrong address
<!-- intents: delivery_issue -->

- The carrier makes up to 3 delivery attempts on different business days, then returns the parcel to the seller.
- If the parcel is returned to the seller, the order is canceled and fully refunded, or re-shipped at the customer's request once the address is confirmed.
- The delivery address cannot be changed once the order is "shipped". Before that, see Cancellations and Order Changes.
- If the address on the order is incomplete, the customer should contact support before the order is shipped so the advisor can correct it.

## Parcel marked delivered but not received
<!-- intents: delivery_issue, track_delivery -->

1. Ask the customer to check with neighbours, reception and household members, and to look at the delivery proof (name and time) on the tracking page.
2. If the parcel is still missing after 2 days, open a carrier investigation (up to 5 business days).
3. If the carrier cannot prove delivery, the customer receives a re-shipment or a full refund.
