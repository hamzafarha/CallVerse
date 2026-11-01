# CallVerse — Integrated Project Validation Report

**A multi-agent digital twin of an e-commerce customer service center**
Commercial and technical validation · Advanced Data Science integrated project (ESPRIT)
Author: Hamza Farhani · Version 1.0 · October 2026

---

## Executive summary

**Problem.** An e-commerce customer service center fails in two expensive ways: too few
advisors when contacts spike (promotions, delivery delays) and too many when it is quiet.
Staffing is the largest cost of a contact center, yet staffing and routing decisions are
usually made on experience and tested directly on real customers.

**Solution.** CallVerse is a *virtual copy* of the center. It forecasts how many customers
will contact the company and why, replays those customers through a discrete-event
simulation, and lets four cooperating AI agents act inside it: a **Client** agent that plays
customers, an **Advisor** that answers with company knowledge and business tools, a
**Quality** agent that grades every conversation, and a **Workforce** agent that plans shifts
and routes customers. A manager tests a decision in the twin — in seconds — before applying it.

**Framework.** Four business objectives (BO) are mapped to four data science objectives
(DSO), each with a baseline it must beat and a simpler backup that takes over if it does not.

| BO | DSO | Main idea | Baseline | Headline result |
|---|---|---|---|---|
| BO1 shorter waits | DSO1 routing | MaskablePPO (RL) | FIFO + skill matching | PPO: ASA **−14%** on unseen stressed days, 90th-percentile wait −18% to −25% in peak weeks; the backup (tuned skill score) cuts abandonment by 8–11% |
| BO2 correct answers, CSAT | DSO2 advisor + judge | agentic RAG + LLM judge | keyword FAQ search | context recall@4 **96.9%** vs 80.4%; hybrid advisor **12/12** verified policy-correct actions, CSAT 4.33; judges not yet trusted (kappa < 0.4) |
| BO3 lower cost, same service | DSO3 shift planning | forecast + OR-Tools CP-SAT | fixed schedule | **−40%** labour cost, service level still above the 80% target, all labour rules respected |
| BO4 prepare for peaks | DSO4 forecast + twin | LightGBM + SimPy twin | same day last week; Erlang C | wMAPE **25.3% vs 31.6%**; testing first cuts understaffed hours by **60–84%** |

**Verdict.** The technical foundation (DSO4) and the planning objective (DSO3) clearly
beat their baselines. DSO1 and DSO2 deliver measurable gains but, following our own switch
rules, their *production* configuration is the backup or a hybrid (tuned skill-score
routing; LLM advisor constrained by a rules engine), while the pure-AI versions remain the
research track. Every result is reproduced by one command (`callverse all`) and reported
with 95% confidence intervals over 10 seeds.

**Honest limit.** There are no public call-center logs. Contacts, tickets and chats are
generated from 99,441 real Olist orders with explicit, documented rates. The results prove
that the method works and is decision-ready; the euro amounts must be recalibrated on a
client's real logs, which the pipeline accepts unchanged.

---

# Part A — Commercial validation

## A1. Context and problem

E-commerce support volume is driven by orders and by what goes wrong with them: late
deliveries ("where is my order?"), cancellations and refunds, wrong or damaged items,
payment questions. These drivers are *predictable* (orders, promotions, carrier delays are
known in advance) but most centers still plan from last year's average and react to peaks.

Consequences of the status quo:

- **Peaks hurt customers**: long waits, abandoned chats, repeat contacts, bad reviews.
- **Quiet periods waste money**: paid advisors with nothing to do.
- **Decisions are tested on real customers**: there is no safe place to try "what if the
  promotion doubles tracking questions?" or "what if 20% of agents are sick?".
- **AI assistants are adopted without measurement**: chatbots answer customers, but few
  companies measure whether the answers follow policy or whether the AI grader agrees with humans.

## A2. Target customers and users

| Segment | Who decides | What they need |
|---|---|---|
| Mid-size e-commerce retailers and marketplaces (20–300 advisors) | Head of Customer Service, COO | fewer understaffed peaks, controlled cost |
| BPO / outsourced contact centers | Operations director | planning that respects labour rules and SLAs per client |
| Workforce-management (WFM) teams | WFM planner | a forecast per contact reason, a schedule in minutes, scenario testing |
| CX quality teams | Quality manager | automatic grading of 100% of conversations, trusted against human graders |

**Personas.** *Sara, WFM planner*: builds the weekly roster in spreadsheets and dreads
promotion weeks. *Karim, Head of CS*: must cut cost by 10% without hurting CSAT.
*Lina, Quality manager*: listens to 2% of conversations and cannot see the rest.

## A3. Value proposition

| Customer jobs | Pains | Gains | CallVerse features |
|---|---|---|---|
| Staff the center each week | understaffed peaks, overtime surprises | right staff at the right hour | forecast per intent → Erlang C need → CP-SAT roster |
| Prepare promotions and incidents | decisions tested on real customers | decide before the event | digital-twin what-if in ~3 s, 10 seeds, confidence intervals |
| Answer customers correctly | inconsistent answers, policy breaches | consistent, policy-correct answers | RAG advisor on the knowledge base + order tools + rules engine |
| Control quality | 2% sampling, subjective grading | every conversation graded, trusted | LLM judge + calibration against human labels (kappa) |
| Justify budgets | no evidence | quantified savings | KPI engine: wait, abandonment, cost per contact, money saved by testing |

Positioning statement: *For customer-service leaders of e-commerce companies who must
handle unpredictable peaks at controlled cost, CallVerse is a decision twin that tests
staffing, routing and AI-answering policies on a virtual copy of their center before
customers feel them — unlike classic WFM tools that only forecast and schedule, it
simulates the consequences and grades AI conversations, and it runs on-premise with local
models so customer data never leaves the company.*

## A4. Market and competition

The workforce-engagement and contact-center software market is mature and dominated by
large suites; AI agents for customer service are a fast-growing adjacent market.
(Market sizes are deliberately not quoted here: published estimates vary widely between
analysts; they should be sourced and dated in a business plan.)

| Category | Examples | What they do well | Gap CallVerse addresses |
|---|---|---|---|
| CCaaS / WEM suites | NICE CXone, Genesys Cloud, Verint, Calabrio | forecasting, scheduling, quality management at scale | scenario simulation of *decisions* is limited; closed, expensive, cloud data processing |
| Modern WFM for digital support | Assembled, Playvox, Zendesk WFM | easy scheduling for chat/e-mail teams | little "what-if" simulation; no link to order data |
| AI customer-service agents | Zendesk AI, Intercom Fin, Salesforce Agentforce | automated answers | evaluation of answer quality and grader trust is thin |
| Spreadsheets + Erlang calculators | in-house | cheap, understood | no uncertainty, no routing, no testing |

