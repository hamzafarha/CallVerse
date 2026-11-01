# CallVerse — step-by-step run guide

This guide takes a fresh Windows machine to the two running apps (front office and back office). Every command is
for **PowerShell** from the project folder (`CallVerse/`). Linux/macOS: replace
`.venv\Scripts\activate` with `source .venv/bin/activate`.

Times are measured on the development laptop (Intel CPU, 16 GB RAM, GTX 1650 4 GB).

---

## 0. What you need

| Tool | Version | Why | Check |
|---|---|---|---|
| Python | 3.11 or 3.12 | the whole pipeline | `python --version` |
| Node.js | 20 LTS | the two React apps | `node --version` |
| Git | any | clone / version | `git --version` |
| NVIDIA GPU + driver *(optional)* | ≥ 4 GB VRAM, driver ≥ 560 | local Hugging Face LLMs (4-bit) | `nvidia-smi` |
| Docker Desktop *(optional)* | ≥ 24 | one-command deploy | `docker --version` |
| Disk space | ~12 GB | venv with CUDA torch (~6 GB), data (~0.4 GB), bge-m3 (~2.3 GB), LLMs (~3.1 GB) | |

Without a CUDA GPU the agents use their offline backups (approved templates, rule-based
judge); all pages and every evaluation still work.

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
# NVIDIA GPU: CUDA build of torch (~2.5 GB). No GPU: use .../whl/cpu instead.
pip install torch --index-url https://download.pytorch.org/whl/cu126
pip install -e ".[all]"
copy .env.example .env
```

`.[all]` installs the forecast (LightGBM, Prophet, statsmodels), agent (transformers,
accelerate, bitsandbytes, sentence-transformers, FAISS, LangGraph, Gymnasium,
Stable-Baselines3, OR-Tools), MLOps (MLflow, nbclient) and dev (pytest, ruff,
import-linter) extras.

Check the GPU is visible: `python -c "import torch; print(torch.cuda.is_available())"` → `True`.

First time only — let the embedding model download: in `.env` set `HF_HUB_OFFLINE=0`,
run step 4, then set it back to `1` (faster start, no network calls).

Check:

```powershell
callverse status
pytest -m "not llm" -q
```

---

## 3. Local LLMs from Hugging Face (≈5-60 min download, once)

```powershell
callverse llm-pull          # downloads the models of the active profile, pins their commits
callverse status            # GPU, models downloaded, LLMs available
```

| Role | Model (Hugging Face Hub) | Why |
|---|---|---|
| Advisor + simulated customer | `HuggingFaceTB/SmolLM3-3B` (4-bit: `unsloth/SmolLM3-3B-bnb-4bit`, 2 GB) | fully open 3B model, tool calling, Apache-2.0 |
| Quality judge | `ibm-granite/granite-4.0-1b` (4-bit: `unsloth/granite-4.0-1b-bnb-4bit`, 1.2 GB) | different family than the advisor (no self-preference), Apache-2.0 |
| Retrieval | `BAAI/bge-m3` (CPU) | multilingual embeddings for the knowledge base |

Both LLMs together use ~3.2 GB of VRAM (4-bit NF4 weights, bfloat16 compute), so they fit a
4 GB laptop GPU. `llm-pull` writes the exact commit of each repository to
`artifacts\traces\llm_models.lock.json`; afterwards models load from the local cache only
(`HF_HUB_OFFLINE=1`). Profiles (`CALLVERSE_LLM_PROFILE`): `gpu4gb` (default) or `full`
(full-precision weights, ≥ 12 GB GPU).

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
| 7 | `callverse agents --n 12 --variants rag_policy,rag` | ~30 min | LLM advisor variants (needs the GPU models) |
| 8 | `callverse judge-calibrate --judge llm` | ~15 min | LLM judge agreement (needs the GPU models) |

Single experiments for exploring:

```powershell
callverse schedule --scenario promo_spike --planner cpsat
callverse simulate --scenario delivery_delays --planner cpsat --router ppo --seeds 10 --unprepared
callverse chat --mode template
callverse chat --mode llm --variant rag_policy
```

---

## 5. Start the two apps

Terminal 1 — API (shared by both apps):

```powershell
.venv\Scripts\activate
callverse serve            # http://127.0.0.1:8000  (Swagger: /docs)
```

Terminal 2 — front office (customers + advisors):

```powershell
cd frontend
npm install                # once, installs the three workspaces
npm run dev:front          # http://localhost:5173
```

Terminal 3 — back office (managers' control room):

```powershell
cd frontend
npm run dev:back           # http://localhost:5174
```

Terminal 4 — MLflow UI (optional):

```powershell
.venv\Scripts\activate
mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000   # http://localhost:5000
```

Before a demo, open the back office → *Models & MLOps* → **Load models on GPU** (or call
`POST /api/system/warmup`): the first chat then answers at full speed (~8 s per reply)
instead of waiting ~20 s for the models to load.

| App | Pages |
|---|---|
| Front office :5173 | Home + semantic help search · Help centre · My orders (demo customers) · Live chat with the AI advisor · Advisor desk (queue, copilot drafts, autopilot, customer 360, quality review) |
| Back office :5174 | Overview · Data & contracts · Demand forecast · Digital twin (live floor + scenario lab) · Agent theater · Workforce agent · Quality & labeling · BO/DSO scorecard · Models & MLOps |

Both apps: `Ctrl+K` opens the command palette; the theme toggle is top right. Add
`?snapshot` to a URL to render every animation in its final state (screenshots).

---

## 6. Docker (one command)

```powershell
copy .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Front office (nginx) | http://localhost:8080 |
| Back office (nginx) | http://localhost:8081 |
| API | http://localhost:8000/docs |
| MLflow (+ Postgres) | http://localhost:5000 |

`data\` and `artifacts\` are mounted from the host, so build them first (step 4). The
default image is CPU-only (agents use their offline backups). With an NVIDIA GPU and the
NVIDIA Container Toolkit:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
docker compose exec api callverse llm-pull     # once: models go to the hf-cache volume
```

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `Raw data missing` | put the Olist/Bitext CSVs where step 1 says |
| `No index in data\knowledge_base\index` | `python scripts\build_knowledge_base.py` (needs bge-m3 once: `HF_HUB_OFFLINE=0`) |
| Sidebar says *Offline backups* | `nvidia-smi` works? CUDA torch installed (`torch.cuda.is_available()`)? `callverse llm-pull` done? (`callverse status` says which) |
| First LLM reply takes ~20 s | models load on first use: *Load models on GPU* in the back office before the demo |
| `CUDA out of memory` | close other GPU apps; only one process may hold the models (stop `callverse serve` while running `callverse agents`) |
| Output only `!!!!` | float16 overflow: keep the default bfloat16 compute (`src/callverse/llm/hf_local.py`) |
| `ppo` router missing in the UI | `callverse train-rl` |
| Evaluation page empty | `callverse evaluate` |
| Port 8000 busy | `callverse serve --port 8001` and `$env:VITE_API_TARGET="http://127.0.0.1:8001"; npm run dev:front` |
| Prophet/cmdstan error | `callverse forecast --fast` (skips Prophet and SARIMA) |
