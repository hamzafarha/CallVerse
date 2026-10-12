# CallVerse Phase 1D — Feature Engineering & Analytical Dataset Report

**Notebook:** `notebooks/04_feature_engineering_analytical_dataset.ipynb`  
**Inputs:** Phase 1C prepared tables in `data/processed/` and the category translation table in `data/raw/olist/`  
**Prepared:** 11 October 2026  
**Scope:** Engineering order-level features, building an order-level analytical table and a daily activity table, documenting each feature in a catalog, validating and exporting. No model training, forecasting, simulation, or contact generation.

## Executive summary

Phase 1D turns the seven prepared Olist tables into two analytical datasets:

| Dataset | Grain | Size | Purpose |
|---|---|---|---|
| `olist_orders_analytical.parquet` | One row per order | 99,441 × 77 | Order, customer, item, payment, delivery-timeline and review features for contact scenarios and simulation inputs |
| `olist_daily_activity.parquet` | One row per calendar day | 774 × 15 | Daily counts of e-commerce events for the forecasting phase |
| `olist_feature_catalog.csv` | One row per order-table column | 77 × 6 | Meaning, source, type, missing count and **`available_at` stage** of every column |

Every feature is tagged with the moment it becomes known: at purchase, approval, carrier handoff, delivery, review, or only in hindsight at the end of the data. A later simulated contact at time *t* may only use features known before *t*; this prevents **leakage** of future information.

Main results:

- **No order was removed, and no item, payment or review row was lost** in aggregation; all validation checks passed.
- The data **effectively end on 31 August 2018**, not on the latest timestamp (17 October 2018). After the end of August only a few stray events remain. Using the effective end avoids labelling late-August orders still in transit as "never delivered".
- **1,725 orders are overdue without delivery** (estimated date passed, still in progress). They are a natural basis for future *simulated* "where is my order?" contacts.
- Late delivery is strongly associated with low review scores (mean 2.27 versus 4.29).

> These datasets describe **e-commerce events, not contacts**. Olist has no contact logs, contact reasons, channels, call durations, queue times or agents. The daily table counts orders, deliveries and reviews, which are *candidate drivers* of contact demand, not contact demand. Synthetic contacts will be generated in a later phase from documented assumptions.

## Design decisions

The four main decisions were agreed with the project owner before implementation.

| Topic | Decision |
|---|---|
| Output | Order-level table **and** daily activity table |
| Analysis window | **Keep all orders**; flag purchases from 1 January 2017 to 31 August 2018 with `in_analysis_window` |
| Contradictory timestamps | Leave a duration **empty** when its two timestamps were flagged as contradictory in Phase 1C; keep the order's other features |
| Several reviews per order | Use the **latest** review (latest answer, then latest creation); keep `review_count` |

Additional implementation choices:

| Topic | Choice |
|---|---|
| Aggregation | Items, payments and reviews are aggregated to one value per order (counts, sums, maxima). The detailed rows remain in the Phase 1C tables. |
| Primary item | Where one value per order is needed (category, seller), the **most expensive item line** is used; ties go to the lowest `order_item_id`. |
| Primary payment type | Type of the largest payment; ties go to the first payment step. |
| Missing values | Not imputed. A feature is empty when its source is missing or the event did not happen. Only `review_count` is filled with 0, because "no review row" is a real count. |
| Joins | Every join uses pandas `validate=` (`one_to_one` or `many_to_one`), so a join that would multiply rows raises an error. |

### `available_at` stages

| Stage | Meaning | Columns |
|---|---|---:|
| `identifier` | Keys; not predictive features | 3 |
| `purchase` | Known when the order is placed | 36 |
| `approval` | Known once payment is approved | 2 |
| `carrier_handoff` | Known once the seller hands over the parcel | 3 |
| `delivery` | Known once the customer receives the order | 5 |
| `review` | Known once the customer writes a review | 12 |
| `end_of_data` | Only known in hindsight (final status, censoring, quality flags) | 16 |

---

## Step-by-step walkthrough

Section numbers refer to the notebook.

### 2–3. Paths and loading

The notebook uses the same project-root detection as earlier phases and reads the Phase 1C Parquet files, which keep datetime and boolean types. If an input is missing, it stops and asks to run `03_data_cleaning_preparation.ipynb` first.

