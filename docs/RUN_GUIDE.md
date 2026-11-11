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
| Back office :5174 | Overview · Data & contracts · Demand forecast · Digital twin (live floor, side by side, scenario lab; simple and detailed views) · Agent theater · Workforce agent · Contact centre (live, full screen) · Models & MLOps · AI monitoring |

Both apps: `Ctrl+K` opens the command palette; the theme toggle is top right. Add
`?snapshot` to a URL to render every animation in its final state (screenshots).

### The contact centre page (for the projector)

Open **http://localhost:5174/centre** (or *Agents → Contact centre (live)* in the sidebar).
It fills the window, without the sidebar; the **full-screen** button (top right) or the
`F` key hides the browser too.

1. Choose **LLMs** (the real demo) or **Offline backups** (rehearsals: no OpenRouter
   request is used).
2. Press **A customer walks in** and choose who: **Random** (a real customer from the
   history), **A customer** (the portal's demo customers and the new customers created
   before), or **New customer** (a name, a persona, one of the 17 problems, a first
   message — a real one for that problem, editable — and a real Olist order or a new order
   with its dates and status; the same rules as the portal's form, and the customer is
   saved like a portal customer). The Client agent plays that customer, and the floor shows
   the real chat: the customer explains the problem at the reception (Workforce agent),
   walks to the chosen desk (Advisor agent: its tool badges pop up while it works, then
   move into its answer's bubble), the supervisor comes if the chat is escalated, and the
   quality lead shows the Quality agent's score. The KPI wall then counts the chat.
3. Click a **desk** to see that advisor's finished chats and the Quality agent's score of
   each one (the whole conversation opens with a click).
4. Real chats walk in too: every chat of the server appears on the floor, with a label that
   says who plays the customer: a person on the customer portal (*web chat*), a person on a
   phone (*phone call*), or the Client agent (Agent theater, advisor desk). Customers take
   turns like in a real centre: one at a time at the reception (the others wait in the
   waiting area), at most two chats per advisor, and the supervisor and the quality lead
   go to one desk at a time. A customer who closes the tab leaves the floor; a phone that
   hangs up leaves after 2 minutes (it may only have locked its screen).
5. **Voices on** reads every bubble aloud, each person with their own voice (the browser's
   speech engine: no server, no cost), plus three short announcements: the receptionist
   names the desk, the supervisor says which desk they join, the quality lead reads the
   score. A bubble stays until its voice ends. Voices start off: browsers only play sound
   after a click. Edge has the most natural voices.
6. **Talk as a customer** lets a visitor become a real customer from the history: click the
   microphone, speak, pause (speech to text in the browser: Chrome or Edge, on
   `localhost`). The advisor answers out loud on the floor. Quick replies give the order
   number (nobody can read a 32-character id aloud); end with a 1-5 star rating. The chat
   is labelled *visitor at the centre* on the floor and in the advisor's history.

Every move comes from a real event of the server (`/ws/centre`); the page only slows the
pace so each step can be read (**2×** speeds it up). Finished chats are saved in
`artifacts/traces/live_sessions/` (one file per chat); that folder is the advisors' history.

### The AI monitoring page

Open **http://localhost:5174/monitoring** (*Serving & MLOps → AI monitoring*). It reads
what CallVerse already records — the trace of every LLM call
(`artifacts/traces/llm_calls.jsonl`), the saved chats (live and evaluation runs) and the
evaluation's result tables — and shows: the LLMs (calls, errors, cache, providers),
latency (median and p95), tokens and cost (real cost, plus an "if we paid" estimate at the
yardstick price of `configs/monitoring.yaml`), the RAG (offline benchmark, live
citations), tool calling (who chose each tool: the AI, a pipeline step or a safety net;
MCP use), quality (the judge's scores, FCR, CSAT, and the judge's agreement with human
labels), routing (accuracy, the problems it mixes up, accuracy by confidence),
grounding, the engines and advisor variants side by side, the judge against the
customer's rating, and the numbers per resolved chat. Headline tiles turn orange or red
past the thresholds of `configs/monitoring.yaml`. Filters: last 24 hours / 7 days /
everything, and live chats / evaluation runs / all. API: `GET /api/monitoring?period=24h|7d|all&source=live|eval|all`.

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

## 7. Put the app online (Azure for Students)

The online demo runs **one Docker container**
([deploy/huggingface/Dockerfile](../deploy/huggingface/Dockerfile)) that serves the API and both apps from one
address: the front office at `/`, the back office at `/back-office/`, the API documentation at `/docs`. On
Azure it runs on a small Linux virtual machine (VM), behind Caddy, which gets a free HTTPS certificate.
Nothing needs to be installed on your PC: the VM is made in the Azure Portal (your browser), and the script
talks to it with SSH, which comes with Windows.

**Once: create the VM in the Azure Portal.** First print the public key the VM will trust (the script makes a
key pair just for this VM, in `~\.ssh\callverse_azure`):

```powershell
.venv\Scripts\python scripts\deploy_azure.py --public-key
```

Then on [portal.azure.com](https://portal.azure.com): *Virtual machines* → *Create* → *Azure virtual machine*.

| Tab | Setting | Value |
|---|---|---|
| Basics | Subscription · Resource group | Azure for Students · *Create new*: `callverse-rg` |
| Basics | Virtual machine name · Region | `callverse-vm` · (Europe) France Central (if *Review + create* refuses the region, pick another: Italy North, Spain Central, Sweden Central...) |
| Basics | Availability options | No infrastructure redundancy required |
| Basics | Image · Size | Ubuntu Server 24.04 LTS - x64 Gen2 · `Standard_B2ms` (2 vCPU, 8 GiB; or any other size with 8 GiB) |
| Basics | Authentication | SSH public key · username `azureuser` · *Use existing public key* · paste the line printed above |
| Basics | Public inbound ports | Allow selected ports: **SSH (22), HTTP (80), HTTPS (443)** |
| Disks | OS disk size · type | 64 GiB · Standard SSD |

*Review + create* → *Create* (2-3 minutes) → *Go to resource*. On the VM's *Overview*, click
**DNS name: Not configured**, type a label (e.g. `callverse-demo`), *Save*, and copy the full name it shows,
e.g. `callverse-demo.francecentral.cloudapp.azure.com`.

**Each deployment** (the first one takes 20-30 minutes; later ones update the app):

```powershell
.venv\Scripts\python scripts\deploy_azure.py --host callverse-demo.francecentral.cloudapp.azure.com --send-openrouter-key
```

It builds the cleaned folder (below), installs Docker on the VM, sends the folder (~120 MB compressed), builds
the image on the VM (the Python packages and the bge-m3 model download there, not on your connection), starts
the app and Caddy, and waits until `https://<name>/` answers. `--send-openrouter-key` copies the key from your
`.env` to a file on the VM that only its user can read (once is enough). Without it, or when the free daily
quota is used up (until 00:00 UTC), the agents answer with their offline templates and rules.

With the Azure CLI installed (`az login`), the script can also create the VM itself: run it without `--host`.

**Cost:** the VM uses your student credit while it runs (a few dollars a day; see *Cost Management* in the
Portal). On the VM's page, *Stop* pauses it (start it again before a demo: same address, the app restarts by
itself); deleting the resource group `callverse-rg` removes everything.

**Hugging Face Spaces (alternative):** `scripts\deploy_space.py` publishes the same container as a Space
(`hf auth login` first, then add `OPENROUTER_API_KEY` as a Space secret). Hugging Face now asks for a PRO
subscription to host Docker Spaces (error 402 when we tried, 2026-11-11), which is why the demo runs on Azure.

What the scripts upload, and what stays on your PC:

| Uploaded | Stays on your PC |
|---|---|
| the code (`src`, `configs`, `frontend` without `node_modules`), `pyproject.toml` | `.env`, the TLS keys (`frontend/certs`), caches |
| `data/callverse.db` **without the new customers you created** (their names) | `data/raw` (the CSVs: not needed online) |
| `data/processed`, `data/knowledge_base`, `data/external` | `artifacts/traces/live_sessions` (your real chats) |
| `artifacts/` (evaluations, forecasts, trained models), the LLM trace **without its texts** | `artifacts/traces/llm_cache.sqlite` |
| `mlflow.db`, `mlruns` | |

The script stops before the upload if it finds a key, a token or one of the removed names. It also writes
`space/constraints.txt` with this environment's library versions, so the Space loads the saved models with the
versions that made them. `--private` makes the Space visible only to you; `--keep-private-data` also uploads
the removed data (not recommended).

Good to know: the online app has no login, so anyone with the link can use it (do not type real personal
data). What visitors add (chats, customers) stays until the next deployment, which starts again from the
cleaned data.

---

## 8. Troubleshooting

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
