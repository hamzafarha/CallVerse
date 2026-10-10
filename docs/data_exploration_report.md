# CallVerse — Olist Data Exploration Report

**Dataset:** Brazilian E-Commerce Public Dataset by Olist, files in `data/raw/olist/`  
**Prepared:** 10 October 2026  
**Scope:** Descriptive exploration of the supplied CSVs; no model training, forecasting, or simulation.

## Executive summary

The local Olist files provide useful e-commerce context for CallVerse: 99,441 orders placed between 4 September 2016 and 17 October 2018, linked to customer, item, payment, review, product, seller, and location tables. In the delivered-order subset with both delivery dates, 96,470 orders were eligible for comparing actual and estimated delivery. Of those, 7,826 (8.11%) arrived after the estimate; the median delivery was 11.95 days earlier than estimated.

This is an e-commerce dataset, **not contact-center data**. It contains no observed support arrivals, contact reasons, agent handling times, staffing, waits, abandonment, or SLA outcomes. Late or canceled orders may be used as conditions for explicitly synthetic inquiry scenarios, but they do not show that a customer contacted support.

## Dataset inventory

Record counts below were read from the local CSVs. Review CSV records were counted with a CSV parser; physical line count is higher because quoted review text can contain line breaks. Sizes are the on-disk file sizes.

| Table / file | Records | Size (MiB) | Exploration role |
|---|---:|---:|---|
| Customers | 99,441 | 8.62 | Customer IDs and location fields |
| Geolocation | 1,000,163 | 58.44 | ZIP-prefix coordinate observations; prefix is not unique |
| Orders | 99,441 | 16.84 | Status and order/delivery timestamps |
| Order items | 112,650 | 14.72 | Product and seller lines, price, freight |
| Payments | 103,886 | 5.51 | Payment type, installments, value |
| Reviews | 99,224 | 13.78 | Review scores, comments, review timestamps |
| Products | 32,951 | 2.27 | Product categories and attributes |
| Sellers | 3,095 | 0.17 | Seller identifiers and location |
| Category translation | 71 | <0.01 | Portuguese/English category mapping |

All nine expected CSV files were present; no unexpected CSV file was reported.

## Order and delivery findings

### Order status

| Status | Orders | Share |
|---|---:|---:|
| Delivered | 96,478 | 97.02% |
| Shipped | 1,107 | 1.11% |
| Canceled | 625 | 0.63% |
| Unavailable | 609 | 0.61% |
| Invoiced | 314 | 0.32% |
| Processing | 301 | 0.30% |
| Created | 5 | 0.01% |
| Approved | 2 | <0.01% |

The distribution is heavily dominated by delivered orders. Canceled and unavailable orders are order statuses, not evidence of refunds or support contacts.

### Timestamp coverage and delivery delay

All 99,441 orders had a purchase timestamp and estimated delivery date. Actual customer delivery time was missing for 2,965 rows; carrier handoff was missing for 1,783; approval was missing for 160. Missing delivery events should be interpreted with order status and not automatically treated as errors.

For delivered orders with both actual and estimated dates, the derived delay is `actual delivery − estimated delivery`:

| Measure | Result |
|---|---:|
| Eligible delivered orders | 96,470 |
| Delivered on or before estimate | 88,644 (91.89%) |
| Delivered after estimate | 7,826 (8.11%) |
| Mean delay | −11.18 days |
| Median delay | −11.95 days |
| Range | −146.02 to +188.98 days |

The large range indicates extreme cases that can affect averages and should be reviewed in later analysis. “On or before estimate” means the actual timestamp is less than or equal to the estimated timestamp; the late share is strictly later. These values describe delivery records, not customer perceptions or contacts.

## Reviews and data quality

The parsed reviews table contains 99,224 records and no missing review scores. The mean score is **4.09 / 5**. Score counts were: 1 = 11,424; 2 = 3,151; 3 = 8,179; 4 = 19,142; 5 = 57,328. A review score is post-purchase feedback, not a contact-center satisfaction survey.

Selected completeness findings:

- Orders: 160 missing approvals, 1,783 missing carrier handoffs, and 2,965 missing actual delivery timestamps; purchase and estimated-delivery timestamps were complete.
- Products: 610 rows lack category, product name length, description length, and photo count; two rows lack each of the listed physical dimensions/weight fields.
- Order `order_id` was unique in the orders table (no repeated order IDs found).
- No unmatched child keys were found in the inspected order-items-to-orders, payments-to-orders, reviews-to-orders, items-to-products, or items-to-sellers relationships.
- Geolocation contains many observations per ZIP prefix. A ZIP prefix must not be treated as a unique coordinate/address without a deliberate aggregation rule.

No rows were removed or repaired for this report. The relationship checks are key-membership checks; they do not prove every field or table relationship is semantically correct.

## Implications for CallVerse

Olist is a suitable starting **e-commerce event substrate** for order tracking and delivery-exception scenarios. The project can directly use order statuses, purchase and delivery timestamps, customer/order identifiers, products, payment context, and reviews (subject to license conditions). Delivery delay is a derived indicator.

The following remain absent and require real contact-center data or clearly labeled synthetic generation and documented assumptions:

- Whether an order generated a support contact, contact reason/channel, and contact arrival time.
- Repeat contacts, customer patience, abandonment, wait time, service start/end, resolution, and transfer outcomes.
- Agent skills, availability, shift schedules, staffing levels, wages, and handling costs.
- Real agent responses, policy compliance, and QA rubric scores. Company knowledge and policy documents would need a separate source.

Consequently, Olist alone cannot train or validate models for contact arrivals/AHT, realistic waiting and abandonment/SLA, or a workforce optimizer based on observed schedules. It can support order-volume exploration; order volume must not be reported as contact volume. Any mapping from delay/cancellation to synthetic contacts or contact probabilities is a modeling assumption, not an observed Olist result.

## Recommendation and next steps

Continue with Olist for exploratory order and delivery analysis, while keeping source, derived, synthetic, and assumed data distinct. Before using or redistributing the files, verify the current license at the official dataset source. For the next project phase, review unusual delivery-delay extremes and detailed table-level missingness, then define a separately documented contact-scenario study. Calibrate contact and workforce assumptions with real operational traces if they become available. The next planned notebook is `notebooks/02_contact_analysis.ipynb`; forecasting and simulation are outside this report's scope.

## Method note

The results in this report were calculated from the CSV files present locally using PowerShell CSV parsing because Python/Jupyter were not available on the shell PATH. The analysis notebook itself was not executed in this environment. Counts, timestamps, missingness, status distribution, delay statistics, review score distribution, and selected key matches above are observed/derived from the supplied files; no contact-center outcomes were generated or inferred as fact.