**Output:**

| Dataset | Rows | Columns |
|---|---:|---:|
| Orders | 99,441 | 21 |
| Order items | 112,650 | 7 |
| Customers | 99,441 | 5 |
| Payments | 103,886 | 8 |
| Reviews | 99,224 | 12 |
| Products | 32,951 | 11 |
| Sellers | 3,095 | 4 |
| Category translation | 71 | 2 |

### 4. Design decisions

A Markdown section records the decisions above and the `available_at` stages. There is no code output.

### 5. Order base

#### 5.1 Orders joined with customers

`customer_id` is unique in both tables, so the join is one-to-one. **Output:** 99,441 rows before and after.

#### 5.2 Purchase calendar features

`purchase_date`, `purchase_year_month`, `purchase_day_of_week`, `purchase_hour`, `purchase_is_weekend`.

**Output, orders by day of the week:**

| Day | Orders |
|---|---:|
| Monday | 16,196 |
| Tuesday | 15,963 |
| Wednesday | 15,552 |
| Thursday | 14,761 |
| Friday | 14,122 |
| Sunday | 11,960 |
| Saturday | 10,887 |

Purchases peak early in the week; 22.98% of orders are placed at the weekend.

#### 5.3 Customer history

`customer_order_number` is the position of the order among the person's orders (`customer_unique_id`), sorted by purchase time. It uses only earlier orders, so it is known at purchase. `customer_is_repeat_buyer` is `True` from the second order onwards.

**Output:** 96,096 first orders, 2,997 second orders, 252 third orders, and a long tail up to one person with 17 orders. In total 3,345 orders come from repeat buyers.

### 6. Item features

Each item line receives its product category, English translation, weight and seller state (many-to-one lookups; 112,650 item rows before and after). Items are then aggregated per order.

**Output (orders with items):**

| Feature | Median | Mean | Max |
|---|---:|---:|---:|
| `item_count` | 1 | 1.14 | 21 |
| `distinct_sellers` | 1 | 1.01 | 5 |
| `items_price_total` (BRL) | 86.90 | 137.75 | 13,440.00 |
| `items_freight_total` (BRL) | 17.17 | 22.82 | 1,794.96 |
| `order_value` (BRL) | 105.29 | 160.58 | 13,664.08 |
| `freight_share` | 0.18 | 0.21 | 0.96 |
| `items_weight_g_total` (g) | 750 | 2,390 | 184,400 |

- Most orders contain a single item from a single seller.
- `items_weight_g_total` is empty for 16 orders with an item lacking a weight, in addition to the 775 orders without items.
- **Primary category:** the top English categories are `bed_bath_table` (9,328), `health_beauty` (8,801) and `sports_leisure` (7,683). The primary category is empty for 2,190 orders: 775 without items and 1,415 whose main product has no category. The English name is also empty for 22 orders whose category has no translation; it was not invented.
- **Customer and seller in the same state:** 35,468 orders; different states: 63,198; unknown (no items): 775.

### 7. Payment features

`payment_count`, `payment_total`, `max_installments`, `uses_voucher`, `primary_payment_type`, `payment_minus_order_value`.

**Output:**

| Primary payment type | Orders |
|---|---:|
| credit_card | 74,975 |
| boleto | 19,784 |
| voucher | 3,151 |
| debit_card | 1,527 |
| not_defined | 3 |
| none (no payment row) | 1 |

3,866 orders use at least one voucher. Payment total and order value agree for most orders (median difference 0.00 BRL); 249 orders differ by more than 1 BRL, as found in Phase 1B.

### 8. Delivery timeline features

| Feature | Known at | Rule |
|---|---|---|
| `purchase_to_approval_hours` | approval | Empty if `flag_approved_before_purchase` |
| `approval_to_carrier_days` | carrier handoff | Empty if `flag_carrier_before_approval` |
| `carrier_to_delivery_days` | delivery | Empty if `flag_delivered_before_carrier` |
| `purchase_to_delivery_days` | delivery | Empty if `flag_delivered_before_purchase` |
| `promised_delivery_days` | purchase | Estimated date − purchase date |
| `delivery_delay_days` | delivery | Delivery date − estimated date (negative = early) |
| `carrier_after_shipping_limit` | carrier handoff | Handoff later than the seller's shipping deadline |

