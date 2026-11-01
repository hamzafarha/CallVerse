# CallVerse — presentation kit for a final-year internship (PFE)

Everything you need to present CallVerse to a recruiter or a technical interviewer:
pitches of three lengths, CV and LinkedIn text, the portfolio checklist, the demo path,
and the questions you will be asked (with answers grounded in what the project really did).

---

## 1. The pitch

**One sentence (CV, cold message)**
> I built CallVerse, a multi-agent digital twin of an e-commerce customer service center
> that forecasts demand, tests staffing and routing decisions in simulation, and grades AI
> customer conversations — cutting simulated staffing cost by 40% while keeping the
> service target.

**30 seconds (career fair, phone screen)**
> Call centers lose money in two ways: too many agents when it's quiet, too few at peaks.
> CallVerse is a virtual copy of a call center built from 99,000 real e-commerce orders.
> A LightGBM model forecasts contacts per problem type 20% more accurately than the
> classic baseline; a SimPy simulation replays a week of customers; an OR-Tools solver
> plans shifts, a reinforcement-learning agent routes customers, and LLM agents answer
> and grade conversations. Before a promotion, a manager can test the plan in the twin:
> in our peak scenarios, testing first cut understaffed hours by 60 to 84%.

**2 minutes (interview "tell me about a project")** — use the STAR structure:
- *Situation*: integrated data science project, e-commerce support center, no real call logs.
- *Task*: four business objectives (wait, quality, cost, peaks), each mapped to a data
  science objective with a baseline and a backup.
- *Action*: built the data pipeline (Olist + Bitext, Pandera contracts), the forecast
  (rolling backtest of 5 models), the SimPy twin (validated against Erlang C), the
  Workforce agent (CP-SAT + MaskablePPO), the RAG advisor and LLM judge (LangGraph,
  Hugging Face SmolLM3 + Granite in 4-bit on a 4 GB GPU), the KPI engine (seeds, 95% CIs),
  FastAPI with token streaming, two React apps (front office + back office), MLflow, Docker, CI.
- *Result*: cost −40% at the service target (CP-SAT), forecast error −20% vs naive,
  routing −14% wait on stressed days, retrieval recall@4 97% vs 80% for keyword
  search — and honest negatives: the small LLM advisor invented promises, so the
  rules-engine hybrid and the template backup were kept, exactly as our switch rules said.

---

## 2. CV bullets (pick 3-4)

- Built a **multi-agent digital twin** of a customer service center (Python, SimPy,
  LangGraph) combining forecasting, simulation, reinforcement learning, optimization and LLM agents.
- Forecast daily contacts per intent with **LightGBM** in a 46-week rolling-origin backtest:
  **wMAPE 25.3% vs 31.6%** for the seasonal naive baseline (−20%), benchmarked against SARIMA and Prophet.
- Planned shifts and overtime with **OR-Tools CP-SAT** under labour rules: **−40% labour cost**
  vs a peak-sized fixed schedule while meeting the 80/20 service level in simulation.
- Trained a **MaskablePPO** routing agent (Stable-Baselines3, Gymnasium) in the simulator:
  **−14% average speed of answer** vs FIFO on unseen stressed days.
- Built an **agentic RAG** advisor (bge-m3 + FAISS, tool calling over SQLite) on open-weight
  **Hugging Face** LLMs run locally with `transformers` + 4-bit `bitsandbytes` (SmolLM3-3B advisor,
  IBM Granite judge) and an **LLM-as-judge** with agreement measured by Cohen's kappa; retrieval
  recall@4 **97% vs 80%** for keyword search.
- Shipped it as a product: **FastAPI** (REST + WebSocket token streaming), two **React/TypeScript**
  apps on one design system — a customer/advisor **front office** (live AI chat, advisor desk with
  an AI copilot) and a manager **back office** (animated live floor of the twin, agent theater,
  scorecard) — **MLflow**, LLM tracing, **Docker Compose**, **GitHub Actions** CI (95+ tests,
  layered-architecture contracts).

## 3. LinkedIn post (draft)

> 🎧 What if a call center could test tomorrow's decisions today?
>
> For our integrated data science project at ESPRIT I built **CallVerse**, a digital twin of
> an e-commerce customer service center:
> 📈 a LightGBM forecast of contacts per problem type (−20% error vs the naive baseline)
> 🏭 a SimPy simulation of the center, validated against queueing theory
> 🧑‍💼 a Workforce agent: OR-Tools plans the shifts (−40% labour cost at the same service
> target), a reinforcement-learning agent routes customers
> 🤖 LLM agents (open-weight Hugging Face models running on my laptop GPU) that play customers,
> answer with RAG + tools, and grade each conversation
> 💬 a customer portal where you chat with the AI advisor live, and a control room where you
> watch the virtual contact centre work, customer by customer
> 🧪 every claim tested over 10 seeds with 95% confidence intervals
>
> My favourite lesson: the AI judge caught our small LLM advisor inventing promises — so we
> kept the rules-engine hybrid, exactly as our own "switch to backup" rule said.
> Stack: Python · LightGBM · SimPy · Stable-Baselines3 · OR-Tools · LangGraph · FAISS ·
> Hugging Face transformers · FastAPI · React · MLflow · Docker.
> I'm looking for a PFE internship in data science / ML engineering — happy to demo it! 🔗 [repo]

