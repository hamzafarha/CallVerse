# CallVerse Phase 1C — Data Cleaning & Preparation Report

**Notebook:** `notebooks/03_data_cleaning_preparation.ipynb`  
**Dataset:** Brazilian E-Commerce Public Dataset by Olist, seven tables in `data/raw/olist/`  
**Prepared:** 11 October 2026  
**Scope:** Investigation of the Phase 1B findings, preparation of typed and flagged copies of the source tables, re-validation, and export to `data/processed/`. No imputation, record deletion, timestamp correction, feature engineering, or contact generation.

## Executive summary

Phase 1C produced one prepared file per Olist table. **Every record of every table was preserved**, no source value was filled or corrected, and the raw files and raw in-memory tables were verified to be unchanged. The preparation consists of three kinds of change:

1. **Types:** eight timestamp columns converted to datetime (0 parse failures); ZIP-code prefixes read as text so leading zeros are kept.
2. **Availability columns (`has_*`):** state whether a value or related record exists, e.g. whether an order has a delivery timestamp or any items.
3. **Data-quality flags (`flag_*`):** mark records that match a suspicious pattern, e.g. carrier handoff before approval. A flag means "check before relying on this field", not "this record is unusable".

The main findings:

- **Repeated `review_id` values are not erroneous duplicates.** All 789 repeated IDs carry identical review content and link orders of the same person; the reviews table is keyed on `(review_id, order_id)`.
- **People are identified by `customer_unique_id`**, not `customer_id` (which is created per order). 2,997 people have more than one order.
- **Late delivery affects 6,535 of 96,476 delivered orders (6.77%)** when measured by calendar date. Earlier phases reported about 7,826–7,827 because they compared a delivery timestamp with a date-only estimate stored at midnight.
- **Timestamp contradictions remain unresolved:** 1,359 carrier handoffs before approval, 23 deliveries before carrier handoff, 64 reviews created before the purchase date. They are flagged, not corrected.

> Olist is e-commerce data, **not contact-center data**. It contains no customer contacts, contact reasons, channels, call durations, queue waiting times, or agent assignments. Synthetic contact records will be generated in a later phase from documented assumptions and must never be confused with the observed Olist data described here.

## Methodology

The notebook applies these principles throughout:

- Raw files in `data/raw/` are only read. All work happens on copies (`*_prepared`) of the loaded tables (`*_raw`).
- No record is deleted, no missing value is imputed, and no timestamp is swapped or corrected.
- Missing values are distinguished from invalid values: an empty review title is a normal choice; a delivery before carrier handoff is suspicious.
- Suspicious patterns are first counted and shown with examples, then flagged.
- Tables are kept separate. Joining orders to items, payments or reviews would repeat order rows, so no flattened table is produced.
- Every finding and decision is recorded in an issue log, exported with the data.

**Flag conventions.** Chronology flags are `True` only when both timestamps exist and are in the unexpected order; they are `False` when either is missing (the `has_*` columns separate those cases). `delivered_after_estimated_date` uses a nullable boolean and is empty (`<NA>`) for orders without an actual delivery date, so an undelivered order is never counted as "on time".

---

## Step-by-step walkthrough

Section numbers refer to the notebook.

### 2. Imports and project paths

The notebook locates the project root whether it is started from the root or from `notebooks/`, the same convention as Phases 1A and 1B. It stops with a clear error if `data/raw/olist/` is missing.

**Output:** project root, raw-data directory and `data/processed/` all found.

### 3. Load the source data

All seven files are checked before loading; a missing file raises an error listing every missing name rather than continuing with incomplete data. The two ZIP-prefix columns are read as text, because the CSV stores them as quoted 5-digit strings (e.g. `"09790"`) that pandas would otherwise turn into numbers and drop the leading zero. A fingerprint (a hash of every value) of each loaded table is stored to verify later that nothing changed.

**Output:**

| Table | File | Rows | Columns |
|---|---|---:|---:|
| Orders | `olist_orders_dataset.csv` | 99,441 | 8 |
| Order items | `olist_order_items_dataset.csv` | 112,650 | 7 |
| Customers | `olist_customers_dataset.csv` | 99,441 | 5 |
| Payments | `olist_order_payments_dataset.csv` | 103,886 | 5 |
| Reviews | `olist_order_reviews_dataset.csv` | 99,224 | 7 |
| Products | `olist_products_dataset.csv` | 32,951 | 9 |
| Sellers | `olist_sellers_dataset.csv` | 3,095 | 4 |