**Differentiation**: (1) decision testing in a twin with confidence intervals; (2) demand
driven by order events (delays, promotions), not only by past volume; (3) one place for
planning, routing and conversation quality; (4) local LLMs: zero per-token cost and data
privacy; (5) open, explainable models (LightGBM, CP-SAT, rules) with AI where it beats them.

## A5. Business model

| Building block | Content |
|---|---|
| Customer segments | mid-size e-commerce support teams; BPOs; WFM teams |
| Value proposition | test staffing and AI decisions before customers feel them (A3) |
| Channels | direct sales to Heads of CS; integrations marketplace of help-desk tools; partnerships with BPOs |
| Customer relationship | 8-week pilot on the client's logs, then subscription with a customer-success analyst |
| Revenue streams | SaaS subscription per advisor seat per month (planning + twin), add-on per conversation volume for AI quality grading, one-off calibration fee for the pilot |
| Key resources | the twin engine, forecasting and optimization models, the evaluation framework |
| Key activities | calibration on client logs, model maintenance, integrations |
| Key partners | help-desk/CCaaS vendors (data connectors), BPOs, cloud or on-premise GPU providers |
| Cost structure | engineering, hosting (CPU for twin and solver; small GPU only if LLM agents are used), customer success |

Pricing hypotheses (to validate in interviews, not market data): a per-seat price well
below a full WEM suite; the pilot is priced to be paid back by avoided overtime and
avoided lost customers in one peak season.

## A6. ROI logic (from the twin's measured effects)

The twin produces relative effects with confidence intervals; a client converts them into
money with its own costs. With the assumptions of `configs/simulation.yaml`
(€12/hour, overtime ×1.5, €8 per abandoned customer):

- **Planning (BO3)**: in a normal week the CP-SAT plan costs **€7,050** vs **€11,760** for a
  schedule sized for the busiest hour (−40%), and still answers 92% of chats within 20 s
  (target 80%).
- **Testing first (BO4)**, per peak week, prepared vs unprepared plan:

| Scenario | Understaffed hours | Abandonment | Extra labour | Net saving (labour + lost customers) | Break-even cost of a lost customer |
|---|---|---|---|---|---|
| Promo spike | 41.5 → 12.1 | 11.7% → 4.5% | +€2,712 | **+€226** [€129; €323] | €7.4 |
| Delivery delays | 59.8 → 9.6 | 15.5% → 3.8% | +€4,074 | **+€1,196** [€935; €1,458] | €6.2 |
| Staff shortage (20% absent) | 31.8 → 12.7 | 9.8% → 4.4% | +€2,030 | −€692 [−€987; −€397] | €12.1 |

Reading: preparing always protects service; it also pays for itself as soon as an abandoned
customer is worth more than **€6–12** (a repeat contact plus churn risk usually exceeds
this for an e-commerce order). The break-even, not the euro figure, is the robust result.

## A7. Go-to-market and roadmap

1. **MVP (this project)**: twin, four agents, front office + back office, evaluation — runs on a laptop.
2. **Pilot** (8 weeks, 1–2 clients): connect real logs (tickets, chat timestamps, schedules);
   calibrate patience, handle times and contact rates; validate fidelity; human-label 100 chats.
3. **Product**: connectors (Zendesk, Freshdesk, Gorgias), multi-skill queues and channels
   (voice, e-mail), role-based access, audit logs, hosted or on-premise deployment.
4. **Scale**: RL routing integrated in the help-desk's assignment API behind an A/B test.

Adoption KPIs: forecast error on the client's data, schedules accepted by planners,
understaffed hours in peaks, judge–human agreement.

## A8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Twin not faithful to a real center | fidelity checks are built in (KS tests, Erlang C); calibration on real logs before any decision |
| AI advisor invents answers | rules engine decides the action, LLM writes it; judge + human calibration; template fallback |
| Regulation (GDPR, EU AI Act transparency for chatbots) | local models, data stays on premise; customers told they talk to an AI; humans keep final responsibility for staffing |
| Acceptance by planners | explainable planners (CP-SAT, Erlang C), schedules editable, results with confidence intervals |
| Incumbent suites add simulation | focus on mid-market, open integrations, speed of deployment |

## A9. SWOT

| Strengths | Weaknesses |
|---|---|
| end-to-end (forecast → plan → route → answer → grade); reproducible; local LLMs; honest evaluation | no real logs yet; synthetic contact rates; small LLMs on laptop hardware |
| **Opportunities** | **Threats** |
| AI agents in customer service need evaluation and testing; mid-market under-served by large suites | large CCaaS vendors; data-access barriers; LLM regulation |

---

# Part B — Technical validation

## B1. Business → data science framework

Every objective follows the chain *business objective → business KPIs → data science
objective → DSO metrics*. A KPI says whether the center is doing better; a DSO metric says
whether the AI component works. Both are needed.

| BO | Business KPIs | DSO | DSO metrics | Baseline | Backup |
|---|---|---|---|---|---|
| BO1 make customers wait less | average wait, abandonment, % answered < 20 s | DSO1 AI manager assigns customers to advisors in real time | wait in simulation vs FIFO | FIFO + skill matching | priority score with optimized weights |
| BO2 solve problems correctly, raise satisfaction | FCR, CSAT, % answers following rules | DSO2 AI advisor with company knowledge + AI reviewer | % correct answers, % tool calls that work, judge–human agreement | keyword FAQ search | intent classifier + approved templates + checklist |
| BO3 cut cost without hurting service | cost per contact, staffing and overtime cost, productivity | DSO3 AI manager plans shifts and overtime | cost per contact and overtime vs fixed schedule at the service target | fixed schedule | Erlang C + shift templates + overtime rule |
| BO4 prepare for peaks by testing first | understaffed moments in peaks, money saved by testing, time to decide | DSO4 forecast + virtual copy of the center | forecast error vs naive; twin vs logs (waits, volumes, handle times) | same day last week; queueing formula | statistical forecast + waiting-line model |

Three rules applied everywhere: (1) every idea is compared with a simple baseline;
(2) every DSO has a backup that covers the whole objective with less effort; (3) thresholds
(e.g. ≥10% less waiting) are starting targets. DSO4 is the foundation: DSO1 and DSO3 are
trained and tested inside its simulation.

## B2. Method and project phases (CRISP-DM)

