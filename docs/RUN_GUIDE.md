# CallVerse — step-by-step run guide

This guide takes a fresh Windows machine to the running control room. Every command is
for **PowerShell** from the project folder (`CallVerse/`). Linux/macOS: replace
`.venv\Scripts\activate` with `source .venv/bin/activate`.

Times are measured on the development laptop (Intel CPU, 16 GB RAM, GTX 1650 4 GB).

---

## 0. What you need

| Tool | Version | Why | Check |
|---|---|---|---|
| Python | 3.11 or 3.12 | the whole pipeline | `python --version` |
| Node.js | 20 LTS | the React control room | `node --version` |
| Git | any | clone / version | `git --version` |
| Ollama *(optional)* | ≥ 0.5 | local LLMs for the agents | `ollama --version` |
| Docker Desktop *(optional)* | ≥ 24 | one-command deploy | `docker --version` |
| Disk space | ~8 GB | venv (~3 GB), data (~0.4 GB), bge-m3 (~2.3 GB), LLMs (~4-9 GB) | |

Without Ollama the agents use their offline backups (templates, rule-based judge); all
pages and every evaluation still work.

---

## 1. Get the code and the raw data

```powershell
git clone <your-repo-url> CallVerse
cd CallVerse
```

Raw data (not in git, ~120 MB):

1. **Olist** — <https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> → unzip the 9 CSV
   files into `data\raw\olist\`.
2. **Bitext** — <https://huggingface.co/datasets/bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset>
   → save the CSV as
   `data\raw\bitext\bitext-retail-ecommerce-llm-chatbot-training-dataset.csv`.

> Already have `data\processed\` and `data\callverse.db` (e.g. copied from a teammate)?
> You can skip the data stage with `--skip-data` below.

---

## 2. Python environment (≈10 min, once)

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[all]"
copy .env.example .env
```

`.[all]` installs the forecast (LightGBM, Prophet, statsmodels), agent (sentence-transformers,
FAISS, LangGraph, Gymnasium, Stable-Baselines3, OR-Tools), MLOps (MLflow, nbclient) and
dev (pytest, ruff, import-linter) extras.

First time only — let the embedding model download: in `.env` set `HF_HUB_OFFLINE=0`,
run step 4, then set it back to `1` (faster start, no network calls).

Check:

```powershell
callverse status
pytest -m "not llm" -q
```

---

## 3. Local LLMs with Ollama (optional, ≈10 min download)

```powershell
ollama pull qwen2.5:3b      # client agent (and advisor in the "fast" profile)
ollama pull llama3.2        # quality judge (different model family)
ollama pull qwen2.5:7b      # advisor in the "full" profile (needs > 6 GB VRAM to be fast)
callverse llm-pin           # records the exact model digests (reproducibility)
```

Profiles (`.env`, `CALLVERSE_LLM_PROFILE`): `fast` = everything fits a 4 GB GPU (~1 min per
conversation), `full` = the architecture's 7B advisor (~3-5 min per conversation on 4 GB).

---

## 4. Run the pipeline

Everything at once:

```powershell
callverse all                # with the data stage (~35 min)
callverse all --skip-data    # data already built (~20 min)
callverse all --quick --skip-data   # demo-grade in ~6 min (fewer seeds, 50k PPO steps)
```

Or stage by stage (what each produces):

| # | Command | Time | Output |
|---|---|---|---|
| 1 | `callverse data` | ~15 min | `data\processed\*.parquet`, `data\callverse.db`, KB index; executed notebooks in `artifacts\notebook_runs\` |
| 2 | `callverse validate` | 5 s | Pandera data contracts (PASS/FAIL per table) |
| 3 | `callverse forecast` | ~5 min (`--fast`: 20 s) | backtest of 5 models, LightGBM model, next-week forecast, MLflow run |
| 4 | `callverse train-rl` | ~15 min | skill-score weights + MaskablePPO policy in `artifacts\policies\` |
| 5 | `callverse fidelity` | 20 s | twin fidelity checks (Erlang C, KS tests) |
| 6 | `callverse evaluate` | ~12 min | every experiment, `component_metrics.csv`, `scorecard.json` |
| 7 | `callverse agents --n 15 --variants rag_policy,rag` | ~45 min | LLM advisor variants (needs Ollama) |
| 8 | `callverse judge-calibrate --judge llm` | ~10 min | LLM judge agreement (needs Ollama) |

Single experiments for exploring:

```powershell
callverse schedule --scenario promo_spike --planner cpsat
callverse simulate --scenario delivery_delays --planner cpsat --router ppo --seeds 10 --unprepared
callverse chat --mode template
callverse chat --mode llm --variant rag_policy
```

---

## 5. Start the control room

Terminal 1 — API:

```powershell
.venv\Scripts\activate
callverse serve            # http://127.0.0.1:8000  (API docs: /docs)
```

Terminal 2 — UI (development server with hot reload):

```powershell
cd frontend
npm install                # once
npm run dev                # http://localhost:5173
```

Terminal 3 — MLflow UI (optional):

```powershell
.venv\Scripts\activate
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000   # http://localhost:5000
```

Single-port alternative: `cd frontend; npm run build`, then `callverse serve` also serves the
built UI on http://127.0.0.1:8000.

---

## 6. Docker (one command)

```powershell
copy .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| UI (nginx) | http://localhost:8080 |
| API | http://localhost:8000/docs |
| MLflow (+ Postgres) | http://localhost:5000 |

`data\` and `artifacts\` are mounted from the host, so build them first (step 4). The API
reaches Ollama on the host through `host.docker.internal`; `docker compose --profile llm up`
starts Ollama in a container instead.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Raw data missing` | put the Olist/Bitext CSVs where step 1 says |
| `No index in data\knowledge_base\index` | `python scripts\build_knowledge_base.py` (needs bge-m3 once: `HF_HUB_OFFLINE=0`) |
| Agents page says *Ollama offline* | start Ollama (`ollama serve`) or use "Offline backups" |
| LLM conversation very slow | `CALLVERSE_LLM_PROFILE=fast` in `.env`, restart `callverse serve` |
| `ppo` router missing in the UI | `callverse train-rl` |
| Evaluation page empty | `callverse evaluate` |
| Port 8000 busy | `callverse serve --port 8001` and `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev` |
| Prophet/cmdstan error | `callverse forecast --fast` (skips Prophet and SARIMA) |