### 4. Cleaning methodology and working copies

A Markdown cell states the principles above. The code cell creates the seven `*_prepared` copies and an empty issue log. There is no displayed output.

### 5. Identifiers and duplicate records

#### 5.1 Exact duplicate rows

**Output:** 0 exact duplicate rows in all seven tables. No rows were removed.

#### 5.2 Uniqueness of expected identifiers

Each table's expected key is tested, including keys expected to repeat.

**Output:**

| Table | Key tested | Distinct keys | Rows with a repeated key | Unique? |
|---|---|---:|---:|:---:|
| Orders | `order_id` | 99,441 | 0 | Yes |
| Orders | `customer_id` | 99,441 | 0 | Yes |
| Customers | `customer_id` | 99,441 | 0 | Yes |
| Customers | `customer_unique_id` | 96,096 | 6,342 | No (expected) |
| Order items | `order_id, order_item_id` | 112,650 | 0 | Yes |
| Payments | `order_id, payment_sequential` | 103,886 | 0 | Yes |
| Reviews | `review_id` | 98,410 | 1,603 | **No** |
| Reviews | `review_id, order_id` | 99,224 | 0 | Yes |
| Products | `product_id` | 32,951 | 0 | Yes |
| Sellers | `seller_id` | 3,095 | 0 | Yes |

**Interpretation:** every table has a reliable record key. The only unexpected result is `review_id`, investigated in 5.4.

#### 5.3 `customer_id` versus `customer_unique_id`

Because `customer_id` is unique in the orders table, Olist creates a new one for every order. The person is `customer_unique_id`.

**Output:**

| Description | Count |
|---|---:|
| Distinct people | 96,096 |
| People with exactly 1 order | 93,099 |
| People with 2 orders | 2,745 |
| People with 3 or more orders | 252 |

**Decision:** expected behaviour. Repeat-customer analysis (for example, a person contacting support about several orders) must use `customer_unique_id`. This corrects a statement in the Phase 1B notebook that customer IDs can repeat across orders.

#### 5.4 Repeated `review_id` values

The notebook groups the repeated rows by `review_id` and compares orders, people (looked up via orders → customers), scores, titles, messages and dates.

**Output:**

| Question | Count |
|---|---:|
| Rows with a repeated `review_id` | 1,603 |
| Distinct repeated `review_id` values | 789 |
| …where every copy points to a different order | 789 |
| …where all copies have identical review content | 789 |
| …where all orders belong to the same person | 789 |

764 IDs appear twice and 25 appear three times. The example table shows pairs of rows with the same person, score, creation date and answer timestamp, attached to two different orders.

**Interpretation:** the pattern indicates that **one review was attached to several orders of the same customer**. This is a hypothesis supported by the data, not confirmed by Olist documentation.

**Decision:** all rows kept; `review_id` not modified; the reviews table uses `(review_id, order_id)` as its key; `flag_repeated_review_id` added so later phases can avoid counting one review several times.

#### 5.5 Orders with more than one review

**Output:** 547 orders have more than one review row (1,098 rows in total). The examples show different review IDs with different scores and dates for the same order, for example scores 5, 3 and 5 on consecutive days.

**Decision:** all rows kept; `flag_order_has_multiple_reviews` added. Which review should count as the final one is **unresolved**.

### 6. Timestamp inconsistencies

#### 6.1 Convert timestamps to datetime

Columns are parsed with the explicit format `YYYY-MM-DD HH:MM:SS`. Values that fail become missing, and non-empty failures are counted.

**Output:** 0 parse failures across all eight columns:

| Table | Column | Non-empty values | Failures |
|---|---|---:|---:|
| Orders | `order_purchase_timestamp` | 99,441 | 0 |
| Orders | `order_approved_at` | 99,281 | 0 |
| Orders | `order_delivered_carrier_date` | 97,658 | 0 |
| Orders | `order_delivered_customer_date` | 96,476 | 0 |
| Orders | `order_estimated_delivery_date` | 99,441 | 0 |
| Order items | `shipping_limit_date` | 112,650 | 0 |
| Reviews | `review_creation_date` | 99,224 | 0 |
| Reviews | `review_answer_timestamp` | 99,224 | 0 |

#### 6.2 Chronology checks

Expected order: purchase → approval → carrier handoff → customer delivery. Only orders with both timestamps are compared; each check becomes a `flag_*` column keyed by `order_id`.

**Output:**

