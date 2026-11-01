# DSO2 prototype validation deck: slide plan

Source of the ideas: `CallVerse_DSO_Ideas.docx` (DSO2: idea A, idea B, backup).
Mail plan for every idea: 1 LLM used, 2 Memory, 3 Actions, 4 Tools, 5 Agent pipeline
(screenshot), 6 AI techniques. The deck shows the real prototype: `/chat` = idea A,
`/desk` = idea B, the **Offline** switch = backup.

Canva template: "Thynk Unlimited" AI deck (15 layouts, `T1`–`T15` below).

## Part 0: context

| # | Layout | Title | Content |
|---|---|---|---|
| 1 | T1 cover | CALLVERSE CARE | DSO2 · AI advisor + AI reviewer · prototype validation |
| 2 | T12 list | Agenda | The problem and our 3 ideas · Idea A (/chat) · Idea B (/desk) · Backup, results, live demo |
| 3 | T2 text | DSO2: advisor + reviewer | Problem: customers need correct answers, the company must check quality automatically. Analogy: a new employee with the company handbook + a supervisor who grades the calls. Data: 99,441 Olist orders, Bitext questions, 9,179 contacts and tickets in SQLite, 10 policy documents (58 sections). |
| 4 | T4 four circles | Our three ideas | A: smart advisor + AI judge · B: co-pilot + multi-check reviewer · Backup: question sorting + ready-made answers · Switch rule: beat keyword FAQ search; A → backup if > 10% wrong answers or judge kappa < 0.4; B → backup if no measurable gain |
| 5 | T13 rows | The agent team | Client (plays the customer) · Workforce (intent, desk, Erlang C wait) · Advisor (answers) · Quality (grades) — orchestrated with LangGraph |

## Part A: idea A, smart advisor + AI judge (page `/chat`)

| # | Layout | Point | Content |
|---|---|---|---|
| 6 | T14 | Idea A | The advisor searches the company documents and tools before answering; a second AI grades the chat with a scorecard. Strong: closest to our architecture, most innovative. Weak: can make up answers, AI judge can be inconsistent → we added a rules engine and calibrate the judge. |
| 7 | T6 three items | 1 · LLMs used | SmolLM3-3B (advisor: open, tool calling, 4-bit fits a 4 GB GPU) · Granite-4.0-1B (judge: other family, no self-preference) · bge-m3 (multilingual embeddings for RAG, on CPU) |
| 8 | T10 text + 4 items | 2 · Memory | Short-term: the chat history re-sent every turn · Working memory: AdvisorMemory (intent, order number, verified, outcome, hand-over, summary) · Shared state: LangGraph ConversationState · Long-term: SQLite orders + tickets read as of the contact time, FAISS index, SHA-256 LLM cache |
| 9 | T4 | 3 · Actions | Verify (order number first) · Search the 3 best policy sections · Look up the order, rules engine decides, open a ticket · Write the reply (streamed), then the judge grades 5 criteria |
| 10 | T13 | 4 · Tools | lookup_order + get_ticket_history · check_refund_eligibility + recommend_resolution (rules engine) · search_knowledge_base (bge-m3 + FAISS, 58 sections) · open_ticket (logistics, payments, seller, supervisor). Stack: transformers, bitsandbytes, LangGraph, FastAPI, React |
| 11 | T7 + screenshot | 5 · Pipeline (/chat) | `fo_chat` crop: customer → Workforce → Advisor (bge-m3, tools, LLM) → reply with tool chips |
| 12 | T7 + screenshot | 5 · Pipeline (judge) | `fo_chat_review` crop: Granite judge scorecard, radar, policy reference |
| 13 | T5 text + 4 labels | 6 · Techniques (1/2) | RAG (cosine, top 3, no-answer below 0.57) · agentic tool calling (up to 4 rounds) · hybrid rule (POLICY DECISION block) · LangGraph multi-agent state machine |
| 14 | T12 | 6 · Techniques (2/2) | Advanced prompt engineering (playbook rules, JSON outputs) · guardrails (tool gating, verification, English-only) · LLM-as-judge calibrated with kappa · no fine-tuning (4 GB GPU, no labelled dialogues) |

## Part B: idea B, co-pilot + multi-check reviewer (page `/desk`)

