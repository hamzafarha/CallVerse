# CallVerse Phase 1A — Public E-commerce Dataset Evaluation

**Status:** Discovery report; no dataset downloaded and no synthetic records generated.  
**Evaluation date:** 10 October 2026

## Executive summary

Recommend **Brazilian E-Commerce Public Dataset by Olist** as the starting e-commerce source for Phase 1A, subject to confirming its current Kaggle license and attribution conditions before redistribution or any commercial use. It is the only evaluated candidate with linked order statuses, estimated and actual delivery dates, carrier handoff dates, customer identifiers, products, payments, and reviews. The dataset is a useful source of *order context* from which scenarios for order tracking, late delivery, cancellation, and possible refund/return inquiries can be modeled.

It does **not** include contact-center interactions, observed contact reasons, contact arrival timestamps, agent staffing, handling times, or actual refund/return events. Such contacts and operational attributes must be explicitly labeled as simulated/assumed. Olist supports DSO4’s e-commerce-informed scenario inputs and part of DSO2’s order context, but does not by itself provide historical evidence to calibrate contact demand or queue operations. The project should not describe generated contacts or contact probabilities as observed behavior.

## Repository context

Reviewed `README.md`, `docs/architecture.md`, `docs/data_dictionary.md`, `docs/experiments.md`, `configs/data.yaml`, and `configs/simulation.yaml`. The repository describes synthetic contact generation, forecasting, discrete-event simulation, advisor/quality agents, and replay calibration. `docs/data_dictionary.md` already specifies contact, advisor, article, and forecast entities, but these are planned schemas rather than evidence that source contact logs exist. The architecture doc's DSO numbering and descriptions differ from the definitions in the Phase 1A brief; this report follows the brief: DSO1 assignment, DSO2 advisor/QA, DSO3 workforce optimization, DSO4 forecasting/digital twin.

## Candidates and comparison