| Flag | Comparable orders | Violations | % | Median gap | Max gap |
|---|---:|---:|---:|---:|---:|
| `flag_approved_before_purchase` | 99,281 | 0 | 0.000 | — | — |
| `flag_carrier_before_approval` | 97,644 | 1,359 | 1.392 | 17.2 h | 4,109.3 h |
| `flag_delivered_before_carrier` | 96,475 | 23 | 0.024 | 39.9 h | 386.3 h |
| `flag_delivered_before_purchase` | 96,476 | 0 | 0.000 | — | — |

The example cells list affected order IDs with both timestamps. The explicit purchase-to-delivery duration confirms **0 negative durations** across 96,476 delivered orders (median 10.22 days, mean 12.56, range 0.53–209.63 days).

**Carrier handoff before approval, in detail:**

| Gap | Orders |
|---|---:|
| < 1 hour | 242 |
| 1–6 hours | 379 |
| 6–24 hours | 280 |
| 1–2 days | 280 |
| 2–7 days | 164 |
| > 7 days | 14 |

Two thirds (901 of 1,359) are within one day; 1,350 of the orders are `delivered` and 9 `shipped`. A plausible explanation is that approval and carrier events were recorded by different systems at different times, but the data cannot show which timestamp is correct.

**Decision:** all four checks flagged; original timestamps kept; nothing swapped or removed.

#### 6.3 Actual delivery later than estimated delivery

The notebook first confirms that **all** estimated delivery dates are stored at `00:00:00` (0 exceptions), i.e. they are calendar dates. Comparing them to a delivery timestamp would count a delivery at 10:00 on the estimated day as late, so lateness is measured by calendar date.

**Output:**

| Comparison | Comparable orders | Late orders |
|---|---:|---:|
| Delivery timestamp after estimate (Phase 1B method) | 96,476 | 7,827 |
| Delivery date after estimated date (used here) | 96,476 | **6,535** |

The 1,292-order difference are orders delivered on the estimated day itself. Among late orders, the median lateness is 7 days (mean 10.6, maximum 188).

**Decision:** late delivery is a delivery-performance outcome, not an error. It is stored as `delivered_after_estimated_date`: `True` for 6,535 orders, `False` for the other delivered orders, and empty for the 2,965 orders without a delivery date. This is the most relevant Olist signal for later "where is my order?" contact scenarios.

#### 6.4 Order status versus delivery timestamps

**Output:** a table of non-missing timestamps per status shows the expected pattern: `shipped` orders have carrier but no customer delivery dates; `unavailable`, `invoiced`, `processing`, `created` and `approved` orders have neither. Two unusual combinations were flagged:

| Flag | Orders | Observation |
|---|---:|---|
| `flag_delivered_status_without_delivery_date` | 8 | Status `delivered` but no customer delivery date; 7 of the 8 have a carrier handoff |
| `flag_canceled_status_with_delivery_date` | 6 | Status `canceled`, but a customer delivery date exists; 5 of the 6 are from October 2016 |

**Decision:** flagged; status and timestamps unchanged.

### 7. Missing values

#### 7.1 Missing-value counts

Counts are recomputed after timestamp parsing (so they also confirm that parsing added no missing values).

**Output:**

| Table | Column | Missing | % |
|---|---|---:|---:|
| Orders | `order_delivered_customer_date` | 2,965 | 2.98 |
| Orders | `order_delivered_carrier_date` | 1,783 | 1.79 |
| Orders | `order_approved_at` | 160 | 0.16 |
| Reviews | `review_comment_title` | 87,656 | 88.34 |
| Reviews | `review_comment_message` | 58,247 | 58.70 |
| Products | category, name length, description length, photo count | 610 each | 1.85 |
| Products | weight, length, height, width | 2 each | 0.01 |

Order items, customers, payments and sellers have no missing values.

#### 7.2 Missing order timestamps by status

**Output (missing values per status):**

| Status | Orders | No approval | No carrier handoff | No customer delivery |
|---|---:|---:|---:|---:|
| delivered | 96,478 | 14 | 2 | 8 |
| shipped | 1,107 | 0 | 0 | 1,107 |
| canceled | 625 | 141 | 550 | 619 |
| unavailable | 609 | 0 | 609 | 609 |
| invoiced | 314 | 0 | 314 | 314 |
| processing | 301 | 0 | 301 | 301 |
| created | 5 | 5 | 5 | 5 |
| approved | 2 | 0 | 2 | 2 |

**Interpretation:** almost all missing milestones belong to orders that never reached that stage. Only a handful of `delivered` orders have gaps.

#### 7.3 Decisions and availability columns

