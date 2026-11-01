# CallVerse

**A multi-agent digital twin of an e-commerce customer service center.**
Forecast how many customers will contact you, test staffing and routing decisions on a
virtual call center before applying them, and let AI agents answer and grade customer
conversations — all running locally, at zero API cost, with open-weight Hugging Face models.

> Integrated project (Advanced Data Science, ESPRIT). Data: real Olist orders (99,441)
> and Bitext customer messages; contacts, tickets and chats are generated from them
> with explicit, documented assumptions.

| | |
|---|---|
| **Business objectives** | BO1 shorter waits · BO2 correct answers & satisfaction · BO3 lower cost at equal service · BO4 prepare for peaks by testing first |
| **AI components** | LightGBM forecast · SimPy digital twin · MaskablePPO routing · OR-Tools CP-SAT shift planning · agentic RAG advisor (bge-m3 + FAISS + tools) · LLM-as-judge · LangGraph orchestration |
| **LLMs (Hugging Face, local)** | SmolLM3-3B (advisor + simulated customer) · IBM Granite-4.0-1B (quality judge, different family) · 4-bit NF4 with `transformers` + `bitsandbytes` on a 4 GB GPU · commits pinned |
| **Apps** | **Front office** (customers + advisors): help centre, live chat with the AI advisor, advisor desk with an AI copilot · **Back office** (managers): live floor of the twin, agent theater, forecast, workforce, quality, scorecard, MLOps |
| **Serving & MLOps** | FastAPI (REST + WebSocket token streaming) · React + TypeScript + Framer Motion (npm workspaces, shared design system) · MLflow · LLM tracing · Docker Compose · GitHub Actions |

## Results (from `callverse evaluate`, 10 seeds, 95% CIs)

| Objective | Main idea vs baseline | Result |
|---|---|---|
| **BO4 / DSO4** forecast | LightGBM vs "same day last week" | wMAPE **25.3%** vs 31.6% (−19.9% error), rolling backtest over 46 weeks |
| **BO4 / DSO4** twin | prepared vs unprepared plan in peak weeks | understaffed hours **−60% to −84%**, abandonment **−55% to −76%** (all significant) |
| **BO4 / DSO4** fidelity | simulated vs historical / queueing theory | KS volume p=0.998, hourly profile TVD 0.015, Erlang C error < 4% |
| **BO3 / DSO3** shifts | CP-SAT vs peak-sized fixed schedule | labour cost **−40%** with service level still above the 80% target; all labour rules respected |
| **BO1 / DSO1** routing | PPO / skill score vs FIFO | ASA **−14%** (PPO, unseen stressed days); peak weeks: p90 wait −18% to −25% (PPO), abandonment −8% to −11% (skill score) |
| **BO2 / DSO2** advisor | bge-m3 RAG vs keyword search; LLM variants | context recall@4 **96.9%** vs 80.4%; RAG + rules-engine hybrid **12/12** verified policy-correct actions, best CSAT (4.33/5) |

See [docs/IP_VALIDATION_REPORT.md](docs/IP_VALIDATION_REPORT.md) for the full analysis,
including where an idea did **not** beat its baseline and the backup that took over.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cu126   # NVIDIA GPU (or .../whl/cpu)
pip install -e ".[all]"
copy .env.example .env
callverse llm-pull             # SmolLM3-3B + Granite-4.0-1B, 4-bit (~3 GB, once)
callverse all --skip-data      # forecast -> RL training -> evaluation (~20 min)
callverse serve                # API on http://127.0.0.1:8000 (Swagger: /docs)
cd frontend; npm install
npm run dev:front              # front office  http://localhost:5173
npm run dev:back               # back office   http://localhost:5174  (second terminal)
```

Without a CUDA GPU (or before `llm-pull`) every agent uses its offline backup
(approved templates, rule-based judge), so everything still runs.

Full instructions: [docs/RUN_GUIDE.md](docs/RUN_GUIDE.md) ·
Demo for the validation day: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) ·
Internship (PFE) presentation kit: [docs/RECRUITER_KIT.md](docs/RECRUITER_KIT.md)

## Architecture

```
Data layer ──> Forecast & simulation ──> Digital twin (4 agents, LangGraph) ──> Evaluation ──> Serving & MLOps
 Olist+Bitext    LightGBM per intent       Client  · Advisor (RAG+tools)        KPI engine      FastAPI + WebSocket
 SQLite, FAISS   SimPy event simulation    Quality (LLM judge) · Workforce      scenarios×seeds React front + back office
 Pandera         twin fidelity (KS)        (PPO routing + CP-SAT shifts)        component metrics MLflow, Docker, CI
```

Layers are enforced by `import-linter` contracts (a lower layer never imports a higher one).

## Project structure

```
configs/            every assumption, one YAML per layer (data, simulation, agents, scenarios, app)
data/               raw (Olist, Bitext) -> processed (Parquet) -> SQLite store, knowledge base
notebooks/          01-12: documented data exploration, cleaning, contact generation, studies
src/callverse/
  data/             notebook runner, Pandera contracts, SQLite store, tickets & chat generator
  forecasting/      features (leakage-safe), baselines, LightGBM, rolling backtest
  simulation/       SimPy engine, routers, Erlang C, customers, twin setup
  agents/           client/ advisor/ quality/ workforce/  (the four agents)
  orchestration/    LangGraph conversation graph, live sessions (human + agents), runtime
  twin/             digital twin scenarios and fidelity checks
  evaluation/       KPI engine, experiments, component metrics, scorecard
  llm/              Hugging Face client (transformers, 4-bit), streaming, cache, tracing
  api/              FastAPI app
frontend/           npm workspaces: shared/ (design system), front-office/, back-office/
tests/              unit, smoke and integration tests (pytest)
docs/               report, run guide, demo script, recruiter kit, phase reports
```

## License and data

Olist data: CC BY-NC-SA 4.0 (Kaggle). Bitext dataset: CDLA-Sharing. Synthetic contacts,
tickets and chats are generated by this project and marked `is_synthetic = True`.