## 4. Portfolio checklist

- [ ] GitHub repo public (or private + access on request), README with the results table and a GIF.
- [ ] **Record a 2-3 minute demo video** (OBS): front-office live chat (tokens streaming, behind-the-scenes
      panel) → back-office live floor (promo spike, unprepared vs prepared) → agent theater → scorecard.
- [ ] Screenshots in `docs/img/` (front-office chat, advisor desk, live floor, agent theater, MLOps) —
      add `?snapshot` to the URL to freeze every animation in its final state.
- [ ] Pin the repo on GitHub; add topics: `digital-twin`, `reinforcement-learning`, `rag`,
      `langgraph`, `or-tools`, `forecasting`, `huggingface`, `fastapi`, `react`.
- [ ] One-page PDF summary (problem, architecture diagram, 4 results, stack, your role).
- [ ] Be able to run `callverse chat --mode template` and open the UI on your laptop in < 1 min.
- [ ] Know your numbers by heart (section 1) and the limits (section 6).

## 5. Demo path for an interview (5 minutes)

1. **Overview** (30 s): the BO→DSO scorecard — "each idea is compared with a baseline".
2. **Digital twin** (90 s): Promo spike → *Compare unprepared vs prepared vs fixed* → point at
   understaffed hours and abandonment; "the manager tests the plan before the promotion".
3. **Workforce → Shift planning** (45 s): CP-SAT heatmap + labour-rule badges.
4. **Agent playground** (90 s): one conversation; show tools, sources, the scorecard and the
   policy reference.
5. **Evaluation** (45 s): confidence intervals, the routing result, the honest negative on DSO2.

## 6. Interview questions you should expect

**"Your data is synthetic — why should I trust the results?"**
The orders, delays, cancellations and reviews are real (Olist); only the contacts are
generated, with every rate written in `configs/data.yaml` and a benchmark sanity check
(WISMO 3-10% of orders). The twin is validated three ways: queueing theory (Erlang C within
4%), volume/time-of-day/handle-time KS tests, and sensible scenario behaviour. With real logs
the same code becomes a real calibration. I present results as "the method works", not as
"this company saves X euros".

**"Why reinforcement learning for routing — wouldn't a rule do?"**
That's exactly our test: the optimized skill-score rule is the backup. PPO wins on stressed
days it never saw (−14% ASA) and cuts the longest waits most in peak weeks (p90 −18 to −25%),
but the tuned rule cut abandonment more. The decision rule from our DSO document keeps whichever beats FIFO more robustly; RL
is the more adaptive option, the rule is the more explainable one.

**"Why CP-SAT and not RL for shifts?"**
Labour rules (5 days, 40 h, 11 h rest) must be *guaranteed*, not learned through penalties.
A solver gives the cheapest legal plan and a provable optimum in under a second.

**"How do you know the LLM judge is reliable?"**
We don't assume it: agreement with labels is measured with quadratic Cohen's kappa and
Spearman. The UI has a labeling page; until 20+ human labels exist we use the generator's
answer key as proxy labels, and we report the judge as "not trusted" below kappa 0.4.

**"What was the hardest bug?"**
Good candidates: making the SimPy engine steppable for RL (pausing at each routing decision
inside an event-driven simulation), or proving the new engine reproduces version 1 exactly
(same start time for every contact).

**"What would you do with two more months?"**
Real call logs for calibration; multi-day RL episodes that match the scenario weeks; a
larger advisor model on a GPU server; human labeling of 100 chats; A/B rollout plan.

**"Where does the money come from?"** (business questions)
WFM software is sold per agent seat per month; a twin like this is a planning module on top
of an existing contact-center platform. See the commercial section of the report.

## 7. Skills this project demonstrates

| Area | Evidence in the repo |
|---|---|
| Time-series forecasting | `src/callverse/forecasting/`, rolling-origin backtest, leakage guard |
| Simulation & queueing | `src/callverse/simulation/engine.py`, Erlang C validation |
| Reinforcement learning | `agents/workforce/gym_wrapper.py`, MaskablePPO, reward design |
| Optimization | `agents/workforce/scheduling.py`, CP-SAT two-stage model |
| LLM engineering | `agents/advisor/`, `agents/quality/`, `orchestration/graph.py`, `llm/` |
| Statistics | paired differences, 95% CIs, KS tests, Cohen's kappa |
| Software engineering | layered architecture with import contracts, 95+ tests, CI, typing |
| MLOps | MLflow, model pinning, caching, tracing, Docker Compose |
| Full-stack | FastAPI + WebSocket streaming, two React + TypeScript apps (npm workspaces), Tailwind, Framer Motion, Recharts, canvas animation |
| LLM serving | `llm/hf_local.py`: 4-bit loading, chat templates, tool-call parsing, token streaming, JSON repair |
