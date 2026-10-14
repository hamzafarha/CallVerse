# CallVerse Phase 1F — Tickets, Chat Logs and SQLite Store Report

**Notebook:** `notebooks/12_tickets_chats_database.ipynb`  
**Code:** `src/callverse/data/tickets.py`, `src/callverse/data/conversations.py`, `src/callverse/data/database.py`, `scripts/build_database.py`  
**Tests:** `tests/unit/test_tickets.py`, `tests/unit/test_database.py`  
**Inputs:** `synthetic_contacts.parquet` (Phase 1E), Olist prepared and analytical tables, `configs/data.yaml` (`generation.tickets`, `database`), `configs/simulation.yaml` (handle times), knowledge-base documents (cited sections)  
**Prepared:** 14 October 2026  
**Scope:** Generating one ticket and one chat log per synthetic contact, and storing them with the Olist tables in SQLite. No agent, no queue simulation.

## Executive summary

| Output | Size | Purpose |
|---|---|---|
| `synthetic_tickets.parquet` | 9,179 × 23 | One case per contact: status at contact time, outcome, follow-up, escalation, handle and resolution times, satisfaction |
| `synthetic_chat_messages.parquet` | 60,837 × 7 | Chat messages (6 to 8 per ticket), each advisor answer citing its knowledge-base section |
| `data/callverse.db` | 129 MB, 9 tables | SQLite store with primary keys, foreign keys and indexes, opened read-only by agents |

Main results:

- All 10 consistency checks pass (timelines, message order, cited sections exist); the
  generator is reproducible with its fixed seed.
- Handle times match the simulation config (means within 1%), so tickets and the simulated
  queue describe the same contact center.
- Synthetic KPIs: strict first-contact resolution **53%**, escalation **3.2%**, **4.9 days**
  to resolve on average, satisfaction **3.93 / 5** (30% response).

> Tickets and chats are **synthetic**. Olist has no support data: every rule and rate is an
> explicit assumption in `configs/data.yaml`.

## Design decisions

The first three decisions were made by the project owner before implementation.

| Topic | Decision | Reason |
|---|---|---|
| Ticket grain | One ticket per contact | Simplest; matches the simulation (one contact = one service). Repeat contacts on an order (384 orders) stay linkable by `order_id` |
| Channel | Chat for every contact | Matches "chat logs", the single queue of the simulation and Bitext's chat-style messages |
| Chat method | Templates | All 9,179 chats in 3 seconds, deterministic, always consistent with the policies. A local LLM (llama3.2) would take ~25-35 h on the project GPU |
| Status at contact | Rebuilt from timestamps: created, approved, shipped, delivered, canceled/unavailable | The final `order_status` is only known in hindsight (Phase 1D `available_at` rule) |
| Outcome | Rules per intent family, each following a knowledge-base section | Explainable and policy-consistent |
| Carrier investigation | Past the estimated date and more than 7 days late, **or** more than 25 days in transit | Policy has "no tracking movement for 5 business days"; Olist has no tracking events, so long transit (95th percentile of carrier-to-delivery = 24.2 days) stands in |
| Handle time | Lognormal per intent group from `configs/simulation.yaml` | One source of truth for handle times |
| Resolution time | End of chat + business days of the outcome; investigations end early if the parcel is delivered | Uses the policy delays |
| Supervisor requests | 1% of cases resolved in chat, 6% of those with follow-up | Assumption; feeds escalation KPIs and the quality agent |
| Satisfaction | 30% answer; score shares by outcome class | Directional chat benchmarks (~80-85% satisfied) |
| Leakage guard | `generator_*` columns (hidden cause) are **not** loaded into SQLite | Agents querying the store must not see why a contact was generated |
| SQLite load | Built under a temporary name, swapped in only after `PRAGMA foreign_key_check` passes | A failed build never leaves a half-written store |

### Outcome classes

| Class | Meaning | Share |
|---|---|---:|
| `resolved_in_chat` | Nothing left to do when the chat ends | 53.4% |
| `follow_up` | Work remains: return, investigation, seller check, bank details | 43.4% |
| `escalated` | Supervisor requested, or payments team | 3.2% |

First-contact resolution is defined **strictly** (`resolved_in_chat` only), so a sent return
label counts as not resolved at first contact.

## Tables

### `tickets` (main columns)

| Column | Meaning |
|---|---|
| `ticket_id`, `contact_id`, `order_id`, `customer_unique_id` | Keys (`TK000001` matches contact `SC000001`) |
| `channel`, `intent`, `intent_group`, `opened_at` | From the contact |
| `order_status_at_contact`, `days_past_estimate` | What the advisor could see at that moment |
| `outcome`, `outcome_class`, `handed_to`, `kb_chunk_id` | Decision, its class, party handling the follow-up (seller, carrier, payments team, supervisor), policy section applied |
| `supervisor_requested`, `handle_seconds`, `chat_closed_at`, `resolved_at`, `first_contact_resolution`, `csat_score` | Lifecycle and quality |

### `chat_messages`

`message_id` (`TK000001-03`), `ticket_id`, `turn`, `speaker` (customer / advisor), `sent_at`,
`text`, `kb_chunk_id` (advisor turns only). The first message is the contact's Bitext message
and is sent at `opened_at`; the last is sent at `chat_closed_at`.

### SQLite store

| Table | Rows | Primary key | Foreign keys |
|---|---:|---|---|
| customers | 99,441 | customer_id | |
| sellers | 3,095 | seller_id | |
| products | 32,951 | product_id | |
| orders | 99,441 | order_id | customer_id |
| order_items | 112,650 | order_id, order_item_id | order_id, product_id, seller_id |
| payments | 103,886 | order_id, payment_sequential | order_id |
| contacts | 9,179 | contact_id | order_id |
| tickets | 9,179 | ticket_id | contact_id, order_id |
| chat_messages | 60,837 | message_id | ticket_id |

Timestamps are stored as ISO text (`YYYY-MM-DD HH:MM:SS`), which sorts and compares correctly
in SQL. Reviews are not loaded (not needed by the advisor; still in Parquet).

## Limits

- **Chats are templates**: little vocabulary and fixed structure. Good for testing tools,
  retrieval and the quality rubric; not for training a language model.
- **Bitext labels**: a few first messages fit their intent loosely (for example a
  `track_order` message about a *replacement*), so the answer can look slightly off-topic.
- **Future in the store**: `orders` keeps the final status and all timestamps. Advisor tools
  must rebuild the status as of the chat time (`order_status_at`).
- **No cancellation date** in Olist: canceled orders are treated as canceled from the start.

## How to rebuild

```bash
python scripts/build_database.py      # ~15 s: tickets, chats, Parquet, SQLite
```

```python
from callverse.data import connect
import pandas as pd

with connect("data/callverse.db") as connection:     # read-only
    pd.read_sql("SELECT * FROM tickets WHERE order_id = ?", connection, params=[order_id])
```

## Next steps

1. Advisor tools (`mock_store`): order lookup *as of* a time, customer ticket history.
2. Pydantic schemas and Pandera checks for contacts, tickets and messages (data pipeline box).
3. Optional: a small LLM-written chat set for demos and the quality agent.
