# CallVerse Phase 4a — Knowledge Base for the Advisor Report

**Notebook:** `notebooks/11_knowledge_base_retrieval.ipynb`  
**Code:** `src/callverse/agents/advisor/indexing.py`, `src/callverse/agents/advisor/retrieval.py`, `scripts/build_knowledge_base.py`  
**Tests:** `tests/unit/test_knowledge_base.py`  
**Inputs:** `data/knowledge_base/docs/*.md`, Bitext messages (`data/raw/bitext/`), `configs/agents.yaml`, `configs/data.yaml`  
**Prepared:** 14 October 2026  
**Scope:** Writing the knowledge-base documents, indexing them with bge-m3 and FAISS, and evaluating retrieval. No answer generation (LLM) yet: that is the advisor agent itself.

## Executive summary

The advisor agent needs company rules to answer from, so that it never invents a refund delay
or a return condition. Olist publishes no policies, so version 1 writes them for a fictional
store, grounded in what the Olist data shows (order statuses, payment methods, delivery times).

| Output | Size | Purpose |
|---|---|---|
| `data/knowledge_base/docs/*.md` | 10 documents (8 policies, 1 FAQ, 1 advisor playbook) | Source text, tracked in git |
| `data/knowledge_base/index/` | 58 chunks × 1024 dimensions | FAISS index, chunk table, manifest (rebuilt by script) |
| `artifacts/evaluations/knowledge_base_*` | 4 CSV files, 1 figure | Retrieval metrics |

Main results (1,020 Bitext customer messages, 60 per intent):

| Method | hit@1 | hit@4 | MRR@4 | French hit@4 | ms / query (CPU) |
|---|---:|---:|---:|---:|---:|
| TF-IDF (lexical) | 0.526 | 0.799 | 0.639 | 0.559 | <0.1 |
| all-MiniLM-L6-v2 | 0.782 | 0.963 | 0.860 | 0.412 | 3 |
| **bge-m3 (chosen)** | **0.837** | **0.969** | **0.892** | **1.000** | 50 |

- The advisor sees a relevant section for **97% of questions** (hit@4).
- bge-m3 is chosen over the much smaller MiniLM because it **keeps working in French** (34
  questions, 100% vs 41%), at a cost of 50 ms per question.
- A top-1 score below **0.57** means "no answer in the knowledge base". This keeps 95.5% of
  covered questions and rejects all clearly unrelated ones (password, account, app).

> **Limit.** Relevance is judged by intent tags that were written together with the documents.
> The evaluation shows that the search finds the section *intended* for each kind of question;
> it does not check that the policies themselves are realistic.

## Design decisions

| Topic | Decision | Reason |
|---|---|---|
| Content | Synthetic policies of a fictional store; facts from Olist, rules as explicit assumptions | Olist has no policy documents |
| Grounding | Status lifecycle, payment methods, 24 installments, boleto approval time (~29 h), promised vs actual delivery (24 vs 10 days median), 6.8% late deliveries, multi-seller parcels | Measured in `olist_orders_analytical.parquet` and `olist_payments_prepared.parquet` |
| Legal periods | 7-day right of withdrawal, 30/90-day defect periods | Brazilian Consumer Defense Code (CDC arts. 49 and 26), matching Olist's market |
| Language | English documents | Same decision as the contact generator (`language: english`); bge-m3 handles French questions |
| Intents | The 17 order-linked intents of `configs/data.yaml`; each `##` section declares the intents it answers | Allows intent-filtered search and an automatic evaluation |
| Chunking | One chunk per `##` section (longer than 1,500 characters: split on paragraphs) | Sections are short and self-contained; the advisor can cite "document > section" |
| Embedding text | `document title - section title` + section text | Gives short sections their context |
| Model | `BAAI/bge-m3`, normalised dense vectors, local CPU | Multilingual, zero cost, no API call (project assumption) |
| Index | FAISS `IndexFlatIP` (exact cosine) | 58 chunks: approximate indexes would only add error |
| Safety checks | Pydantic validation of front matter; unknown intent names fail the build; the manifest stores the model name and a SHA-256 per document, and loading refuses a stale or mismatched index | A silent mismatch would return wrong policies |