**Output:**

| Feature | Count | Median | Mean | Min | Max |
|---|---:|---:|---:|---:|---:|
| `purchase_to_approval_hours` | 99,281 | 0.34 | 10.42 | 0.00 | 4,509.18 |
| `approval_to_carrier_days` | 96,285 | 1.85 | 2.86 | 0.00 | 125.76 |
| `carrier_to_delivery_days` | 96,452 | 7.10 | 9.33 | 0.00 | 205.19 |
| `purchase_to_delivery_days` | 96,476 | 10.22 | 12.56 | 0.53 | 209.63 |
| `promised_delivery_days` | 99,441 | 24 | 24.40 | 2 | 156 |
| `delivery_delay_days` | 96,476 | −12 | −11.88 | −147 | 188 |

- Durations emptied by the flag rule: 1,359 for approval-to-carrier and 23 for carrier-to-delivery. As a result, **no duration is negative**.
- Customers are typically promised 24 days but receive orders in about 10, so most deliveries arrive well before the estimate (median 12 days early).
- **The seller handed over late in 8,849 orders**; 88,808 were on time; 1,784 are unknown (no handoff or no items).
- A consistency check confirms that `delivered_after_estimated_date` (Phase 1C) equals `delivery_delay_days > 0` for every order (0 disagreements).
- Status indicators `is_delivered`, `is_canceled` and `is_unavailable` were added.

### 9. Review features

The latest review per order provides `review_id`, `review_score`, `review_is_low_score` (score 1 or 2), creation and answer dates, title/message indicators, the Phase 1C review flags, and `delivery_to_review_days`.

**Output:**

| `review_count` | Orders |
|---:|---:|
| 0 | 768 |
| 1 | 98,126 |
| 2 | 543 |
| 3 | 4 |

| Latest review score | Orders |
|---:|---:|
| 1 | 11,363 |
| 2 | 3,131 |
| 3 | 8,133 |
| 4 | 19,038 |
| 5 | 57,008 |
| none | 768 |

14,494 orders have a low latest score. `delivery_to_review_days` has a median of 1 day and is negative for 4,977 orders: Olist sends its review request around the *estimated* delivery date, so late orders can be reviewed before they arrive. Review features are known only after the review is written and must not explain an earlier contact.

### 10. Analysis window and censoring

#### 10.1 Monthly order volume

**Output:** fewer than 330 orders per month in 2016 (none in November 2016), 800 in January 2017 rising to about 6,000–7,500 per month in 2018, then 16 in September and 4 in October 2018. This justifies the window of January 2017 to August 2018.

#### 10.2 Effective end of the data

The latest timestamp in the data is 17 October 2018, but activity stops much earlier. The notebook defines the **effective data end** as the last day on which deliveries reach at least 10% of the median weekday delivery count inside the window (an explicit assumption).

**Output:** median weekday deliveries 199, threshold 19.9 per day, **effective data end 31 August 2018**. The latest review creation date (31 August 2018) confirms it.

| Date | Purchases | Approvals | Carrier handoffs | Deliveries |
|---|---:|---:|---:|---:|
| 2018-08-27 | 67 | 64 | 248 | 446 |
| 2018-08-28 | 44 | 56 | 118 | 395 |
| 2018-08-29 | 14 | 15 | 74 | 368 |
| 2018-08-30 | 4 | 0 | 2 | 365 |
| 2018-08-31 | 1 | 0 | 3 | 27 |
| 2018-09-01 to 09-07 | 7 | 1 | 2 | 33 (total) |

The table also shows that **purchases thin out in the last days of August 2018**: these days are inside the window but incomplete. The first four days of January 2017 also have no purchases.

#### 10.3 Window and end-of-data indicators

| Indicator | All orders | In window |
|---|---:|---:|
| `in_analysis_window` | 99,092 | 99,092 |
| `delivery_outcome_observable` | 99,375 | 99,046 |
| `overdue_without_delivery` | 1,725 | 1,696 |

- 349 orders fall outside the window.
- **46 orders in the window have a censored delivery outcome**: they were not delivered and were not yet due when the data end.
- Overdue orders by status: shipped 1,103, invoiced 314, processing 301, created 5, approved 2. The 8 `delivered`-status orders without a delivery date are excluded because their status contradicts the missing date.