| Phase | CRISP-DM step | Deliverables |
|---|---|---|
| 0 | Business understanding | BO/DSO framework, ideas A/B/backup per DSO |
| 1A–1B | Data understanding | dataset evaluation, exploration, quality validation (notebooks 01–02) |
| 1C–1D | Data preparation | cleaning with flags, analytical order table (notebooks 03–04) |
| 1E | Data generation | intent catalog, contact rates, promotion calendar, synthetic contacts (05–08) |
| 1F | Data store | tickets, chat logs, SQLite store (12) |
| 2 | Modelling — forecast | rolling backtest of 5 models (09, `forecasting/`) |
| 3 | Modelling — twin | SimPy engine, Erlang C validation (10, `simulation/`) |
| 4 | Modelling — agents | knowledge base (11), advisor, client, quality, workforce (`agents/`), LangGraph |
| 5 | Evaluation | KPI engine, experiments with seeds and CIs, scorecard (`evaluation/`) |
| 6 | Deployment | FastAPI, React front office + back office, Hugging Face LLMs, MLflow, Docker Compose, CI |

## B3. Data

**Sources.**
- *Olist Brazilian e-commerce* (Kaggle, CC BY-NC-SA 4.0): 99,441 orders (2016–2018) with
  items, payments, reviews, customers, sellers, products, and every delivery timestamp.
- *Bitext retail e-commerce chatbot dataset* (CDLA-Sharing): customer messages labelled
  with 46 intents; the **17 order-linked intents** are kept, grouped into four families:
  *where is my order* (wismo), *cancel/refund*, *after delivery* (post_delivery), *order admin*.

**Preparation (notebooks 03–04).** Types parsed, anomalies flagged rather than deleted
(chronology violations, status inconsistencies, repeated review ids), no imputation,
record counts preserved; an analytical table of 77 features per order (delivery delay,
lateness, payment anomalies, review score...) and a daily activity table.

**Synthetic contacts (notebooks 05–08).** Each order is placed in a *situation*
(never delivered and overdue, delivered late, canceled, post-delivery problem, payment
anomaly...). Each situation has a contact probability and an intent mix
(`configs/data.yaml`, e.g. 35% of late deliveries contact support), a timing rule
relative to an order event, and the hour-of-day profile of Olist purchases. The wording is
a real Bitext message of the chosen intent. Result: **9,179 contacts** (2017-01 → 2018-08),
cross-checked against a public benchmark (where-is-my-order contacts at 3–10% of orders).

**Tickets and chats (notebook 12).** One ticket per contact with a rule-based outcome
(the company policy: e.g. late parcel > 7 days → carrier investigation), handle time drawn
from the simulation's assumption, CSAT survey (30% response) — **9,179 tickets and 60,837
chat messages** in a SQLite store with primary and foreign keys.

**Knowledge base.** 10 hand-written policy documents (refunds, returns, delays, payments,
invoices, advisor playbook...) → **58 sections**, embedded with **bge-m3** (multilingual,
1024 dimensions) in an exact FAISS index.

**Data contracts.** Pandera schemas check keys, types, allowed values and ranges of the six
tables every later layer depends on (`callverse validate`); all pass.

## B4. Architecture

```
┌────────────┐   ┌──────────────────────┐   ┌──────────────────────────────────┐   ┌─────────────┐   ┌──────────────────┐
│ DATA LAYER │──▶│ FORECAST & SIMULATION│──▶│ DIGITAL TWIN (LangGraph)          │──▶│ EVALUATION  │──▶│ SERVING & MLOPS  │
│ Olist      │   │ LightGBM per intent  │   │ Client agent  (small LLM)         │   │ KPI engine  │   │ FastAPI + WS     │
│ Bitext     │   │ SimPy event sim.     │   │ Workforce agent (PPO + CP-SAT)    │   │ scenarios × │   │ front + back     │
│ SQLite     │   │ Erlang C, fidelity   │   │ Advisor agent (RAG + tools)       │   │ seeds, CIs  │   │ office, MLflow,  │
│ FAISS KB   │   │                      │   │ Quality agent (LLM judge)         │   │ comp. metrics│  │ tracing, Docker  │
└────────────┘   └──────────────────────┘   └──────────────────────────────────┘   └─────────────┘   └──────────────────┘
```

Where each part runs: PPO trains on the fast SimPy + Gymnasium environment (sampled
intents, no LLM calls); the LLM agents then validate behaviour on a smaller set of
conversations. Model versions are pinned (Hugging Face commit of each repository, written by
`callverse llm-pull`) and seeds are fixed.

**Layering is enforced**: `import-linter` contracts forbid a lower layer from importing a
higher one (data ↛ simulation ↛ agents ↛ twin ↛ orchestration/evaluation ↛ api); all 5 hold.

### Technology stack and why

| Layer | Tool | Why this tool |
|---|---|---|
| Data | pandas, PyArrow/Parquet | columnar, typed, fast; standard |
| Data | SQLite | the advisor's tools need a real relational store; zero setup |
| Data | Pandera | declarative data contracts, readable by non-developers |
| Data | nbclient | re-runs the documented notebooks headless (single source of truth) |
| Forecast | LightGBM (Poisson) | best accuracy on small tabular panels; feature importance; fast |
| Forecast | statsmodels SARIMA, Prophet | strong classical baselines/backups |
| Simulation | SimPy | discrete-event simulation in Python; steppable for RL |
| Simulation | Erlang C (own code) | queueing formula: staffing need and engine validation |
| RL | Gymnasium, Stable-Baselines3, sb3-contrib MaskablePPO | standard API; action masking for variable queues |
| Optimization | Google OR-Tools CP-SAT | exact integer optimization with hard labour rules |
| NLP / RAG | sentence-transformers bge-m3, FAISS | multilingual (FR/EN) embeddings, exact cosine search |
| NLP | scikit-learn TF-IDF + logistic regression | intent classifier (backup) and keyword baseline |
| LLM | Hugging Face `transformers` + `bitsandbytes` 4-bit: SmolLM3-3B (advisor, client), IBM Granite-4.0-1B (judge) | open weights, local, free, private; tool calling; judge from another family and organisation; both fit a 4 GB GPU |
| Orchestration | LangGraph | explicit state machine of agents; streaming of each step |
| API | FastAPI, Pydantic, uvicorn, WebSocket | typed, documented (OpenAPI), async streaming |
| UI | React 18, TypeScript, Vite, Tailwind, Framer Motion, Recharts, cmdk, npm workspaces | two apps (front office, back office) on one design system; typed; animated; replaces Streamlit |
| MLOps | MLflow (SQLite / Postgres) | runs, params, metrics, artifacts per experiment |
| MLOps | JSONL tracing (+ Langfuse option), SQLite LLM cache | cost/latency per agent call; reproducible replays |
| Delivery | Docker Compose, GitHub Actions, pytest, ruff, import-linter | one-command deploy; tested, linted, layered builds |

## B5. DSO4 part 1 — contact volume forecast

**Target.** Daily contacts per intent group (4 series) and their total, 1 to 7 days ahead.

