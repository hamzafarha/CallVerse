# CallVerse — validation day: demo script

A 20-minute presentation + live demo for the tutor, then questions. Times in brackets.
Everything shown is produced by commands of the run guide; nothing is mocked.

---

## The day before (checklist)

- [ ] `callverse status` → every box ticked (data, store, KB index, forecast, PPO, classifier, scorecard).
- [ ] `pytest -m "not llm" -q` → all tests pass (show it if asked about quality).
- [ ] `ollama list` shows `qwen2.5:3b` and `llama3.2`; run **one** LLM conversation so the
      models are warm and the answer is cached (`callverse chat --mode llm --contact SC006158`).
- [ ] Laptop on power, GPU drivers OK, notifications off, screen resolution 1920×1080, browser zoom 100%.
- [ ] Backup plan: a recorded 3-minute video of the demo + screenshots in `docs/img/`, in case
      Wi-Fi/Ollama fails. The offline backups also work with no network at all.

## Start-up (5 minutes before)

Terminal 1:
```powershell
cd CallVerse; .venv\Scripts\activate
callverse serve
```
Terminal 2:
```powershell
cd CallVerse\frontend; npm run dev
```
Terminal 3 (optional): `mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000`

Open http://localhost:5173 (light mode for a projector: toggle bottom-left).

---

## Part 1 — The business problem (3 min, slides or the Overview page)

**Say:** "An e-commerce call center fails in two ways: too few agents during promotions and
delivery delays, too many when it is quiet. Decisions are made on intuition and tested on
real customers. Our goal: a virtual copy of the center where every decision is tested first."

**Show:** Overview page → the four BO → DSO cards.

- BO1 shorter waits → DSO1 routing agent
- BO2 correct answers → DSO2 RAG advisor + AI judge
- BO3 lower cost at equal service → DSO3 shift planning
- BO4 prepare for peaks → DSO4 forecast + digital twin

**Say:** "Every idea has a baseline and a backup. We keep an idea only if it beats its
baseline; the scorecard applies that rule automatically."

## Part 2 — Data (2 min, Data layer page)

**Show:** weekly contacts chart, the "why customers contact us" table, data contracts.

**Say:** "There are no public call-center logs. We start from 99,441 real Olist orders. Each
order situation — late delivery, cancellation, payment anomaly, bad review — has a contact
probability written in `configs/data.yaml`. The wording comes from real Bitext customer
messages. 9,179 contacts, 9,179 tickets and 60,837 chat messages, all marked synthetic.
Pandera contracts check every table before the models read it."

## Part 3 — Forecast (2 min, Forecast page)

**Show:** the three stat tiles, the actual-vs-forecast chart, the wMAPE table.

**Say:** "Rolling-origin backtest: every Sunday for 46 weeks, each model only sees the past.
LightGBM uses lagged orders, late deliveries and the promotion calendar. wMAPE 25.3%
against 31.6% for 'same day last week': 20% less error. It also beats SARIMA and Prophet on the
total. Small groups are noisy — a few contacts a day — so we decide at the total level."

## Part 4 — The digital twin, live (5 min, Digital twin page) ⭐ main demo

1. Scenario **Promo spike**, planner **CP-SAT**, routing **FIFO**, *Normal forecast (unprepared)*, 5 seeds → **Run**.
   **Say:** "This is what happens if we plan the promotion week like a normal week."
   Point at: service level ~76%, abandonment ~12%, understaffed hours ~42.
2. Switch to *Scenario forecast (prepared)* → **Run**.
   **Say:** "Same customers, plan tested in the twin first: service ~92%, abandonment ~4.5%,
   understaffed hours −71%." Point at the 95% intervals: "10 seeds, the difference is significant."
3. Click **Compare unprepared vs prepared vs fixed**.
   **Say:** "The fixed schedule sized for the peak also works — at 67% more labour cost. The
   CP-SAT plan is the cheapest plan that meets the target."