### 11. Order table and feature catalog

The notebook selects the 77 final columns and writes a catalog entry for each. It stops if any column lacks an entry, so nothing undocumented is exported. The Phase 1C quality flags are carried over unchanged. The stage counts are listed in the design section above.

### 12. Validation of the order table

| Check | Result |
|---|---|
| One row per order (99,441) | Passed |
| `order_id` unique | Passed |
| Item rows = sum of `item_count` (112,650) | Passed |
| Payment rows = sum of `payment_count` (103,886) | Passed |
| Review rows = sum of `review_count` (99,224) | Passed |
| Item price total preserved | Passed |
| Payment total preserved | Passed |
| `item_count` empty exactly when `has_items` is `False` | Passed |
| No negative values in the four milestone durations | Passed |
| All yes/no columns use a boolean type (nullable where values can be unknown) | Passed |

**Missing values.** 41 of the 77 columns have missing values, from three sources, none of them imputed:

| Source | Examples | Missing |
|---|---|---:|
| Event did not happen | delivery timestamp and delay features | 2,965 |
| | carrier handoff | 1,783 |
| | approval | 160 |
| Related record does not exist | item features (no items) | 775 |
| | review features (no review) | 768 |
| | payment features (no payment) | 1 |
| Emptied by the flag rule, or source attribute missing | `approval_to_carrier_days` | 3,156 |
| | `primary_category_english` | 2,212 |
| | `delivery_to_review_days` | 3,611 |

### 13. First look at the analytical dataset

#### Late delivery by purchase month (delivered orders in the window)

| Month | Delivered | Late | Late % | Median days to deliver |
|---|---:|---:|---:|---:|
| 2017-01 | 750 | 22 | 2.93 | 10.73 |
| 2017-04 | 2,303 | 151 | 6.56 | 12.75 |
| 2017-07 | 3,872 | 108 | 2.79 | 10.16 |
| 2017-10 | 4,478 | 187 | 4.18 | 10.26 |
| **2017-11** | 7,288 | 904 | **12.40** | 12.70 |
| 2017-12 | 5,513 | 411 | 7.46 | 13.14 |
| **2018-02** | 6,556 | 927 | **14.14** | 14.27 |
| **2018-03** | 7,003 | 1,328 | **18.96** | 13.37 |
| 2018-04 | 6,798 | 306 | 4.50 | 9.31 |
| 2018-06 | 6,096 | 71 | 1.16 | 7.96 |
| 2018-08 | 6,351 | 393 | 6.19 | 7.01 |

*(Selected months; the notebook shows all 20.)* Late-delivery rates spike after Black Friday 2017 and in February–March 2018, then drop sharply; delivery times fall during 2018.

#### Review score by late delivery (delivered, reviewed orders in the window)

| Delivered late? | Orders | Mean score | Low score (1–2) |
|---|---:|---:|---:|
| No | 89,182 | 4.29 | 9.25% |
| Yes | 6,379 | 2.27 | 62.41% |

Late delivery is associated with much lower scores. This is a correlation in post-purchase feedback; it motivates, but does not measure, a late-delivery contact scenario.

**Final status of orders in the window:** delivered 96,211, shipped 1,097, unavailable 602, canceled 580, processing 299, invoiced 296, created 5, approved 2.

### 14. Daily activity table

774 days from 4 September 2016 to 17 October 2018, including days with no events. Each column counts events on the date they happened:

| Column | Counted on the date of |
|---|---|
| `orders_purchased` | purchase |
| `orders_approved` | approval |
| `orders_handed_to_carrier` | carrier handoff |
| `orders_delivered` | delivery |
| `late_deliveries` | delivery, for late orders |
| `deliveries_due` | estimated delivery date |
| `canceled_orders_by_purchase_date` | purchase, for canceled orders (no cancellation date exists) |
| `reviews_created` | review creation (each distinct `review_id` once) |
| `low_score_reviews` | review creation, scores 1–2 |
| `order_value_purchased` | purchase (sum of order values, BRL) |