| # | Layout | Point | Content |
|---|---|---|---|
| 15 | T9 | Idea B | The AI does not talk to the customer: it drafts each reply for a human advisor, shows the policy and the next step; the review combines 3 checks. Strong: safer, a human validates. Weak: we must simulate one side, the gain is harder to measure. |
| 16 | T3 | 1 · LLMs used | SmolLM3-3B writes the drafts and also plays the customer (Client agent, role-play) · Granite-4.0-1B grades. Same weights loaded once: one 3B model + one 1.6B judge = ~3.2 GB. |
| 17 | T8 | 2 · Memory | Same AdvisorMemory + draft memory: every sent message keeps the draft and whether it was edited ("human · AI draft" / "edited AI draft") · Customer 360: order timeline + previous contacts · desk queue |
| 18 | T4 | 3 · Actions | Draft the reply · Show policy sources, next step (rules-engine action, hand-over) and confidence · Human: send, edit first or Autopilot · Wrap up → 3 checks |
| 19 | T13 | 4 · Tools | Same advisor tools behind each draft · Customer 360 API (order, items, previous tickets) · Workforce routing (intent + confidence, desk, Erlang C) · WebSocket desk actions (suggest, advisor_message, autopilot, end) |
| 20 | T7 + screenshot | 5 · Pipeline (/desk) | `fo_desk_copilot`: queue, pipeline, COPILOT DRAFT, policy state, sources with scores, Workforce decision |
| 21 | T7 + screenshot | 5 · Multi-check reviewer | `fo_desk_quality`: AI scorecard (Granite) + mood (sentiment criterion + customer CSAT) + fact-check (answer vs the rules-engine policy reference) |
| 22 | T10 | 6 · Techniques | Human-in-the-loop co-pilot · confidence signals (intent confidence, similarity scores, 0.57 no-answer, hand-over) · multi-check review (judge + mood + fact-check) · LLM role-play to simulate the customer (personas) |

## Part C: backup, question sorting + ready-made answers (switch **Offline**)

| # | Layout | Point | Content |
|---|---|---|---|
| 23 | T14 | Backup | The AI sorts the question into a type and replies with a pre-approved answer filled with the order details; a checklist + mood score reviews the chat. Covers both parts of DSO2; also the automatic fallback when the GPU or a model fails. |
| 24 | T3 | 1 · Model | No LLM: TF-IDF + logistic regression intent classifier, 99.0% accuracy on held-out Bitext sentences. Why: deterministic, instant, no GPU, cannot invent an answer. |
| 25 | T11 two circles | 2 · Memory + 4 · Tools | Memory: same AdvisorMemory and SQLite store, no LLM cache · Tools: lookup_order, check_refund_eligibility, open_ticket, decide_outcome, template library, called by the code (never chosen by a model) |
| 26 | T4 | 3 · Actions | Sort the question · Verify + look up the order · Rules decide + fill the approved template (or escalate) · Checklist review (verified? looked up? policy cited? no card data?) + lexicon mood |
| 27 | T7 + 2 screenshots | 5 · Pipeline (Offline) | `fo_chat_offline` + `fo_chat_offline_review` (captured on 22 Oct 2026): "offline backups · approved templates", tool chip, checklist judge |
| 28 | T6 | 6 · Techniques | Supervised text classification · rule-based expert system (policy decision table) · template generation + lexicon sentiment + rule-based checklist |

## Part D: evidence and demo

| # | Layout | Title | Content |
|---|---|---|---|
| 29 | T13 | A vs B vs backup | Who answers · wrong answers (rules decide, human check, approved text) · speed + needs (GPU vs none) · reviewer (judge / judge + mood + fact-check / checklist + mood) |
| 30 | T7 two paragraphs | Measured results | see below |
| 31 | T12 | Limits & next steps | Re-run the conversation tests on the current GPU stack · grade 60 chats by hand to calibrate the judge · measure B with real human advisors (edit rate, handle time) · speed (7–10 s per reply on 4 GB) |
| 32 | T4 | Live demo | /chat (idea A) · /desk (idea B) · Offline (backup) · quality reviews; fallback: screenshots on slides 11, 12, 20, 21, 27 |
| 33 | T15 | Thank you | Questions? |

### Measured results (slide 30)

- Policy search, 255 questions: bge-m3 + FAISS Recall@1 80.0%, Recall@4 96.9%, MRR 0.87 vs keyword FAQ
  search (the DSO2 baseline) 52.9%, 80.4%, 0.64. French questions: 100% vs 55.9% in the top 4.
- Conversations (12 per LLM variant, first LLM stack; 40 offline): pure RAG 0% policy-correct, CSAT 3.58;
  **hybrid (idea A) 100%, CSAT 4.33**; backup 100%, CSAT 3.83. LLM answers: 93–99% of sentences supported
  by the retrieved policy or tool results.
- Judge agreement (60 chats, proxy labels): first LLM judge (Llama 3.2) kappa 0.06 (satisfaction and
  resolution), checklist kappa 0.39 (resolution) → below 0.4, the AI judge is **not trusted yet**. Today's
  judge (Granite-4.0-1B) has not been measured yet.
- Live chats on the current GPU stack (informal, 15 chats): 15/15 policy-correct.
- Decision: idea A's advisor passes the switch rule; its AI judge does not yet, so the checklist reviewer
  (backup) stays the reference while the judge is calibrated. Idea B works end to end on /desk but its gain
  is not measured yet. The backup is ready and switches on automatically.