| Dataset / official source | License and restrictions | Access, format, approximate size | Records / coverage | Tables and useful fields | Delivery / returns | Quality and relevance |
|---|---|---|---|---|---|---|
| **Brazilian E-Commerce Public Dataset by Olist** — [Kaggle source](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | Kaggle source metadata is the governing reference. A third-party archival citation reports **CC BY-NC-SA 4.0**; current license text could not be independently read from Kaggle’s dynamically rendered page during this review. Treat the non-commercial/share-alike terms as a restriction to verify before use or redistribution. | Nine CSV files; Kaggle page showed **126.19 MB**. Kaggle account/download flow or Kaggle CLI/API; account/authentication may be required. | Commonly documented as about **100,000 orders**, 2016–2018. The exact per-table row counts were not independently verified from raw files because downloads were out of scope. | Orders (`order_id`, `customer_id`, status; purchase, approval, carrier, delivered-to-customer and estimated-delivery timestamps); customers; order items; payments; reviews; products; sellers; geolocation; category translation. | Actual/estimated delivery milestones and carrier handoff are directly documented. No explicit return/refund event table is documented. Cancellations are order statuses, not necessarily returns/refunds. | Best fit for order/delivery context and plausible tracking/late-delivery scenarios. Reviews provide feedback, not contact transcripts. Limited to Brazilian marketplace context and about two years; operational support outcomes absent. DSO4: moderate input support; DSO2: order context only; DSO1/3: no real queue/workforce evidence. |
| **Online Retail II** — [UCI Machine Learning Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | **CC BY 4.0**, as stated by UCI; attribution required, adaptations allowed under the license. | UCI provides an XLSX file, **43.5 MB**; direct download or UCI repository fetch client. | UCI verifies **1,067,371 instances**, 01 Dec 2009–09 Dec 2011. | One transaction table: InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country. Invoice numbers prefixed `C` indicate cancellations. UCI says missing values exist. | Invoice-level transaction time and cancellation marker; no delivery dates, shipping events, or explicit return/refund event records. Negative quantity may be informative during inspection but must not automatically be called a refund. | Strong transaction-volume time series and more permissive license; weak order/delivery journey and limited customer/order support context. Useful comparator for forecasting methods, but not sufficient for contact-center workload grounding. |
| **H&M Personalized Fashion Recommendations** — [Kaggle competition data/rules](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data) | **Subject to Kaggle competition rules**, which require accepting rules to access data. Not a conventional open dataset license; evaluate and comply with rules before any use or sharing. | CSV plus a large image collection; Kaggle page reports **34.56 GB** total, including a 3.49 GB transaction CSV. Sign-in and acceptance of competition rules required. | Competition describes customer purchase history over time; no single aggregate record count verified here. Transactions span 2018–2020 in competition materials; exact coverage is not relied on in this report. | `transactions_train.csv` (customer, article, date, price, sales channel); `customers.csv`; `articles.csv`; image directory and sample submission. | No delivery status, shipment events, returns, or refunds documented in the competition data description. | Customer/product purchase sequences but considerable download footprint and restrictive access rules. Poor fit for support-contact derivation. DSO4: purchase seasonality only; DSO2: product context, no policy knowledge; DSO1/3: no queue/workforce evidence. |

**Verification note:** Facts above are based on source descriptions and documentation, not inspection of downloaded files. Olist’s Kaggle page lists nine CSV files and its displayed archive size. Its dataset description and field names are widely represented in public data dictionaries; exact counts and field completeness should be checked during a later, authorized acquisition/inspection phase. Dataset sizes can change by version or packaging. H&M access and size are competition-page facts. UCI’s record count, XLSX size, date range, columns, missing-value flag, cancellation convention, and license are stated directly on its repository page.

## Requirements coverage matrix

Legend: **Available directly** = documented field/event exists; **Derivable** = computed from documented fields, with explicit logic; **Requires synthetic data** = not observed and must be simulated/assumed; **Unavailable or uncertain** = no documented basis in candidate.

| CallVerse requirement | Olist | Online Retail II | H&M |
|---|---|---|---|
| Customer and order identification | Available directly | Available directly (invoice/customer; customer may be missing) | Available directly (customer/article transaction; transaction is not an order lifecycle) |
| Order status and delivery delays | Available directly (status and estimated/actual dates) | Unavailable or uncertain | Unavailable or uncertain |
| Return and refund events | Unavailable or uncertain; cancellations are not refunds | Unavailable or uncertain; cancellation invoices are not explicit refund records | Unavailable or uncertain |
| Contact-reason generation | Derivable as scenario labels from status/delivery discrepancy; probabilities not observed | Derivable only as synthetic hypotheses from cancellation/transaction context | Requires synthetic data |
| Contact-arrival-time generation | Requires synthetic data | Requires synthetic data | Requires synthetic data |
| Contact-volume forecasting | Derivable for **order** counts from timestamps; contact volume requires synthetic contact linkage | Derivable for transaction counts; contact volume requires synthetic linkage | Derivable for purchase transaction counts; contact volume requires synthetic linkage |
| Agent skills and availability | Requires synthetic data | Requires synthetic data | Requires synthetic data |
| Handling-time estimation | Requires synthetic data | Requires synthetic data | Requires synthetic data |
| Staffing costs and scheduling | Requires synthetic data | Requires synthetic data | Requires synthetic data |
| Customer Advisor knowledge-base construction | Requires company policy/source documents; product/category fields provide context only | Requires company policy/source documents; product descriptions provide limited context | Requires company policy/source documents; articles provide product context only |
| Quality Analyst evaluation | Requires synthetic transcripts/rubrics or independently sourced policy answers | Requires synthetic transcripts/rubrics or independently sourced policy answers | Requires synthetic transcripts/rubrics or independently sourced policy answers |

## Missing-data analysis for Olist

**Available directly (documented):** order/customer IDs; order status; order purchase, approval, carrier handoff, actual customer delivery, and estimated delivery timestamps; order items and product categories; payment method/value; seller/customer geographic attributes; review scores/comments. Reviews are post-purchase feedback and must not be treated as contact-center transcripts or complaint labels.

**Derivable:** delivery delay in elapsed time or days by comparing actual and estimated delivery dates; order age at a chosen simulated observation time; undelivered/late-order flags; order-level item/value summaries; order volume by time bucket; scenario strata such as canceled, delayed, or delivered. These are derived order outcomes, not actual customer inquiries. Cancellation status does not establish that a refund occurred.

**Requires synthetic generation:** whether a customer contacts support; contact reason/channel and timestamp; repeat contacts; patience/abandonment; sentiment at contact; transcript and resolution; service/handle time; transfer/resolution status; advisor identity/skills; schedules, availability, wages, and staffing costs; contact-to-order linkage. If contact probabilities are used, they need documented assumptions and sensitivity ranges; they are not estimates observed in Olist.

**Requires external policy material or explicit synthetic content:** return eligibility, refund timing/method, order-tracking response policy, exceptions, and evaluation rubrics. Olist's commercial records do not define the simulated company's policies. Synthetic knowledge articles must be marked as fictional policy content.

**Operational assumptions to document before simulation:** mapping from order conditions to contact propensity; delay thresholds; contact-time distributions and time-zone interpretation; channel mix; repeat-contact rules; patience and abandonment distributions; handling-time distributions by reason; agent skill coverage, shift patterns, breaks, wage/overtime costs, service-level target, and seasonality/scenario factors. Distinguish source fields, deterministic transformations, and assumptions in all outputs.

## Recommendation, risks, and limits

Choose Olist for the **e-commerce event substrate**, not as a contact-center dataset. It best aligns with order tracking and delivery exception scenarios, has linked tables suitable for customer/order context, and is modest in size compared with H&M. Online Retail II is a useful alternative/benchmark for order-like transaction demand and has a clearly stated CC BY 4.0 license, but lacks shipping milestones. H&M has rich product/customer purchases but the high download size, competition rules, and absence of logistics make it a poor primary source here.

Key risks:

- **License:** verify the current Olist Kaggle terms before acquisition, redistribution, publication, or use beyond non-commercial research. The license surfaced in a secondary archival citation, not directly readable from the Kaggle page in this review.
- **No contact logs:** Olist cannot empirically establish contact rates, arrival times, topics, handling times, or staffing. DSO1/DSO3 evaluation would depend on simulated operational assumptions until contact traces are obtained.
- **Temporal limits:** roughly two years of historical order data is short for robust annual seasonality analysis; data is historical and Brazil-specific.
- **Proxy validity:** delivery delay and cancellation can motivate plausible support scenarios, but are not labels for actual contacts, returns, refunds, dissatisfaction, or resolutions.
- **Quality and completeness:** the raw files were not downloaded or profiled. Missing timestamps, unmatched rows, duplicate geolocation prefixes, inconsistent table grains, and sparsity must be checked after approval.
- **Evaluation claims:** report observed e-commerce patterns separately from simulated contacts and scenario results. Do not claim operational realism or calibration to a real contact center without real operational traces.

## References and next steps

1. [Olist dataset source and file listing (Kaggle)](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Its current license should be checked directly at acquisition time. [Archival citation identifying CC BY-NC-SA 4.0](https://zenodo.org/records/23121289) is secondary evidence and is not a substitute for the source's current terms.
2. [Online Retail II (UCI)](https://archive.ics.uci.edu/dataset/502/online+retail+ii) — official documentation, file size, instance count, variables, dates, missing values, and CC BY 4.0 license.
3. [H&M Personalized Fashion Recommendations (Kaggle)](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data) — competition description, files, size, and rules-based access.
4. [Creative Commons BY 4.0 deed](https://creativecommons.org/licenses/by/4.0/) — license terms for UCI candidate.

After team approval: (a) confirm Olist license and access terms; (b) acquire only the approved dataset; (c) inspect actual schemas, counts, null rates, table joins, date coverage, and version/checksums; (d) document a source-versus-derived-versus-assumed field inventory; and (e) separately design and validate a synthetic contact-generation study. No database schema or pipeline is proposed in this report.
