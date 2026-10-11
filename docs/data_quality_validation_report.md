# CallVerse Phase 1B ? Data Quality Validation Report

## Scope and method

This report summarizes validation checks on the seven priority Olist CSVs in `data/raw/olist`. Counts below were calculated from the repository files using the checks defined in `notebooks/02_data_quality_validation.ipynb`. The notebook's code cells could not be run in this environment because pandas is unavailable; the CSV checks were therefore reproduced with Python's standard CSV and datetime libraries. Timestamps were parsed as ISO date-times, and missing CSV fields were treated as missing. The raw files were read only.

The report distinguishes observations from confirmed defects. Olist represents e-commerce orders; it is not a record of customer contacts.

## Dataset inventory

| Table | Rows | Columns |
|---|---:|---:|
| Orders | 99,441 | 8 |
| Order items | 112,650 | 7 |
| Customers | 99,441 | 5 |
| Payments | 103,886 | 5 |
| Reviews | 99,224 | 7 |
| Products | 32,951 | 9 |
| Sellers | 3,095 | 4 |

## Key findings

### Missing values

- Orders have no missing purchase timestamps, estimated delivery dates, order IDs, customer IDs, or statuses. Approval time is missing for **160** orders (0.16%); carrier handoff time is missing for **1,783** (1.79%); actual customer delivery time is missing for **2,965** (2.98%). Missing delivery milestones can be expected for orders that have not completed delivery or were canceled.
- Reviews have no missing order IDs, review IDs, or scores. Review comment titles are absent for **87,656 of 99,224** rows (88.34%); comment messages are absent for **58,247** (58.70%). These are optional text fields, not evidence that review records are unusable.
- Products have **610** rows (1.85%) missing category and the related name/description/photograph attributes. Weight and each dimension are missing in **2** rows (0.01%).
- The item, customer, payment, and seller tables have no missing values in the loaded CSV fields.

### Duplicates and identifier uniqueness

- No exact duplicate rows were found in any of the seven tables.
- `order_id` is unique in Orders (99,441 distinct IDs). `customer_id` is unique in Customers (99,441); `product_id` is unique in Products (32,951); and `seller_id` is unique in Sellers (3,095).
- The composite key (`order_id`, `order_item_id`) is unique across all 112,650 item rows. There are 23,787 rows whose `order_id` occurs multiple times, which is expected because an order can contain multiple item lines.
- `review_id` repeats in 1,603 review rows (814 repeats beyond the first occurrence). This should be checked before treating it as a unique review-record key or using it as a join key. The records were not removed.
- Customers may place multiple orders; repeated order IDs in payment/review records can also reflect table granularity. Those repeated identifiers are not equivalent to exact duplicate rows.

### Referential integrity and coverage

| Relationship / coverage check | Result |
|---|---:|
| Orders ? Customers, unmatched customer references | 0 of 99,441 |
| Order items ? Orders, unmatched order references | 0 of 112,650 |
| Order items ? Products, unmatched product references | 0 of 112,650 |
| Order items ? Sellers, unmatched seller references | 0 of 112,650 |
| Payments ? Orders, unmatched order references | 0 of 103,886 |
| Reviews ? Orders, unmatched order references | 0 of 99,224 |

The tables therefore have complete parent-key coverage for the checked, non-missing identifiers. There are 775 orders without item rows, 1 without a payment row, and 768 without a review row. Those are coverage observations, not automatic defects: a review is not expected for every order, and order status/lifecycle may explain absent item or payment records.

### Timestamps and order status

All non-empty values in the five order milestone columns parsed successfully. Of records with both timestamps present:

| Chronology check | Compared rows | Reversed order |
|---|---:|---:|
| Purchase after approval | 99,281 | 0 |
| Approval after carrier handoff | 97,644 | 1,359 |
| Customer delivery before carrier handoff | 96,475 | 23 |
| Customer delivery before purchase | 96,476 | 0 |

The approval/carrier and carrier/delivery exceptions warrant review; timestamp ordering alone does not establish which field is wrong. There were no negative purchase-to-delivery durations. Actual delivery was later than the estimated date in **7,827** rows where both dates were present; this is a late-delivery indicator, not an invalid timestamp. The comparison spans records with actual delivery dates, regardless of status, so inspect status alongside it before using it as a delay feature.

Observed statuses were:

| Status | Orders | Share |
|---|---:|---:|
| delivered | 96,478 | 97.02% |
| shipped | 1,107 | 1.11% |
| canceled | 625 | 0.63% |
| unavailable | 609 | 0.61% |
| invoiced | 314 | 0.32% |
| processing | 301 | 0.30% |
| created | 5 | 0.01% |
| approved | 2 | <0.01% |

Of delivered-status orders, **8** lack the customer delivery timestamp; 2 lack the carrier handoff timestamp. Of canceled orders, **6** have a customer delivery timestamp and 75 have a carrier handoff timestamp. These small status/timestamp inconsistencies deserve contextual review rather than automatic deletion or recoding.

## Implications for CallVerse

Order IDs and the principal customer/product/seller links are reliable for the checked joins. Review IDs need additional investigation if used as unique keys. Actual and estimated delivery dates are broadly available, but missing milestones and the 23 reversed carrier/delivery pairs need careful handling. The 1,359 approval-to-carrier reversals also matter when reconstructing a delivery timeline. Predictive features must use only events observable at the simulated contact time; actual delivery outcomes are future information for an earlier inquiry.

Olist does not contain actual contact events, contact reasons, agent assignments, call durations, queue waits, or abandonment records. It cannot directly establish that a customer contacted support after a delay or cancellation. Future contact-demand estimates require a transparent contact-generation process or explicit assumptions, which should be documented and tested.

## Recommended next step

Phase 1B has identified issues and coverage patterns but has not cleaned or imputed values. Phase 1C ? Data Cleaning and Preparation ? should decide how to handle the review key, timestamp exceptions, missing delivery milestones, product attributes, and orders without associated item/payment rows. Preserve source values and document each decision so that the CallVerse dataset remains auditable.