No missing value was filled. Instead, availability columns were added:

| Table | Column | `False` count |
|---|---|---:|
| Orders | `has_approval_timestamp` | 160 |
| Orders | `has_carrier_handoff_timestamp` | 1,783 |
| Orders | `has_customer_delivery_timestamp` | 2,965 |
| Reviews | `has_comment_title` | 87,656 |
| Reviews | `has_comment_message` | 58,247 |
| Products | `has_category` | 610 |
| Products | `has_complete_dimensions` | 2 |

The notebook also confirms that the 610 products without a category are exactly the products missing name length, description length and photo count. Review text was not replaced with invented content, and no product or order was dropped for missing optional fields.

### 8. Orders without related records

#### 8.1 Orders without items, payments, or reviews

**Output:**

| Related table | Orders without records | % of orders |
|---|---:|---:|
| Order items | 775 | 0.78 |
| Payments | 1 | 0.00 |
| Reviews | 768 | 0.77 |

- **Without items:** 603 `unavailable`, 164 `canceled`, 5 `created`, 2 `invoiced`, 1 `shipped`. These are mostly orders that never completed.
- **Without reviews:** 646 `delivered`, 75 `shipped`, 20 `canceled`, 14 `unavailable`, 6 `processing`, 5 `invoiced`, 2 `created`. A missing review is normal, since customers are not required to write one.
- **Without payment:** one order (`bfbd0f9bdef84302105ad712db648a6c`), status `delivered`, purchased 15 September 2016 and delivered 9 November 2016.

**Decision:** all orders kept; `has_items`, `has_payments` and `has_reviews` added. No related records were invented.

#### 8.2 Payment totals versus item totals

Per-order totals were computed for this check only; the prepared tables still hold one row per item and per payment.

**Output:** of 98,665 orders with both items and payments, **249** have payments differing from items + freight by more than 1 BRL. Differences range from −51.62 to +182.81 BRL (median +6.98), mostly payments *above* the item total.

**Interpretation:** consistent with credit-card instalment interest or vouchers, but not provable from the data. Reported only; **unresolved**.

### 9. Complete the prepared datasets

#### 9.1 Review flags

`flag_repeated_review_id` (1,603 rows) and `flag_order_has_multiple_reviews` (1,098 rows) record the findings of 5.4 and 5.5. `flag_review_created_before_purchase_date` compares calendar dates, because review creation dates have no time of day.

**Output:** 64 reviews were created before their order's purchase date. Of these, **40 have a repeated `review_id`**, which fits the 5.4 explanation: a review written for an earlier order and also attached to a later one looks "too early" for the later order. 3 belong to orders with several reviews. The remaining cases are unexplained.

#### 9.2 Payment flags

**Output:** payment types are `credit_card` 76,795, `boleto` 19,784, `voucher` 5,775, `debit_card` 1,529, `not_defined` 3.

| Flag | Rows | Observation |
|---|---:|---|
| `flag_payment_type_not_defined` | 3 | All three have value 0.00 |
| `flag_non_positive_payment_value` | 9 | Includes the 3 `not_defined` rows; the other examples shown are zero-value vouchers |
| `flag_zero_installments` | 2 | Credit-card payments (second payment step) with 0 instalments |

Values unchanged.

#### 9.3 Summary of prepared datasets

**Output:** type changes and added columns per table. No source column was renamed or removed, including Olist's original spellings such as `product_name_lenght`.

| Table | Rows | Source columns | Added columns | Type changes |
|---|---:|---:|---:|---|
| Orders | 99,441 | 8 | 13 | 5 timestamps → datetime |
| Order items | 112,650 | 7 | 0 | `shipping_limit_date` → datetime |
| Customers | 99,441 | 5 | 0 | none (ZIP read as text at load) |
| Payments | 103,886 | 5 | 3 | none |
| Reviews | 99,224 | 7 | 5 | 2 review dates → datetime |
| Products | 32,951 | 9 | 2 | none |
| Sellers | 3,095 | 4 | 0 | none (ZIP read as text at load) |

The notebook also displays a **flag dictionary** listing each added column, its meaning and its `True` count; every added column has a documented meaning.

### 10. Validation of the prepared datasets

All checks from Phase 1B were repeated on the prepared copies.

