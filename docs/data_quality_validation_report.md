# CallVerse Phase 1B — Data Quality Validation Report

## Scope and method

This report summarizes validation checks on the seven priority Olist CSVs in `data/raw/olist`, plus the product-category translation table. All counts come from executing `notebooks/02_data_quality_validation.ipynb` top to bottom with pandas on the repository files. Timestamps were parsed as date-times, and missing CSV fields were treated as missing. The raw files were read only.

The report distinguishes observations from confirmed defects. Olist represents e-commerce orders; it is not a record of customer contacts.

**Revision note (11 October 2026).** This revision corrects three points of the original Phase 1B report: late delivery is now measured by calendar date (6,535 orders instead of 7,827), `customer_id` is described as a per-order identifier, and the repeated `review_id` values have been investigated. It also adds checks on review timestamps, payment values, payment totals and category translations.

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
| Category translation | 71 | 2 |

## Key findings

### Missing values

- Orders have no missing purchase timestamps, estimated delivery dates, order IDs, customer IDs, or statuses. Approval time is missing for **160** orders (0.16%); carrier handoff time is missing for **1,783** (1.79%); actual customer delivery time is missing for **2,965** (2.98%). Missing delivery milestones can be expected for orders that have not completed delivery or were canceled.
- Reviews have no missing order IDs, review IDs, or scores. Review comment titles are absent for **87,656 of 99,224** rows (88.34%); comment messages are absent for **58,247** (58.70%). These are optional text fields, not evidence that review records are unusable.
- Products have **610** rows (1.85%) missing category and the related name/description/photograph attributes. Weight and each dimension are missing in **2** rows (0.01%).
- The item, customer, payment, seller, and translation tables have no missing values.

### Duplicates and identifier uniqueness

- No exact duplicate rows were found in any table.
- `order_id` is unique in Orders (99,441 distinct IDs); `product_id` is unique in Products (32,951); `seller_id` is unique in Sellers (3,095).
- `customer_id` is unique in both Orders and Customers (99,441) because **Olist creates a new `customer_id` for every order**. The person behind an order is `customer_unique_id`: 96,096 distinct people, with 6,342 customer rows belonging to people who placed more than one order. Repeat-customer analysis must use `customer_unique_id`.
- The composite key (`order_id`, `order_item_id`) is unique across all 112,650 item rows. There are 23,787 rows whose `order_id` occurs multiple times, which is expected because an order can contain multiple item lines.
- `review_id` repeats in 1,603 review rows (789 distinct IDs; 814 repeats beyond the first occurrence). The composite key (`review_id`, `order_id`) is unique. See the next section.
- Repeated order IDs in payment and review records reflect table granularity and are not equivalent to exact duplicate rows.

### Repeated review identifiers

| Check | Count |
|---|---:|
| Repeated `review_id` values | 789 |
| …every copy points to a different order | 789 |
| …all copies have identical review content (score, title, message, dates) | 789 |
| …all orders belong to the same person | 789 |

The pattern indicates that **one review was attached to several orders of the same customer**. This is a hypothesis supported by the data, not confirmed by Olist documentation. The records were not removed; (`review_id`, `order_id`) is the appropriate record key. Separately, **547 orders have more than one review row**, so it must be decided which review counts before using reviews at order level.

### Referential integrity and coverage

| Relationship / coverage check | Result |
|---|---:|
| Orders → Customers, unmatched customer references | 0 of 99,441 |
| Order items → Orders, unmatched order references | 0 of 112,650 |
| Order items → Products, unmatched product references | 0 of 112,650 |
| Order items → Sellers, unmatched seller references | 0 of 112,650 |
| Payments → Orders, unmatched order references | 0 of 103,886 |
| Reviews → Orders, unmatched order references | 0 of 99,224 |

The tables therefore have complete parent-key coverage for the checked, non-missing identifiers. There are 775 orders without item rows, 1 without a payment row, and 768 without a review row. Those are coverage observations, not automatic defects: a review is not expected for every order, and order status/lifecycle may explain absent item or payment records.

Two further cross-table observations:

- **Payment totals:** of 98,665 orders with both items and payments, **249** have payments differing from item prices plus freight by more than 1 BRL (from −51.62 to +182.81 BRL, median +6.98). Mostly payments exceed the item total, which is consistent with instalment interest or vouchers but not provable from the data.
- **Category translation:** two product categories, `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos`, have no English translation; they cover **13** products.

### Timestamps and order status

All non-empty values in the five order milestone columns parsed successfully. Of records with both timestamps present:

| Chronology check | Compared rows | Reversed order |
|---|---:|---:|
| Purchase after approval | 99,281 | 0 |
| Approval after carrier handoff | 97,644 | 1,359 |
| Customer delivery before carrier handoff | 96,475 | 23 |
| Customer delivery before purchase | 96,476 | 0 |

The approval/carrier and carrier/delivery exceptions warrant review; timestamp ordering alone does not establish which field is wrong. There were no negative purchase-to-delivery durations.

**Late delivery.** All 99,441 estimated delivery dates are stored at `00:00:00`, i.e. they are calendar dates. Comparing them with the delivery *timestamp* counts an order delivered later on the estimated day as late. Compared by calendar date, actual delivery was later than the estimated date for **6,535** of 96,476 orders (6.77%). The timestamp comparison used in the original version of this report gives 7,827; the 1,292 difference are orders delivered on the estimated day. Lateness is a delivery-performance indicator, not an invalid timestamp. The comparison spans records with actual delivery dates regardless of status, so inspect status alongside it before using it as a delay feature.

**Review timestamps.** Both review date columns parsed for all 99,224 rows, and no review was answered before it was created. **64** reviews have a creation date earlier than their order's purchase date; **40** of them have a repeated `review_id`, which fits a review written for an earlier order being attached to a later one.

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

### Payment values

| Check | Payment rows |
|---|---:|
| Payment type `not_defined` | 3 |
| Payment value zero or negative | 9 |
| Zero instalments | 2 |

These are unusual values to investigate before building payment features; a zero-value voucher, for example, may be legitimate.

## Implications for CallVerse

Order IDs and the principal customer/product/seller links are reliable for the checked joins. People must be identified with `customer_unique_id`, not `customer_id`. Reviews should be keyed on (`review_id`, `order_id`), with care not to count a review attached to several orders more than once, and with a rule for orders that have several reviews. Actual and estimated delivery dates are broadly available, but missing milestones and the 23 reversed carrier/delivery pairs need careful handling. The 1,359 approval-to-carrier reversals also matter when reconstructing a delivery timeline. Late delivery should be measured by calendar date. Predictive features must use only events observable at the simulated contact time; actual delivery outcomes are future information for an earlier inquiry.

Olist does not contain actual contact events, contact reasons, agent assignments, call durations, queue waits, or abandonment records. It cannot directly establish that a customer contacted support after a delay or cancellation. Future contact-demand estimates require a transparent contact-generation process or explicit assumptions, which should be documented and tested.

## Recommended next step

Phase 1B has identified issues and coverage patterns but has not cleaned or imputed values. Phase 1C — Data Cleaning and Preparation — should decide how to handle the review key, timestamp exceptions, missing delivery milestones, product attributes, unusual payment values, and orders without associated item/payment rows. Preserve source values and document each decision so that the CallVerse dataset remains auditable. Phase 1C has since been carried out; see `docs/data_cleaning_preparation_report.md`.