**Features (leakage-safe: every lag ≥ 7 days).** Own history (lags 7/14/21/28, same-weekday
mean, 7- and 28-day means), order drivers (orders purchased, handed to carrier, delivered,
late deliveries — 7-day means lagged 7 days; orders promised for the day; overdue backlog),
calendar (weekday, public holidays, promotion windows, days to next event, days since the
last major sale). A unit test checks that `lag_7` equals the value 7 days before.

**Models.** Seasonal naive "same day last week" (DSO baseline), 4-week weekday mean,
SARIMA(1,1,1)(0,1,1,7), Prophet with holidays and promotions, and one **global LightGBM**
(Poisson objective, group as a categorical feature).

**Protocol.** Rolling-origin backtest: 46 weekly origins (Sundays, Oct 2017 → Aug 2018),
each model trained only on data up to the origin, forecasting the next 7 days.

**Results (wMAPE %, lower is better).**

| Level | LightGBM (main) | Same day last week (baseline) | 4-week weekday mean | SARIMA (backup) | Prophet (backup) |
|---|---|---|---|---|---|
| **Total** | **25.3** | 31.6 | 31.9 | 27.7 | 35.9 |
| Where is my order | **36.9** | 45.5 | 48.8 | 42.3 | 52.1 |
| After delivery | 38.0 | 45.1 | 41.9 | **35.2** | 43.7 |
| Order admin | 54.7 | 68.0 | 55.9 | 53.7 | **52.7** |
| Cancel / refund | 83.8 | 102.9 | 86.1 | **81.3** | 90.5 |

LightGBM reduces the error by **19.9%** vs the naive baseline at the total level (RMSE 7.0
contacts/day), and is also better than SARIMA (27.7) and Prophet (35.9) on the total and
on the largest group. SARIMA is slightly better on two small groups and Prophet on one,
which is why an ensemble per group is a natural next step.
Small groups have 1–3 contacts a day: their error is dominated by Poisson noise, so staffing
is decided at the total level. The most important features are the recent levels
(28- and 7-day means), the same-weekday mean, the days since the last major sale and the
orders promised for the coming days — i.e. the model uses the *order drivers* the DSO
document asked for. **Decision: main idea kept.**

## B6. DSO4 part 2 — the digital twin

**Engine** (`simulation/engine.py`, SimPy). Customers arrive as a non-homogeneous Poisson
process (daily volume × hourly profile × scale ×25), each with an intent group, a handle time
(lognormal; means 3/4/6/7 min by group, CV 0.6) and a persona (impatient 25% / normal 55% /
patient 20%, mean patience 90/180/360 s). Advisors have skills (×0.75 handle time on a
primary group, ×1.3 on a weak one). A duty matrix says who works which hour (regular or
overtime); a router decides who takes whom. Chats arriving while closed (22:00–08:00) are a
backlog served in the morning. Costs: €12/hour, overtime ×1.5, €8 per abandoned customer.

**Two modes.** `run()` for evaluation; step-by-step (`advance()` / `resolve()`) for RL: the
engine pauses at every routing decision. With uniform skills and FIFO, version 2 reproduces
the version-1 engine *exactly* (identical start time for every contact — unit-tested).

**Scenarios** (`configs/scenarios.yaml`): a real week of history changed by multipliers —
promo spike (all groups ×1.4–1.8), delivery delays (wismo ×2.5, handle time +10%),
staff shortage (20% absent), and the historical Black Friday week.

**Fidelity (DSO4 metric).**

| Check | Result | Rule |
|---|---|---|
| Erlang C: probability of waiting | 0.279 simulated vs 0.285 theory | < 5% error ✓ |
| Erlang C: mean wait | 33.3 s vs 34.2 s | ✓ |
| Erlang C: answered < 20 s | 76.5% vs 75.9% | ✓ |
| Daily volume vs history (4 weeks) | KS p = 0.998 (491 vs 488 contacts/day) | p > 0.05 ✓ |
| Hour-of-day profile | total variation distance 0.015 | < 0.05 ✓ |
| Handle time vs ticket logs | KS p = 0.35 (273 s vs 272 s) | p > 0.05 ✓ |

The first group proves the engine is correct; the second proves the twin is consistent
with its inputs. With real logs the same code becomes a real calibration.

**BO4 — testing first** (CP-SAT plan from the normal forecast = *unprepared*, vs from the
scenario-adjusted forecast = *prepared*; same customers, 10 seeds; all differences
significant at 95%):

| Scenario | Service level < 20 s | Abandonment | Understaffed hours / week |
|---|---|---|---|
| Promo spike | 76.1% → **91.9%** | 11.7% → **4.5%** (−62%) | 41.5 → **12.1** (−71%) |
| Delivery delays | 67.8% → **93.7%** | 15.5% → **3.8%** (−76%) | 59.8 → **9.6** (−84%) |
| Staff shortage | 81.6% → **92.6%** | 9.8% → **4.4%** (−55%) | 31.8 → **12.7** (−60%) |

The average wait of live customers falls by 60–78% (e.g. 43.4 s → 9.6 s under delivery delays).
Time to decide: **2–7 s** for 10 replications of a week. Cost trade-off: see A6.
**Decision: main idea kept** (forecast beats naive, twin passes every fidelity check).

## B7. DSO3 — shift and overtime planning

**Requirement.** From the forecast, Erlang C gives the advisors needed each hour to answer
80% of chats within 20 s with occupancy ≤ 90% (overnight backlog spread over 08:00–10:00).

**CP-SAT model (two stages).**
*Stage 1 — cheapest coverage.* Integer variables: x[d,t] advisors on shift template t
(4, 6 or 8 hours, any start inside 08:00–22:00; 27 templates) on day d; o[d,h] overtime
advisors (≤ 4 per hour, ≤ 60 h per week); s[d,h] shortfall.
Constraint: Σ covering x + o + s ≥ requirement for each open hour.
Objective: minimise €12 × hours + €18 × overtime + €200 × shortfall.
*Stage 2 — legal roster.* Booleans y[a,d,t] assign the chosen shifts to named advisors:
one shift per day, ≤ 5 days and ≤ 40 hours per week, ≥ 11 hours rest between days;
headcount grows until feasible. Solved to optimality in < 1 s.

**Results (normal week, prepared plans, FIFO routing, 10 seeds).**

| Planner | Labour cost | Cost per contact | Service level | Overtime h | Labour rules |
|---|---|---|---|---|---|
| Fixed, sized for the peak (**baseline**) | €11,760 | €3.20 | 97.7% | 0 | n/a |
| Erlang C + 2 templates + overtime rule (backup) | €9,792 (−17%) | €2.68 | 95.8% | 0 | by construction |
| **CP-SAT (main)** | **€7,050 (−40%)** | **€1.95** | **92.4%** | 45 | **all ✓** |
| Fixed, tuned to the 75th percentile (sensitivity) | €7,056 | €1.96 | 93.1% | 0 | n/a |