4. Move the *Where is my order* slider to ×2.5 and *Absent agents* to 20% → Run.
   **Say:** "Any what-if in about 3 seconds: this is BO4's 'time needed to decide'."

## Part 5 — Workforce agent (2 min, Workforce page)

**Show:** Shift planning → required vs scheduled heatmaps, the four labour-rule badges, roster.
**Say:** "CP-SAT chooses 4, 6 and 8-hour shifts and overtime hours, then assigns them to named
agents: max 5 days, 40 hours, 11 hours rest — guaranteed, not learned."

Switch to **Real-time routing** → learning curve and the comparison.
**Say:** "The routing agent is MaskablePPO, trained only in the simulator. On unseen stressed
days it cuts the average speed of answer by 14% versus FIFO, and in peak weeks it cuts the
longest waits (90th percentile) by 18-25%. In full peak weeks the tuned
skill-score rule reduces abandonment more — so, following our own rule, the skill-score
backup is the production candidate and PPO stays the research track."

## Part 6 — The four agents together (3 min, Agent playground)

1. Pick a contact, *Local LLMs via Ollama*, variant *RAG + tools + rules engine* → Start.
   (If time is short or Ollama fails: *Offline backups* — instant.)
2. While it streams, **say:** "LangGraph runs the graph: the Client agent — a small LLM — plays
   the customer; the Workforce agent predicts the problem type and routes to a specialist; the
   Advisor retrieves policy sections with bge-m3 + FAISS and calls tools on the SQLite store;
   the Quality agent — a Llama model, different family from the Qwen advisor — grades the
   chat against the policy-correct outcome."
3. Point at the tool calls, the sources, the scorecard and the reference outcome.

## Part 7 — Evaluation and honesty (2 min, Evaluation + Quality pages)

**Show:** the scorecard table, BO4 savings with the break-even, component metrics.
**Say:**
- "Retrieval: recall@4 97% with bge-m3 versus 80% with keyword search — the DSO2 baseline."
- "The AI judge must agree with humans: here is the labeling page; the agreement is measured
  with Cohen's kappa. On proxy labels the judge is not yet trusted — that is a result, not a bug."
- "Testing first saves money when a lost customer is worth more than 6 to 12 euros."

## Part 8 — Serving & MLOps (1 min, MLOps page)

**Show:** MLflow runs, LLM tracing by agent, pinned models, `docker compose up`, the CI workflow.

---

## Likely questions and short answers

| Question | Answer |
|---|---|
| Why synthetic contacts? | No public call logs; real orders + explicit rates + real wording; validated against benchmarks and queueing theory; the pipeline accepts real logs unchanged. |
| How do you know the twin is realistic? | Erlang C check (<4% error), KS tests on daily volume (p=0.998) and handle time, hourly profile distance 0.015, and scenarios move KPIs in the expected direction. |
| Why LightGBM and not deep learning? | ~600 days × 4 series: too little for deep models; LightGBM with lags beats SARIMA/Prophet and is explainable (feature importance). |
| How is leakage avoided? | Every lag ≥ 7 days, rolling origins, a leakage guard test (`lag_7` equals the value 7 days before). |
| Why is PPO not the winner everywhere? | Trained on single stressed days; peak weeks differ (multi-day backlog, planned overtime). Our rule keeps the backup when the main idea doesn't clearly beat FIFO. |
| Why CP-SAT instead of RL for shifts? | Labour rules must be guaranteed; the solver gives the optimal legal plan in < 1 s. |
| LLM cost? | Zero: local Ollama models; every call is traced (tokens, latency) and cached. |
| What if Ollama is down? | Every agent has an offline backup; the UI says which mode answered. |
| Reproducibility? | Fixed seeds in configs, pinned model digests, MLflow runs, `callverse all` rebuilds everything. |
| What's next? | Real logs to calibrate; human labels (60) for the judge; multi-day RL episodes; GPU for the 7B advisor. |
