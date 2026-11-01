# CallVerse — validation day: demo script

A 20-minute presentation + live demo for the tutor, then questions. Times in brackets.
Everything shown is produced by the code and the commands of the run guide; nothing is
mocked. Two apps run side by side:

- **Front office** (http://localhost:5173) — what customers and advisors use.
- **Back office** (http://localhost:5174) — what managers use: the control room of the twin.

---

## The day before (checklist)

- [ ] `callverse status` → every box ticked; *LLMs available = True*, GPU = GTX 1650.
- [ ] `pytest -m "not llm" -q` → all tests pass (show it if asked about quality).
- [ ] Run **one** live chat in the front office so the models, bge-m3 and the answer cache are warm.
- [ ] Laptop on power, GPU drivers OK, notifications off, 1920×1080, browser zoom 100%,
      nothing else using the GPU (close games, video editors, other Python processes).
- [ ] Backup plan: a recorded 3-minute video + screenshots (`http://localhost:5174/?snapshot`
      renders every animation in its final state). Without the GPU every agent switches to its
      offline backup, so the demo still runs with no network and no LLM.

## Start-up (5 minutes before)

```powershell
# Terminal 1 — API
cd CallVerse; .venv\Scripts\activate; callverse serve
# Terminal 2 — front office
cd CallVerse\frontend; npm run dev:front
# Terminal 3 — back office
cd CallVerse\frontend; npm run dev:back
```

Open both apps in two browser tabs. Back office → *Models & MLOps* → **Load models on GPU**
(~20 s; the sidebar card turns to "2 models loaded"). Front office: light theme (projector);
back office: dark theme (control room). Toggle top right.

---

## Part 1 — The hook: a customer chats with the AI (3 min, front office) ⭐

1. Front office home. **Say:** "This is the customer side of our virtual contact centre."
   Point at the animated hero (the chat demo loops) and type *"my parcel is late"* in the
   search box: semantic results appear with their similarity scores (bge-m3 + FAISS).
2. *Try it as a real customer* → pick a card with a red **days late** badge.
   **Say:** "Each card is a real Olist order and the real message its customer sent. The twin
   replays the day they contacted us." Point at the order timeline (late step in red).
3. **Chat with an advisor** → click the suggested opening message, then *My order number is…*.
   While tokens stream, point at **Behind the scenes** on the right:
   - Workforce agent: predicted intent + confidence, desk, Erlang C expected wait.
   - Knowledge-base hits with cosine scores, *Order lookup ✓*, *Rules engine ✓*.
   - *LLM writes the reply* — SmolLM3-3B from Hugging Face, 4-bit, on the laptop GPU.
   **Say:** "The rules engine decides, the LLM only writes. That is why it never invents a refund."
4. **End chat** → 4 stars → the Granite judge's scorecard animates (radar, verdicts, rationale).
   **Say:** "A different model family grades every chat, against the policy-correct answer."

## Part 2 — The business problem (2 min, back office Overview)

**Show:** the hero ring "2/4 main ideas kept" and the four BO → DSO cards.

- BO1 shorter waits → DSO1 routing agent
- BO2 correct answers → DSO2 RAG advisor + AI judge
- BO3 lower cost at equal service → DSO3 shift planning
- BO4 prepare for peaks → DSO4 forecast + digital twin

**Say:** "Every idea has a baseline and a backup. We keep an idea only if it beats its
baseline; the scorecard applies that rule automatically — two ideas won, two backups took over."
Point at the animated architecture map: five layers, data flowing left to right.

## Part 3 — Data and forecast (3 min, Data + Demand forecast)

**Say:** "There are no public call-center logs. We start from 99,441 real Olist orders. Each
order situation — late delivery, cancellation, payment anomaly — has a contact probability in
`configs/data.yaml`; the wording comes from real Bitext messages: 9,179 contacts, 9,179 tickets,
60,837 chat messages, all marked synthetic. Pandera contracts check every table."

Forecast page. **Say:** "Rolling-origin backtest over 46 weeks: LightGBM wMAPE 25.3% against
31.6% for 'same day last week' — 20% less error, also better than SARIMA and Prophet."

## Part 4 — The digital twin, live floor (4 min, Digital twin) ⭐ main demo

1. *Live floor*: Promo spike, Wednesday, CP-SAT, FIFO, **Normal forecast (unprepared)**.
   Press play. **Say:** "Every dot is a customer of the simulation; desks are agents, coloured by
   skill." At 08:00 point at the ✉ desks and *Backlog left*: "All agents start on last night's
   messages, live customers queue behind them and hang up — red dots." Click
   **Jump to the peak** and let it run at 15 min/s.
2. Switch *Plan built from* to **Scenario forecast (prepared)**: fewer red dots, higher service level.
   **Say:** "Same customers, a plan tested in the twin first."
3. *Scenario lab* tab → **Compare unprepared vs prepared vs fixed** (5 seeds).
   **Say:** "Prepared: understaffed hours −60 to −84%, abandonment −55 to −76%, all significant
   (95% CIs over common random numbers). The peak-sized fixed schedule also works — at ~67%
   more labour cost. CP-SAT is the cheapest plan that meets the target." (BO3: −40% cost.)

## Part 5 — The four agents together (2 min, Agent theater)

Pick a contact → *Local LLMs*, *Hybrid* → **Start conversation**. The LangGraph pipeline lights
up node by node while the transcript streams. **Say:** "No human here: the Client agent plays the
customer, the Workforce agent routes, the Advisor answers, the Quality agent grades, the KPI
engine records FCR, CSAT and compliance. This is how we evaluate the advisor on many
conversations before a real customer sees it." (~45 s per conversation; *Offline backups* is instant.)

## Part 6 — The advisor desk: human + AI copilot (2 min, front office)

Front office → *Advisor desk*. Accept the longest-waiting customer (timers tick live).
The Client agent writes as the customer; the **copilot draft** streams in above the composer.
Click **Edit first**, change a word, send. Toggle **Autopilot** to let the agent finish, then
**Wrap up** → the Quality tab opens with the scorecard. **Say:** "Human in the loop: the copilot
drafts from the policies and the order, the advisor stays responsible."

## Part 7 — Workforce agent and evaluation (2 min, back office)

Workforce page: CP-SAT heatmaps, four labour-rule badges, the PPO learning curve.
**Say:** "PPO cuts the average speed of answer by 14% on unseen stressed days, but in full peak
weeks the tuned skill-score rule wins, so — following our own rule — it is the production candidate."
Evaluation page: scorecard, BO4 break-even (a lost customer worth more than €6–12).
Quality page: "The judge must agree with humans: here is the labeling studio; agreement is Cohen's
kappa. On proxy labels the judge is not yet trusted — a result, not a bug."

## Part 8 — Serving & MLOps (1 min, Models & MLOps)

**Show:** the three Hugging Face model cards (family, licence, pinned commit, VRAM), the GPU
gauge, LLM tracing (latency, tokens/s per agent), MLflow runs, `docker compose up`, the CI workflow.

---

## Likely questions and short answers

| Question | Answer |
|---|---|
| Why two apps? | Different users and risks: the front office is customer/advisor-facing (chat, desk); the back office is for managers (planning, evaluation, MLOps). Same API, same design system (npm workspaces). |
| Which LLMs, and why? | Hugging Face open weights: SmolLM3-3B (advisor + simulated customer) and IBM Granite-4.0-1B (judge, another family to avoid self-preference). 4-bit NF4 with `transformers` + `bitsandbytes`: both fit a 4 GB laptop GPU (~3.2 GB). |
| LLM cost? Privacy? | Zero per call; nothing leaves the laptop. Every call is traced (tokens, latency, tokens/s) and cached. |
| Why does the LLM not decide refunds? | Small models invent ids and promises. The hybrid design lets a deterministic rules engine decide; the LLM only writes. Verified-action rate is the DSO2 metric. |
| Why synthetic contacts? | No public call logs; real orders + explicit rates + real wording; validated against queueing theory; the pipeline accepts real logs unchanged. |
| How do you know the twin is realistic? | Erlang C check (<4% error), KS tests on daily volume (p=0.998) and handle time, hourly profile distance 0.015. |
| Why LightGBM and not deep learning? | ~600 days × 4 series: too little for deep models; LightGBM with lags beats SARIMA/Prophet and is explainable. |
| How is leakage avoided? | Every lag ≥ 7 days, rolling origins, a leakage guard test. |
| Why is PPO not the winner everywhere? | Trained on single stressed days; peak weeks differ (multi-day backlog, planned overtime). Our rule keeps the backup when the main idea doesn't clearly beat FIFO. |
| Why CP-SAT instead of RL for shifts? | Labour rules must be guaranteed; the solver gives the optimal legal plan in < 1 s. |
| What if the GPU fails? | Every agent has an offline backup; the UI says which mode answered. |
| Reproducibility? | Fixed seeds, Hugging Face commits pinned in `llm_models.lock.json`, MLflow runs, `callverse all` rebuilds everything. |
| What's next? | Real logs to calibrate; 60 human labels for the judge; multi-day RL episodes; a bigger advisor on a server GPU. |
