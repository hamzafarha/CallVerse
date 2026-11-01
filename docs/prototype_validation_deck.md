# CallVerse Care — Prototype validation deck (content plan)

Two features only: **Live chat** (`localhost:5173/chat`) and **Advisor desk** (`localhost:5173/desk`).
Structure follows the validation mail: for the **selected idea** and the **backup idea**,
1 LLM · 2 Memory · 3 Actions · 4 Tools · 5 Agent pipeline (screenshots) · 6 AI techniques.
Every fact below comes from the code (`src/callverse/agents`, `orchestration`, `llm`, `configs/agents.yaml`)
or from `artifacts/evaluations/`.

---

## Part 0 — Context

### 1. Cover
CallVerse Care — AI agents in action · Prototype validation · Live chat + Advisor desk ·
ESPRIT, Integrated Project (Advanced Data Science) · October 2026 · team names.

### 2. Plan
Context → Selected idea (6 points) → Backup idea (6 points) → Selected vs backup → Results → Live demo.

### 3. The problem and the two features
- Online-shop customer service: customers ask where their order is, want a refund, report a damaged item.
- Goal **BO2 / DSO2**: correct, policy-compliant answers and satisfied customers.
- **Live chat**: a real person (the customer) chats with the AI advisor. A *Behind the scenes* panel shows every agent step live.
- **Advisor desk**: the Client agent plays real customers waiting in a queue; a human advisor answers with the AI as **copilot** (drafts every reply) or **autopilot** (answers alone).
- Data: 99,441 real Olist orders, real Bitext customer sentences, 10 policy documents (58 sections).

### 4. Selected idea vs backup idea (the switch rule)
| | Selected idea (production) | Backup idea |
|---|---|---|
| Name | Hybrid agentic RAG advisor + LLM judge (`rag_policy`) | Intent classifier + approved templates + checklist reviewer (`template`) |
| Who decides | The company rules engine | The company rules engine |
| Who writes | SmolLM3-3B (LLM) | Approved templates |
| Who grades | Granite-4.0-1B (LLM judge) | Checklist reviewer (rules) |
| In the app | **Local LLM** switch | **Offline** switch (also automatic fallback if the GPU fails) |

- Variant kept for comparison: **Pure RAG** (`rag`) — the LLM itself chooses the tools and the answer (switch *Hybrid / Pure RAG* on the chat page).
- Switch rule (decided in advance): ≤ 10% wrong answers **and** judge agreement kappa ≥ 0.4.
- Why hybrid: in the first tests, the small LLM alone invented order numbers and promises.

### 5. The agent team
| Agent | Role | Live chat | Advisor desk |
|---|---|---|---|
| Client agent | Plays the customer (real first message, order, hidden problem, persona) | — (a human is the customer) | Plays every waiting customer |
| Workforce agent | Predicts the problem family, picks the best-skilled desk, quotes the Erlang C wait | ✓ | ✓ |
| Advisor agent | Verifies, retrieves policies, checks the order, writes the reply | Answers the customer | Copilot draft or autopilot |
| Quality agent | Grades the finished chat (5 criteria + correct/resolved) | ✓ at the end | ✓ at wrap-up |
| KPI engine | FCR, CSAT, compliance, policy-correct action, turns | ✓ | ✓ |

All agents are coordinated by **LangGraph**; the browser talks to them through a **WebSocket** (`/ws/session`).

---

## Part A — Selected idea: Hybrid agentic RAG + LLM judge

### 6. A1 · LLMs used and why
| Role | Model | Why |
|---|---|---|
| Advisor + simulated customer | **SmolLM3-3B** (Hugging Face, 3.1 B params, Apache-2.0) | Fully open (weights, data, recipe), supports tool calling, strong for its size; one copy serves two roles, loaded once |
| Quality judge | **Granite-4.0-1B** (IBM, 1.6 B, Apache-2.0) | Different family from the advisor → no self-preference bias; small enough to stay loaded |
| Retrieval | **bge-m3** (BAAI) on CPU | Multilingual embeddings; leaves the GPU to the LLMs |

- Hardware: one laptop GPU, GTX 1650 **4 GB**. 4-bit **NF4** quantization (bitsandbytes) + **bfloat16** compute → both LLMs in ~**3.2 GB**.
- Settings: temperature 0.2 (advisor), 0.7 (client), 0.0 (judge); fixed seed 42; max new tokens 320 / 160 / 256.
- Speed: ~8–13 tokens/s; one advisor reply ≈ 7–10 s.
- Exact model versions pinned (commit hashes in `llm_models.lock.json`).