In the promo week: CP-SAT €9,762 vs €16,464 for the peak-sized fixed schedule (−41%), at
91.9% service. **Decision: main idea kept** (≥ 5% cheaper while meeting the target).

*Critical note.* A fixed schedule *tuned* by hand to the right level costs about the same
in a normal week, because the Olist hourly profile is flat from 10:00 to 22:00. CP-SAT's
value is that it finds that level automatically for every week and scenario, guarantees
every hour of the requirement and the labour rules, and adapts when demand has peaks.

## B8. DSO1 — real-time routing

**MDP.** *Decision*: an advisor becomes free and ≥ 2 customers wait. *State*: the 10 oldest
waiting customers (wait so far, intent group, persona, live chat or overnight message,
expected handle time and speed of *this* advisor on it) + queue length, backlog, free and
on-duty advisors, time of day. *Action*: which slot to serve (invalid slots masked →
MaskablePPO). *Reward*: − customer-seconds of waiting since the last decision (overnight
messages weighted 0.1) − 600 s per abandonment. Minimising total waiting time minimises
the average wait (Little's law).

**Training.** Episodes are single days of the training period (Feb 2017 – Mar 2018) made
busier than planned (load ×1.0–1.8, each intent group surging ×1.0–1.6, 5–30% absences):
2,394 episodes, 300k decisions, MLP 128×128, 12 minutes on CPU. A first version trained
with a uniform load increase (v1) was improved by adding per-intent surges (v2), which
raised its abandonment gain on stressed days from −1.9% to −4.6%; v2 is kept.

**Backup.** Priority score = w₁·wait + w₂·skill match + w₃·short job + w₄·impatient, with
weights found by random search in the twin (best: skill match 2.4, short job 2.2,
impatient 2.4, wait 0.15).

**Results.**

*Unseen stressed days* (test period Apr–Aug 2018, load ×1.6, 15% absent, 40 paired runs):

| Router | ASA | Service level < 20 s | Abandonment |
|---|---|---|---|
| FIFO + skill matching (baseline) | 25.2 s | 59.7% | 19.7% |
| Skill score (backup) | 22.9 s (−9.2%) | 62.8% | 18.2% (−7.8%) |
| MaskablePPO v2 (main) | 21.7 s (**−13.9%**, CI −4.7 to −2.3 s) | 63.0% | 18.8% (−4.6%) |

*Full peak weeks of the twin* (3 scenarios × 10 seeds, unprepared CP-SAT plan):

| Router vs FIFO | Mean wait (all live customers) | Abandonment | 90th-percentile wait | Service level |
|---|---|---|---|---|
| Skill score (backup) | not significant (−6% to +1%) | **−8% to −11%** | −14% to −15% | +1.4 to +4.1 pts |
| MaskablePPO v2 (main) | not significant (−1% to +7%) | −4% to −5% | **−18% to −25%** | +1.1 to +4.2 pts |

All abandonment and service-level differences are significant at 95%. PPO trades a little
average wait for much shorter long waits: it serves customers who have waited long or are
about to leave, which is a fairness gain the mean hides.

**Decision (switch rule).** PPO beats FIFO by > 10% on stressed days but not robustly in
full peak weeks (different conditions: multi-day backlog, planned overtime). Per the DSO
document the **tuned skill-score backup is the production candidate** (robust, explainable),
PPO stays the research track. Next step: multi-day training episodes that match the scenarios.

## B9. DSO2 — AI advisor and AI reviewer

**Client agent** (twin input): plays the customer of a real contact — opening message from
history, persona, knowledge of its order — with a small LLM (SmolLM3-3B, JSON output), or a
rule-based customer offline. It ends with a 1–5 satisfaction survey.

**Advisor agent** (Ask → Retrieve → LLM → Reply). Retrieval: bge-m3 + FAISS top-3 policy
sections (with a "no-answer" threshold calibrated at 0.57). Tools on the SQLite store, all
"as of" the moment the customer writes: `lookup_order`, `get_ticket_history`,
`check_refund_eligibility`, `open_ticket`, `search_knowledge_base`, and — in the hybrid
variant — `recommend_resolution` (the company rules engine). Variants evaluated:
- *template* (backup): intent classifier (TF-IDF + logistic regression, **99.0% accuracy,
  macro-F1 0.991** on held-out Bitext) + approved answers filled with order facts;
- *rag* (pure idea A): LLM with retrieval and tools; the LLM decides which tools to call;
- *rag_policy* (hybrid): once the order number is known, the pipeline itself calls
  `lookup_order` and the rules engine `recommend_resolution` (deterministic steps); the LLM
  receives the decision and only writes the reply in natural language.

**Guardrails added after the first LLM run.** The first batch exposed two failure modes of
3B models, both visible thanks to tool tracing:
1. the advisor called `lookup_order` on the first turn with *invented* order ids
   ("order_number", "customer_order_id"): 9 of 20 tool calls failed. → **Tool gating**: order
   tools are offered only once an order number appears in the conversation;
2. the client model sometimes swapped roles and asked the advisor for *its* order number.
   → The simulated customer answers verification questions deterministically; the LLM
   handles free reactions only;
3. in one hybrid conversation the advisor answered generic policy without ever asking for
   the order number. → **Verification guardrail** (playbook rule 1, hybrid only): a reply
   given before verification always ends with the order-number request.

**Quality agent**: a scorecard of 5 criteria (compliance, relevance, satisfaction,
sentiment, resolution, 1–5) filled by an LLM judge from a **different family** than the
advisor (IBM Granite vs Hugging Face SmolLM3), given the policy-correct reference; checklist
reviewer offline.

**Correctness** is measured two ways: deterministic (the advisor's chosen action equals the
policy reference computed by the rules on the true intent) and by the judge.

**Retrieval (255 Bitext questions, 17 intents).**

| Retriever | Recall@1 | Recall@4 | MRR |
|---|---|---|---|
| Keyword search TF-IDF (**DSO2 baseline**) | 52.9% | 80.4% | 0.641 |
| **bge-m3 + FAISS** | **80.0%** | **96.9%** | **0.868** |

**Conversations (BO2 KPIs).** See the table produced by `callverse agents`
(`artifacts/evaluations/dso2_agents_summary.csv`):

All three variants answer the **same 12 sampled customers** (paired comparison), with the
"fast" LLM profile (qwen2.5:3b advisor and client, llama3.2 judge):

| Advisor variant | Verified policy-correct action | Similarity to the policy answer (bge-m3 cosine) | Faithfulness to evidence | Customer CSAT (1–5) | Tool calls that worked |
|---|---|---|---|---|---|
| Template (backup) | 100% | 1.00 (it *is* the approved answer) | 0.64 | 3.67 | 100% |
| **RAG + rules engine (hybrid)** | **100%** (12/12; 11/12 before the verification guardrail) | 0.74 | 0.80 | **4.33** | 100% |
| Pure agentic RAG (idea A) | not verifiable (no structured action; the untrusted judge says 0/12) | 0.74 | **0.99** | 3.58 | 100% (48% before tool gating) |

Reading: the pure-RAG answers are well grounded (faithfulness 0.99: almost every sentence is
supported by a tool result or a policy section) and semantically as close to the approved
answer as the hybrid's, but nothing in them can be *verified* as the policy action. The hybrid
gives a checkable action, keeps the best customer satisfaction and is the configuration
we would put in front of customers. Faithfulness is low for templates only because the
embedding metric compares formatted dates and phrases with raw JSON fields — a known limit
of the cheap, local alternative to an LLM-graded RAGAS.

**Judge calibration.** Agreement with labels (60 historical chats; quadratic Cohen's kappa,
"trusted" at ≥ 0.4):

| Judge | Labels | Satisfaction kappa | Resolution kappa | Within ±1 point |
|---|---|---|---|---|
| LLM judge (llama3.2 3B) | proxy (generator answer key) | 0.06 | 0.06 | 58–65% |
| Checklist reviewer (backup) | proxy (generator answer key) | 0.07 | **0.39** | 63–65% |

Neither judge is trusted yet. Two reasons, both documented: (1) a 3B judge is too weak —
in the transcripts it marked policy-correct answers as "invented promises"; (2) proxy
satisfaction labels are random draws given the outcome, so no judge can predict them well.
The labeling page (Quality & labeling) collects real human grades; with ≥ 20 labels the
calibration switches to them automatically. Until then the deterministic action check and
the checklist are the production quality signals, and the LLM judge is advisory only.

**Decision.** Retrieval clearly beats the keyword baseline (recall@4 96.9% vs 80.4%). For
answering, the pure-RAG advisor cannot be shown to meet the "≤ 10% wrong answers" rule with a
3B model, so the production configuration is the hybrid (12/12 verified policy actions,
best CSAT) with the template advisor as the offline backup. On the same 12 chats the 3B LLM
judge called only 2 of these answers "correct": the deterministic check, not the judge, is
the reliable signal today. The AI reviewer stays "not trusted" until its
kappa against human labels reaches 0.4 — the main open item of DSO2.

## B10. Orchestration (LangGraph)

```
START → client_open → workforce_route → advisor ⇄ client_reply → quality → kpi → END
```

The state (messages, routing decision, advisor memory, reference, scorecard, KPIs) is a
typed dictionary; every node's update is streamed to the UI through a WebSocket, so the
tutor sees each agent act. A conversation takes ~0.2 s offline and ~1–2 min with local LLMs
on a 4 GB laptop GPU ("fast" profile; "full" profile = 7B advisor).

## B11. Evaluation framework

- **KPI engine** (`evaluation/business_kpis.py`): mean wait of all live customers, ASA,
  abandonment, service level, p90 wait, AHT, occupancy, labour/overtime cost, cost per
  contact, labour + lost-customer cost, understaffed hours; BO2 KPIs from conversations
  (FCR, CSAT, compliance, correct answers, tool success).
- **Experiments** with **common random numbers** (every option sees the same customers) and
  **paired differences with 95% t-intervals**; a difference is claimed only when the interval
  excludes zero.
- **Component metrics**: forecast (wMAPE, RMSE), RAG (recall, MRR, faithfulness, relevance),
  judge (quadratic kappa, Spearman), twin (KS, Erlang C error).
- **Scorecard**: applies each DSO's switch rule (`artifacts/evaluations/scorecard.json`).

## B12. Serving and MLOps

| Component | Implementation |
|---|---|
| API | FastAPI: back office — `/api/overview`, `/api/data/summary`, `/api/forecast`, `/api/twin/config`, `POST /api/twin/run`, `POST /api/twin/compare`, `/api/twin/floor` (one day, contact by contact), `/api/workforce/*`, `/api/agents/*`, `/api/quality/*` (labeling, calibration), `/api/evaluation`, `/api/mlops`, `/api/system` (+ `POST /api/system/warmup`); front office — `/api/portal/customers[/id]`, `/api/kb/articles[/id]`, `/api/kb/search`, `/api/desk/queue`, `WS /ws/session` (live chat: tokens, tool calls, stages, review); OpenAPI docs at `/docs` |
| Front office | React app for customers and advisors: home with semantic help search, help centre (the advisor's knowledge base), demo customers with the order journey, live chat with the AI advisor (token streaming + "behind the scenes" trace + CSAT + quality review), advisor desk (live queue, copilot drafts, autopilot, customer 360, quality tab) |
| Back office | React app for managers: overview (BO→DSO rings, animated architecture), data, forecast, digital twin (animated canvas **live floor** replaying a simulated day + scenario lab), agent theater (the four agents streaming live), workforce, quality & labeling, scorecard, models & MLOps (Hugging Face model cards, GPU gauge, tracing); command palette (Ctrl+K), light/dark themes, colour-blind-safe palette |
| Tracking | MLflow experiments: forecast, routing PPO, evaluation suites (params, metrics, artifacts) |
| LLM ops | Hugging Face models pinned to a commit (`callverse llm-pull` / `llm-pin`), local-cache-only loading, 4-bit NF4 + bf16 compute, disk cache, JSONL tracing per agent (tokens, latency, tokens/s, tools), optional Langfuse |
| Reproducibility | seeds in configs, `callverse all`, executed notebooks archived |
| Deployment | Docker Compose: api, web (nginx: front office :8080, back office :8081), mlflow + postgres; GPU override `docker-compose.gpu.yml` (CUDA torch + NVIDIA device) |
| Quality | 95+ automated tests (unit, smoke, integration incl. the live WebSocket session), ruff, 5 import contracts, GitHub Actions (Python + type-check and build of both apps) |

## B13. Project structure — folder by folder, file by file

**Root**

| File | Role |
|---|---|
| `README.md` | front page: results, quick start, structure |
| `pyproject.toml` | package, dependency extras (forecast, agents, mlops, dev), ruff, pytest, import contracts |
| `Makefile` | shortcuts (install, install-gpu, llm-pull, test, all, serve, front, back, docker, docker-gpu) |
| `Dockerfile`, `docker-compose.yml`, `docker-compose.gpu.yml`, `.dockerignore` | API image (CPU or CUDA torch) and the multi-service deployment |
| `.env.example` | environment settings (LLM profile and device, retriever, MLflow, Langfuse) |
| `.github/workflows/tests.yml` | CI: lint, contracts, tests, type-check and build of both apps |

**`configs/`** — every assumption, in one place

| File | Content |
|---|---|
| `data.yaml` | contact-rate assumptions per order situation, intent groups, promo calendar, ticket rules, pipeline notebooks, store path |
| `simulation.yaml` | opening hours, staffing target (80/20), patience, handle times, skills, costs, fidelity settings |
| `agents.yaml` | LLM profiles (Hugging Face repositories per role), model catalog (family, licence, chat-template options), personas, advisor (variant, KB, classifier), quality rubric, workforce (PPO, skill score, CP-SAT rules) |
| `scenarios.yaml` | what-if scenarios (week, multipliers, absences) |
| `app.yaml` | API, CORS, MLflow experiments |

**`notebooks/`** — documented data work: `01` exploration, `02` quality validation, `03`
cleaning, `04` analytical dataset, `05` intent dataset evaluation, `06` contact rates,
`07` promotion calendar, `08` synthetic contacts, `09` forecasting study, `10` simulation
study, `11` knowledge-base retrieval study, `12` tickets and chats.

**`scripts/`** — `build_database.py` (tickets, chats, SQLite store), `build_knowledge_base.py`
(bge-m3 + FAISS index).

**`src/callverse/`**

| Path | Role |
|---|---|
| `config.py` | project paths, `.env` loading, YAML access |
| `tracking.py` | MLflow runs (SQLite or server), recent runs for the UI |
| `main.py` | the `callverse` CLI (data, validate, forecast, train-rl, schedule, simulate, fidelity, chat, agents, judge-calibrate, llm-pull, llm-pin, evaluate, status, serve, all) |
| `llm/client.py` | chat client: role → pinned Hugging Face model, fallbacks, availability (GPU, weights), cache, tracing, streaming, JSON repair |
| `llm/hf_local.py` | local `transformers` models: 4-bit loading, model pool, chat templates, tool-call parsing, token streaming (tool markup hidden), early stop on complete JSON |
| `llm/cache.py` | SQLite cache of LLM answers (reproducible replays) |
| `llm/tracing.py` | JSONL tracing of every call (+ Langfuse) |
| `data/pipeline.py` | headless execution of notebooks 03–08 |
| `data/validation.py` | Pandera contracts |
| `data/loaders.py` | cached readers of processed tables |
| `data/database.py` | SQLite schema with keys, safe build, read-only connection |
| `data/tickets.py` | ticket generator and the company outcome rules |
| `data/conversations.py` | approved answer templates and chat generator |
| `forecasting/features.py` | leakage-safe features and panel |
| `forecasting/baselines.py` | seasonal naive, weekday mean, SARIMA, Prophet |
| `forecasting/demand_model.py` | global LightGBM (Poisson) |
| `forecasting/backtest.py` | rolling-origin backtest, wMAPE/MAE/RMSE/bias, integrity checks |
| `forecasting/predict.py` | weekly out-of-sample forecasts, next-week forecast |
| `forecasting/train.py` | forecast stage with artifacts and MLflow |
| `simulation/customers.py` | contacts, Poisson arrivals, personas, patience |
| `simulation/service.py` | lognormal handle times |
| `simulation/resources.py` | Erlang C formulas, staffing need, hourly plan inputs |
| `simulation/engine.py` | the twin engine (skills, routing, duty, overtime, costs, KPIs) |
| `simulation/policy.py` | agents, router protocol, FIFO and skill-score routers |
| `simulation/environment.py` | version-1 engine (kept as the reference) |
| `simulation/metrics.py` | version-1 KPIs and replication summaries |
| `simulation/scenarios.py` | simulation configuration loader |
| `simulation/setup.py` | twin settings and builders (contacts, plans, pools, absences) |
| `agents/client/profiles.py`, `simulator.py` | customer profiles; Client agent (LLM / rules) |
| `agents/advisor/indexing.py`, `retrieval.py` | KB chunking and embedding; FAISS and keyword retrievers |
| `agents/advisor/intent_classifier.py` | TF-IDF + logistic-regression intent classifier |
| `agents/advisor/tools.py` | SQLite business tools and their JSON schemas |
| `agents/advisor/prompts.py`, `advisor.py` | prompts; Advisor agent (LLM loop / templates) |
| `agents/quality/rubric.py`, `reviewer.py`, `validation.py` | scorecard; LLM judge and checklist; kappa / Spearman, human labels |
| `agents/workforce/routing.py` | observation builder, PPO router, router factory |
| `agents/workforce/gym_wrapper.py` | Gymnasium environment on the twin |
| `agents/workforce/train.py` | MaskablePPO training and router comparison |
| `agents/workforce/optimization.py` | random search of skill-score weights |
| `agents/workforce/scheduling.py` | CP-SAT, rule-based and fixed planners, labour-rule checks |
| `agents/workforce/manager.py` | Workforce agent facade (plan_week, router) |
| `orchestration/state.py`, `runtime.py`, `graph.py` | LangGraph state, shared resources, conversation graph and batches |
| `orchestration/live.py` | live sessions for the front office: a human plays the customer or the advisor, the same agents play the other side (copilot, autopilot) |
| `twin/state.py`, `digital_twin.py`, `calibration.py` | scenarios; scenario runner and live-floor replay; fidelity checks |
| `evaluation/business_kpis.py` | KPI engine, CIs, paired differences |
| `evaluation/experiments.py` | DSO1–DSO4 experiments, RAG and judge evaluations |
| `evaluation/forecast_metrics.py`, `advisor_metrics.py`, `twin_metrics.py`, `workforce_metrics.py` | component metrics |
| `evaluation/report.py` | component-metrics table and BO/DSO scorecard |
| `api/app.py`, `schemas.py`, `services.py` | FastAPI routes and WebSocket; request models; caching and JSON helpers |

**`frontend/`** — npm workspaces, one design system, two apps:

| Path | Role |
|---|---|
| `package.json`, `package-lock.json` | workspace root (`dev:front`, `dev:back`, `build`, `typecheck`) |
| `Dockerfile`, `nginx.conf` | builds both apps; one nginx serves :8080 (front) and :8081 (back), proxying `/api` and `/ws` |
| `shared/tailwind.preset.js` | shared Tailwind theme (colour tokens, fonts, shadows, keyframes) |
| `shared/src/styles/` | `tokens.css` (light/dark tokens, validated chart palette), `index.css` (cards, buttons, glass, gradients, tables, prose, animations, reduced motion) |
| `shared/src/lib/` | `api.ts` (fetch hooks), `session.ts` (live-session WebSocket client and event reducer), `theme.ts`, `format.ts` |
| `shared/src/components/` | `ui.tsx` (cards, stats, badges, segmented control, avatar, skeletons), `motion.tsx` (page transitions, stagger, count-up, rings, typewriter), `brand.tsx` (logo, aurora background, theme toggle), `chat.tsx` (bubbles, streaming bubble), `AgentPipeline.tsx` (animated LangGraph flow), `LiveTrace.tsx` (behind-the-scenes trace), `QualityScore.tsx` (radar scorecard), `CommandPalette.tsx` (Ctrl+K), `Markdown.tsx`, `ErrorBoundary.tsx` |
| `front-office/src/` | `App.tsx` (routes), `layout/Shell.tsx` (navbar, footer), `customer.tsx` (demo customer), `components/` (help search, order timeline, hero chat demo, CSAT dialog, customer card), `pages/` (Home, Help, Account, Chat, Desk) |
| `back-office/src/` | `App.tsx`, `components/Layout.tsx` (collapsible sidebar by layer, GPU status), `components/LiveFloor.tsx` (canvas replay of the twin), `components/ArchitectureMap.tsx` (animated SVG), `components/Heatmap.tsx`, `pages/` (Overview, Data, Forecast, Twin, Agents, Workforce, Quality, Evaluation, Mlops) |

**`tests/`** — `unit/` (simulation, engine, workforce, forecasting, KPI engine, tickets,
database, knowledge base, Hugging Face LLM layer), `smoke/` (imports, CLI), `integration/`
(conversation, live sessions, front-office endpoints, live-floor replay, WebSocket session, twin,
API on real data; LLM test marked `llm`).

**`data/`** (git-ignored) — `raw/` Olist and Bitext; `processed/` Parquet tables;
`callverse.db`; `knowledge_base/docs` (tracked) and `index/`; `labels/` human grades.
**`artifacts/`** (git-ignored) — `forecasts/`, `policies/` (PPO, classifier, weights),
`evaluations/` (every table of this report), `traces/` (LLM calls, cache, conversations, live
sessions, `llm_models.lock.json`),
`notebook_runs/`.

## B14. Steps to realize the project (reproducible path)

1. **Frame**: BO → KPI → DSO → metric chain; ideas A/B + backup per DSO; switch rules.
2. **Collect data**: Olist and Bitext; evaluate fitness (phase 1A).
3. **Explore and validate quality**; decide flags vs deletions (1B–1C).
4. **Build the analytical order table** and daily activity (1D).
5. **Write the contact assumptions** (rates, intents, timing, calendar) and **generate contacts**;
   sanity-check against benchmarks (1E).
6. **Generate tickets and chats** with the company rules; **build the SQLite store** (1F).
7. **Write the knowledge base**; embed with bge-m3; evaluate retrieval (11).
8. **Forecast**: features with leakage guard, 5 models, rolling backtest, choose the main model.
9. **Simulation**: Erlang C, SimPy engine v1, validation against theory; engine v2 with skills,
   routers, duty, costs; verify v2 = v1 under uniform skills.
10. **Scheduling**: Erlang C requirement → CP-SAT two-stage model; baselines; labour-rule checks.
11. **Routing**: Gymnasium env on the twin; heuristic headroom study; MaskablePPO training;
    skill-score random search; paired comparison on unseen days.
12. **Language agents**: LLM client with pinning, cache and tracing; client, advisor (tools,
    rules engine), quality (rubric, judge); offline backups.
13. **Orchestration**: LangGraph conversation graph; streaming.
14. **Twin scenarios**: scenario file; prepared vs unprepared; fidelity report.
15. **Evaluation**: KPI engine, experiment suites with seeds and CIs, scorecard.
16. **Serving**: FastAPI + WebSocket, React front office + back office, MLflow, Docker Compose, CI, tests.
17. **Document and present**: this report, run guide, demo script.

## B15. Limitations, ethics and future work

- **Synthetic contacts**: rates and handle times are assumptions; euro results must be
  recalibrated on real logs. Fidelity checks make the dependency explicit.
- **Single channel, single queue, 4 problem families**: real centers mix voice, e-mail and chat
  and route by language and skill level.
- **Small local LLMs**: a 3B advisor is fluent but misses policy details; the hybrid design
  and the judge make this visible rather than hidden.
- **Judge calibration** uses proxy labels until humans label ≥ 20 (target 60) chats.
- **RL generalisation**: training on single days does not transfer fully to multi-day peak weeks.
- **Ethics**: customers must know they talk to an AI; the advisor never asks for card data or
  passwords (prompt rule and checklist); staffing recommendations stay human decisions; data
  stays local; synthetic records are flagged.
- **Next**: real-log calibration; multi-day RL episodes; human labeling; larger advisor on GPU;
  connectors to help-desk tools; voice channel.

## B16. Conclusion

CallVerse delivers a working, tested and documented digital twin in which forecasting,
simulation, optimization, reinforcement learning and LLM agents cooperate on one business
problem. The foundation (forecast + twin) and the planning objective clearly beat their
baselines; routing and AI answering bring measurable gains whose production form — tuned
rules and an LLM guided by a rules engine — was chosen by the project's own evidence. That
discipline — every claim with a baseline, a confidence interval and a fallback — is the
main result.

---

## Appendix A — Commands

| Command | Purpose |
|---|---|
| `callverse all [--quick] [--skip-data]` | whole pipeline |
| `callverse data` / `validate` | data layer and contracts |
| `callverse forecast [--fast]` | DSO4 forecast |
| `callverse train-rl` | DSO1 training |
| `callverse schedule --scenario X --planner cpsat` | DSO3 plan |
| `callverse simulate --scenario X --planner P --router R --seeds N [--unprepared]` | twin run |
| `callverse fidelity` | twin fidelity |
| `callverse chat --mode llm|template` | one conversation |
| `callverse agents --n N --variants template,rag,rag_policy` | DSO2 batches |
| `callverse judge-calibrate --judge rules|llm` | judge agreement |
| `callverse evaluate` | every experiment + scorecard |
| `callverse llm-pull` | download the Hugging Face models of the profile and pin their commits |
| `callverse llm-pin` | record the commits of the cached models |
| `callverse serve` | API for both apps |
| `npm run dev:front` / `dev:back` (in `frontend/`) | front office :5173 / back office :5174 |

## Appendix B — Glossary

**ASA**: average speed of answer (wait of answered customers). **Abandonment**: customer
leaves before being answered. **Service level (80/20)**: share answered within 20 s.
**Erlang C**: queueing formula for the probability of waiting with c agents. **wMAPE**:
Σ|error| / Σ actual. **CP-SAT**: constraint-programming / SAT integer solver. **PPO**:
proximal policy optimization (RL). **RAG**: retrieval-augmented generation. **Cohen's
kappa (quadratic)**: chance-corrected agreement on an ordinal scale. **KS test**:
two-sample test that two distributions are equal. **Common random numbers**: every option
simulated on the same random customers, so differences are due to the decision only.
