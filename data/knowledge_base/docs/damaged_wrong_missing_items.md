---
doc_id: damaged_wrong_missing_items
title: Damaged, Wrong, Missing or Defective Items
doc_type: policy
version: 1
intents: [damaged_delivery, wrong_item, missing_item, product_issue]
---

# Damaged, Wrong, Missing or Defective Items

Synthetic policy for the CallVerse store. Multi-seller shipping reflects the Olist data;
time limits and procedures are explicit assumptions.

## Damaged parcel or damaged product
<!-- intents: damaged_delivery -->

- If the packaging is visibly crushed, torn or wet, the customer should refuse the delivery. The parcel goes back to the seller and the customer gets a re-shipment or full refund.
- If the damage is found after opening, the customer reports it within 7 days of delivery, with photos of the product, the packaging and the shipping label.
- The advisor offers a free replacement or a full refund (product and shipping). The damaged item is returned with a prepaid label, unless the seller decides it is not worth returning.

## Wrong item received
<!-- intents: wrong_item -->

1. Ask for a photo of the item received and of the shipping label.
2. Compare with the order: product, size, colour and quantity.
3. If the item is wrong, offer the correct item (shipped once the wrong one is scanned at the post office) or a full refund.
4. Return shipping is free. The customer must not use the wrong item.

## Missing item in an order
<!-- intents: missing_item -->

Before reporting an item as missing, check:

- **Multi-seller orders ship in several parcels.** Each seller sends its own parcel, often on different days. Check in "My orders" whether another parcel is still on its way.
- The quantity ordered and the packing list inside the parcel.
- Whether the item was canceled as "unavailable" (the customer would have received an e-mail and a refund).

If the item really is missing, the customer reports it within 7 days of delivery. The advisor
asks the seller to confirm what was packed, then offers re-shipment of the missing item or a
refund for it.

## Product defective or not working
<!-- intents: product_issue -->

1. Collect a description of the problem, photos or a short video, and the delivery date.
2. Within 7 days of delivery: offer a free return with full refund, or a replacement.
3. After 7 days but within the legal defect period (30 days non-durable, 90 days durable): the seller arranges a repair or replacement. If not solved within 30 days, the customer can choose a refund.
4. Products with a manufacturer warranty: give the customer the manufacturer's service contact as well.

## Product different from the description
<!-- intents: product_issue, wrong_item -->

If the product works but does not match the listing (different material, size, features), it
is treated like a wrong item: free return and a refund or the correct product. Ask for photos
and note which part of the listing is wrong so the seller can fix the listing.