| Check | Result |
|---|---|
| 10.1 Row counts | Identical to source in all 7 tables; **no record added or removed** |
| 10.2 Exact duplicates (source columns) | 0 in all tables |
| 10.2 Record keys | Unique in all tables, using the keys from 5.2 (reviews: `review_id, order_id`) |
| 10.3 Missing values | Identical to raw in all 13 columns with missing values |
| 10.3 Timestamp parsing | 0 failures |
| 10.4 Referential integrity | 0 unmatched references in all 6 relationships (orders→customers, items→orders/products/sellers, payments→orders, reviews→orders) |
| 10.5 Chronology | Recounted violations match the stored flags exactly (0 / 1,359 / 23 / 0) |
| 10.6 Raw tables unchanged | Fingerprints identical for all 7 raw tables |

These flags mark records to consider before using a specific field; they do not make a record unusable.

### 11. Export

The data dictionary plans processed data as Parquet in `data/processed/`, and `pyarrow` is a project dependency. Parquet keeps datetimes, text ZIP codes and nullable booleans; CSV would store timestamps as text that must be parsed again on load. Each file was read back to confirm rows, columns and types.

**Output:**

| File | Rows | Columns | Size (MB) |
|---|---:|---:|---:|
| `olist_orders_prepared.parquet` | 99,441 | 21 | 10.06 |
| `olist_order_items_prepared.parquet` | 112,650 | 7 | 6.21 |
| `olist_customers_prepared.parquet` | 99,441 | 5 | 6.78 |
| `olist_payments_prepared.parquet` | 103,886 | 8 | 3.70 |
| `olist_reviews_prepared.parquet` | 99,224 | 12 | 9.21 |
| `olist_products_prepared.parquet` | 32,951 | 11 | 1.36 |
| `olist_sellers_prepared.parquet` | 3,095 | 4 | 0.13 |
| `olist_preparation_issue_log.csv` | 39 entries | 5 | <0.01 |

All files reloaded with the same row counts and types. `data/processed/` contents are ignored by git, so the files must be regenerated by running the notebook.

### 12. Issue log

The notebook ends by displaying the issue log (also exported as CSV): 39 entries, one per check, with area, table, issue, affected records and decision. The tables in this report are drawn from it.

---

## Unresolved issues for later phases

| Issue | Records | Why it matters |
|---|---:|---|
| Carrier handoff before approval | 1,359 orders | Affects any reconstruction of the order timeline or approval-to-shipping delays |
| Delivery before carrier handoff | 23 orders | Same; excludes these from shipping-duration features or treat separately |
| Which review counts when an order has several | 547 orders | Affects satisfaction features per order |
| Repeated `review_id` interpretation | 789 IDs | Count each review once per person when aggregating satisfaction |
| Reviews created before purchase date | 64 (24 unexplained) | Review timing features |
| Status/timestamp mismatches | 8 + 6 orders | Status-based scenario selection |
| Payment total ≠ items + freight | 249 orders | Refund or billing-dispute scenarios |
| Zero-value, zero-instalment and `not_defined` payments | 9 / 2 / 3 rows | Payment features |
| Category translation not applied | 2 untranslated categories, 13 products | English category names for contact reasons or routing |

Decisions on how later phases treat flagged records have **not** been made in this phase.

## Limitations of Olist for call-center simulation

- Olist records orders, deliveries, payments and reviews. It contains **no** customer contacts, contact reasons, channels, contact times, call durations, queue waits, abandonment, transfers, or agent assignments.
- A late delivery, cancellation or low review score can motivate a *simulated* contact scenario but does not prove a customer contacted support.
- Reviews are post-purchase feedback, not contact-center surveys or transcripts.
- Features for contact simulation must use only information available at the simulated contact time; for example, the actual delivery date is unknown before delivery.
- Order volume must not be reported as contact volume.

## Recommended next step

1. Decide how flagged records are treated in each later use (excluded, kept, or handled separately), and which months of the 2016–2018 range are usable for forecasting.
2. Move the preparation logic into `callverse.data` (schemas, preprocessing, validation) with tests, so the CLI and later phases can reproduce it without the notebook.
3. Proceed to feature engineering, then to a documented synthetic contact-generation phase. Synthetic contacts must remain clearly separated from the observed Olist data.

## Method note

All figures in this report come from the executed notebook `notebooks/03_data_cleaning_preparation.ipynb`, run top to bottom with a Jupyter kernel (Python 3.12, pandas 2.2.2, pyarrow 17.0.0) on the local Olist CSVs. It was executed both from `notebooks/` and from the project root, with no errors. No value in the notebook is copied from earlier reports; all counts are computed from the source files. Late-delivery and customer-identifier figures supersede the corresponding statements in the Phase 1B notebook and report.