### 7. A2 · Memory
| Type | What is kept | Where |
|---|---|---|
| Short-term (conversation) | The whole chat, re-sent to the model at every turn | Chat messages |
| Working memory | Intent + confidence, order number, verified?, rules-engine decision (computed once, cached), outcome, hand-over team, summary, escalated? | `AdvisorMemory` (per chat) |
| Shared state | Profile, messages, routing, advisor memory, reference answer, scorecard, KPIs | LangGraph `ConversationState` |
| Long-term (episodic) | Orders, tickets, previous contacts — read **as of the contact time** | SQLite `data/callverse.db` |
| Long-term (semantic) | 58 policy sections, 1,024-d bge-m3 vectors | FAISS index |
| Response cache | SHA-256 of (model, version, messages, tools, temperature, seed) → identical call answered instantly | SQLite cache |

Client agent memory: its profile (real opening message, order, hidden situation, persona, tone) + the chat.
Quality agent memory: the full transcript + the policy-correct reference answer.

### 8. A3 · Actions
**Advisor agent** — (1) greet and ask for the order number (no order data before verification); (2) retrieve the 3 best policy sections; (3) look up the order as it was on the contact day; (4) let the rules engine decide: share tracking, approve a refund, offer replacement or refund, open a carrier investigation, hand over to logistics / payments / seller; (5) open a ticket for the right team; (6) write a short, warm reply, streamed word by word; (7) escalate to a supervisor when asked; (8) close with a summary.
On the desk: draft every reply for the human (**copilot**) or answer alone (**autopilot**).
**Workforce agent** — classify the first message → problem family → best-skilled desk → Erlang C expected wait.
**Client agent** — open with the real message, answer questions, give the order number, may ask for a supervisor (impatient persona), leave and rate 1–5 (CSAT).
**Quality agent** — score compliance, relevance, satisfaction, sentiment, resolution (1–5) + "correct?" + "resolved?" + one-sentence rationale.

### 9. A4 · Tools
| Tool | What it does | Source |
|---|---|---|
| `lookup_order` | Status, dates, items, payment of the order | SQLite |
| `get_ticket_history` | Previous contacts of this customer | SQLite |
| `check_refund_eligibility` | Can this order be refunded / cancelled? | Rules engine |
| `recommend_resolution` | Action, hand-over team, approved answer, policy section | Rules engine |
| `open_ticket` | Hands the case to logistics, payments, the seller or a supervisor | SQLite |
| `search_knowledge_base` | Semantic search in the 58 policy sections | bge-m3 + FAISS |

- **Tool gating**: order tools exist only after the customer gives an order number.
- In the hybrid variant the pipeline itself calls `lookup_order` + the rules engine; the LLM keeps `search_knowledge_base` and `open_ticket` (max 4 tool rounds).
- Stack / APIs: Hugging Face `transformers` + `bitsandbytes`, LangGraph, FastAPI REST + WebSocket, React (Vite), SQLite, FAISS, MLflow + call tracing (`llm_calls.jsonl`). 100% local, no paid API.

### 10. A5 · Pipeline — Live chat (screenshot `docs/guide/img/fo_chat.png`)
1. Customer message → 2. Workforce agent: intent (90% confidence), desk, Erlang C wait → 3. Advisor: bge-m3 search (top 3 sections with cosine scores) → 4. No order number yet → asks for it → 5. Order lookup ✓, rules engine ✓, ticket opened ✓ → 6. SmolLM3 writes the reply (streamed) → 7. End of chat: Granite judge scorecard + KPIs.

### 11. A5 · Pipeline — Advisor desk (screenshot `docs/guide/img/fo_desk_copilot.png`)
1. Queue of simulated customers (real first messages, wait timers) → 2. Accept → Workforce decision → 3. Advisor drafts the reply (copilot draft, sources, tool calls) → 4. Human: **Send draft**, **Edit first**, or **Autopilot** → messages labelled "human · AI draft" / "human · edited AI draft" → 5. Client agent answers → loop → 6. Wrap up → Quality scorecard + KPIs.

### 12. A5 · Pipeline — under the hood
LangGraph map: `client_open → workforce_route → advisor ⇄ client_reply → quality → kpi` (loop until the customer leaves or 4 customer turns).
WebSocket events: `ready · stage · token · message · routing · advisor_state · suggestion · review · done`.
One GPU lock: only one generation at a time on the 4 GB card.

### 13. A6 · AI techniques (1/2) — RAG + agents
- **RAG**: bge-m3 (1,024-d, L2-normalised) + FAISS exact inner product (= cosine); query = first + latest customer message; top 3 sections injected as POLICY CONTEXT.
- **"No answer" threshold 0.57**: chosen from a threshold sweep — keeps 95.5% of in-scope questions, rejects 58.3% of out-of-scope ones.
- **Agentic tool calling** (function calling, up to 4 rounds) + **hybrid rule**: the rules engine decides, the LLM only writes.
- **Multi-agent orchestration** with LangGraph (explicit state machine).