Calendar columns `day_of_week`, `is_weekend`, `in_analysis_window` and `after_effective_data_end` are added. 608 days are in the window and 47 days fall after the effective data end.

**Output, daily statistics inside the window:**

| Column | Mean | Median | Max |
|---|---:|---:|---:|
| `orders_purchased` | 163.0 | 150.5 | 1,176 |
| `orders_delivered` | 158.1 | 143.0 | 446 |
| `late_deliveries` | 10.6 | 5.0 | 90 |
| `reviews_created` | 161.3 | 148.5 | 461 |
| `low_score_reviews` | 23.5 | 20.0 | 112 |
| `order_value_purchased` (BRL) | 25,964 | 24,029 | 178,378 |

**Validation:** one row per day with no gaps, and every daily column's total equals the corresponding count in the order table (11 checks passed). Six estimated delivery dates fall after the last day of the table and are therefore not counted in `deliveries_due`.

**Weekly pattern (window averages):**

| Day | Purchases | Deliveries | Reviews created |
|---|---:|---:|---:|
| Monday | 185.5 | 216.1 | 12.4 |
| Tuesday | 182.7 | 212.1 | 206.2 |
| Wednesday | 178.2 | 207.0 | 217.5 |
| Thursday | 169.0 | 195.7 | 213.7 |
| Friday | 161.8 | 198.0 | 202.1 |
| Saturday | 126.1 | 63.2 | 204.4 |
| Sunday | 137.1 | 13.8 | 73.5 |

Deliveries happen almost only on weekdays. Review creation dates follow their own schedule, with few on Mondays and Sundays, which suggests they reflect when Olist sends review requests rather than when customers react.

**Busiest purchase days:** 24 November 2017 (Black Friday, 1,176 orders, 178,378 BRL), followed by the four days after it (380–499 orders each).

### 15. Export

| File | Rows | Columns | Size (MB) |
|---|---:|---:|---:|
| `olist_orders_analytical.parquet` | 99,441 | 77 | 24.49 |
| `olist_daily_activity.parquet` | 774 | 15 | 0.03 |
| `olist_feature_catalog.csv` | 77 | 6 | 0.006 |

Both Parquet files were reloaded with identical row counts and column types. Files in `data/processed/` are ignored by git and are regenerated by running notebooks 03 and 04 in order.

---

## How later phases should use these datasets

- **Respect `available_at`.** A simulated contact may only use features known before its contact time. Review features and `end_of_data` indicators are hindsight.
- **Filter with `in_analysis_window`**, and check where purchase counts become reliable at both ends (the first days of January 2017 and the last week of August 2018 are thin).
- **Use `delivery_outcome_observable`** so censored orders are not treated as on time.
- **Use `customer_unique_id`** for anything about people.
- **Treat the daily table as drivers, not demand.** Contact volume must be derived from these drivers through documented assumptions, for example the architecture's `orders(t) × contact-rate(intent | order state, promo, delay)`.

## Limitations

- Olist contains **no contacts, intents, channels, waiting times, handling times or agents**. Intent labels (e.g. the Bitext dataset), synthetic tickets and a promotion calendar are still required by the architecture.
- About 20 usable months contain only one November / Black Friday period, which limits seasonal modelling.
- Cancellation dates are not recorded; cancellations can only be dated by purchase date.
- The effective data end relies on a 10% activity threshold; the result is robust here because activity collapses within one day.
- The late-delivery / review relationship is descriptive, not causal.
- The preparation and feature logic exist only in notebooks; they still need to be moved into `callverse.data` with tests.

## Recommended next step

Before forecasting, a **Phase 1E** should define the synthetic contact layer:

1. evaluate and add an intent dataset (Bitext);
2. map order states to intents (e.g. overdue or late → "where is my order?", canceled/unavailable → "I need a refund");
3. document the contact-rate assumptions;
4. design the synthetic promotion calendar.

Synthetic contacts must remain clearly separated from the observed Olist data.

## Method note

All figures come from executing `notebooks/04_feature_engineering_analytical_dataset.ipynb` top to bottom with a Jupyter kernel (Python 3.12, pandas 2.2.2, pyarrow 17.0.0), from both `notebooks/` and the project root, with no errors. Inputs are the Phase 1C outputs regenerated from the local Olist CSVs. No figure is copied from earlier reports.