## Documents

| Document | Type | Chunks | Main intents |
|---|---|---:|---|
| `order_status_and_tracking` | policy | 5 | track_order, track_delivery |
| `delivery_times_and_delays` | policy | 6 | delivery_time, delivery_issue |
| `cancellations_and_order_changes` | policy | 6 | cancel_order, change_order |
| `refund_policy` | policy | 5 | request_refund, refund_status |
| `returns_and_exchanges` | policy | 6 | return_product, return_product_online, exchange_product |
| `damaged_wrong_missing_items` | policy | 5 | damaged_delivery, wrong_item, missing_item, product_issue |
| `payment_policy` | policy | 6 | payment_issue |
| `invoices` | policy | 4 | request_invoice |
| `customer_faq` | faq | 10 | all (one answer per topic) |
| `advisor_playbook` | procedure | 5 | identity checks, compensation limits, escalation, tone |

Every intent is covered by 3 to 8 chunks.

## Evaluation

**Test set.** Bitext messages of the 17 intents, 60 per intent (seed 42), without the
offensive tag `W`. Out-of-scope set: 10 messages for each of 24 intents the knowledge base was
not written for. 95% intervals are bootstrap intervals over queries.

**Per intent (bge-m3).** Top-1 is weakest for `delivery_issue` (0.18), `track_order` (0.35)
and `request_refund` (0.38); top-4 for these is 0.97, 0.72 and 0.88. Ten intents reach a
top-1 of 0.97 or more.

**Error analysis.** The 166 top-1 misses are mostly explained by three causes:

1. "Report a delivery problem" lands on the FAQ answer about damaged or incomplete parcels, a
   neighbouring topic.
2. Customers write "reimbursement", a word absent from the documents; the internal
   "Compensation authority" section then ranks first for 28 refund requests.
3. Bitext `track_order` includes questions on the status of a *replacement*, which match the
   exchange section.

**No-answer threshold.** At 0.57, clearly unrelated questions (password, account, app,
product ideas) are always rejected. General policy questions (`refund_policy`,
`return_policy`, `shipping_costs`, `payment_methods`) are kept, which is correct because the
documents answer them. The value is stored as `no_answer_score` in `configs/agents.yaml`; the
retriever itself keeps `min_score: 0.0` so the advisor can still inspect weak matches.

![Top-1 score distribution](../artifacts/evaluations/knowledge_base_score_distribution.png)

## How to rebuild and use

```bash
pip install -e ".[heavy]"            # sentence-transformers, faiss-cpu
python scripts/build_knowledge_base.py
```

```python
from callverse.agents.advisor import KnowledgeRetriever, load_knowledge_base_config

retriever = KnowledgeRetriever.from_config(load_knowledge_base_config("configs/agents.yaml"))
for hit in retriever.search("my parcel is late", intent="delivery_issue"):
    print(hit.score, hit.chunk.doc_id, hit.chunk.section)
```

The first run downloads bge-m3 (about 2.2 GB) into the Hugging Face cache.

**Windows note.** pyarrow 17 ships its own old `msvcp140.dll`; when pandas is imported before
torch, torch then fails to load (`WinError 1114`). pyarrow was upgraded to 21.0.0, the newest
version that still supports NumPy 1.26; all existing Parquet files were re-read with
unchanged shapes.

## Next steps

1. Add customer vocabulary ("reimbursement", "replacement status") to the documents and
   re-evaluate on a **new** Bitext sample (the current one was used to find the problems).
2. If top-1 must improve: hybrid search (BM25 + dense) or a reranker (`bge-reranker-v2-m3`).
3. Tag the general policy intents the documents already answer.
4. Advisor agent (Phase 4b): retrieval + order lookup tools + LLM answer citing sections.