### 14. A6 · AI techniques (2/2) — prompting, guardrails, no fine-tuning
- **Advanced prompt engineering**: system prompt with 6 playbook rules, today's date, predicted intent and retrieved policies; injected system messages (order number / "ask for it first"); a POLICY DECISION block ("follow it exactly, add nothing"); role-play prompt for the client; strict rubric prompt with a reference answer for the judge; JSON outputs (generation stops at the closed object + repair step).
- **Guardrails**: tool gating · verification guardrail (a reply before verification always asks for the order number) · English-only check (regenerates if the reply drifts to Portuguese) · client fallback if it talks like an advisor.
- **LLM-as-judge** from another family, calibrated with Cohen's quadratic kappa (trusted at ≥ 0.4).
- **Fine-tuning: not used, on purpose** — 4 GB GPU, no labelled dialogues of our own, and the company rules already live in the rules engine. We adapt the models with quantization + prompting + RAG instead. (Only the backup's intent classifier is trained.)

---

## Part B — Backup idea: offline agents (no LLM)

### 15. B1 · Model used
No LLM. **TF-IDF + logistic regression** intent classifier (99.0% accuracy on held-out Bitext sentences) + rules engine + approved answer templates + checklist reviewer + rule-based customer.
Why: deterministic, instant, works without a GPU, cannot invent an answer. It also runs automatically if the LLM fails (`template_fallback`).

### 16. B2 · Memory
Same `AdvisorMemory` per chat (intent, order number, answered, outcome, hand-over, escalated, summary), same SQLite store read as of the contact time, same chat history. No LLM cache needed.

### 17. B3 · Actions
Greet + ask for the order number → look up the order → refund check for refund / cancel intents → rules engine picks the outcome → open a ticket if a hand-over is needed → fill the approved template → escalate to a supervisor when the customer asks → closing message with the summary.
Checklist reviewer: verified? order looked up? policy cited? no card data asked? + lexicon sentiment → same 5-criterion scorecard.

### 18. B4 · Tools
`lookup_order`, `check_refund_eligibility`, `open_ticket`, the rules engine (`decide_outcome`) and the template library — **called directly by code**, never chosen by a model. Intent classifier (scikit-learn).

### 19. B5 · Pipeline
Customer message → classify intent → verify (order number) → look up order → rules decide → fill template → (supervisor escalation) → checklist review → KPI row.
Demo: switch **Offline** on the chat page or the desk — the header shows "offline backups".

### 20. B6 · AI techniques
Supervised text classification (TF-IDF + logistic regression) · rule-based expert system (company policy as a decision table) · template-based text generation · lexicon-based sentiment · rule-based quality checklist.

---

## Part C — Evidence and demo

### 21. Selected vs backup
| | Selected (hybrid RAG + LLM) | Backup (offline) |
|---|---|---|
| Language | Natural, adapts to follow-ups | Fixed, approved wording |
| Correct action | Decided by the rules engine | Decided by the rules engine |
| Speed | ~7–10 s per reply (laptop GPU) | Instant |
| Needs | GPU + downloaded models | Nothing |
| Risk | Style / language drift (guarded) | Rigid, less human |

### 22. Results (measured)
Policy search on 255 questions:

| Retriever | Recall@1 | Recall@4 | MRR |
|---|---|---|---|
| Keyword baseline (TF-IDF) | 52.9% | 80.4% | 0.64 |
| **bge-m3 + FAISS** | **80.0%** | **96.9%** | **0.87** |

French questions: bge-m3 finds the right section in the top 4 for 100% (TF-IDF 55.9%).

Conversations (12 per LLM variant, first LLM stack; 40 offline):

| Variant | Policy-correct answer | Compliance | CSAT (1–5) | FCR |
|---|---|---|---|---|
| Pure RAG (LLM decides) | 0% | 100% | 3.58 | 66.7% |
| **Hybrid (rules decide, LLM writes)** | **100%** | 83.3% | **4.33** | 50.0% |
| Backup (templates) | 100% | 100% | 3.83 | 75.0% |

Judge: LLM judge kappa 0.06 (satisfaction) → **not trusted yet**; checklist kappa 0.39 on resolution.
Verdict: **hybrid kept**, the LLM judge stays under evaluation.

### 23. Limits and next steps
- Re-run the conversation tests with the Hugging Face models (the table above used the first LLM stack).
- Grade 60 chats by hand (labeling page) to calibrate the judge (switches to human labels from 20).
- ~7–10 s per reply on a 4 GB GPU; a bigger GPU would allow larger models.

### 24. Live demo + thank you
1. `/chat`: "I have a delivery issue" → give the order number → watch the pipeline, the trace and the quality review.
2. Switch **Offline** → same chat with the backup.
3. `/desk`: take the longest-waiting customer → send / edit the copilot draft → autopilot → wrap up.
