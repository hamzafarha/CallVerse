# CallVerse online: ONE container runs the API and also serves both web apps, on port 7860 (the port that
# Hugging Face Spaces expect; on the Azure VM, Caddy passes the HTTPS traffic to it):
#   /               front office (customer portal, advisor desk, phone line)
#   /back-office/   back office (live contact centre, forecasts, workforce, AI monitoring)
#   /api, /ws       REST API and WebSockets        /docs   API documentation (Swagger)
# scripts/deploy_azure.py (Azure VM) and scripts/deploy_space.py (Hugging Face) copy this file to the root of
# a cleaned build folder, next to the code and data it needs (docs/RUN_GUIDE.md, "Put the app online").

# ---------- Stage 1: build the two React apps (Node.js is only needed here) ----------
FROM node:20-slim AS web
WORKDIR /web
# Package files first: Docker reuses the cached npm install while they do not change.
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/shared/package.json shared/
COPY frontend/front-office/package.json front-office/
COPY frontend/back-office/package.json back-office/
# The lock file was written on Windows, so it lists only the Windows builds of esbuild and rollup (the two
# native build tools). Add their Linux builds, at the versions of the lock file.
RUN npm ci --no-audit --no-fund \
    && ESBUILD=$(node -p "require('./package-lock.json').packages['node_modules/esbuild'].version") \
    && ROLLUP=$(node -p "require('./package-lock.json').packages['node_modules/rollup'].version") \
    && npm install --no-save --no-audit --no-fund "@esbuild/linux-x64@$ESBUILD" "@rollup/rollup-linux-x64-gnu@$ROLLUP"
COPY frontend/ ./
# One address for both apps: the links between them are paths, and the back office lives under /back-office/.
ENV VITE_FRONT_OFFICE_URL=/ \
    VITE_BACK_OFFICE_URL=/back-office/ \
    BACK_OFFICE_BASE=/back-office/
RUN npm run build

# ---------- Stage 2: the Python API, which also serves the apps built above ----------
# Python 3.12 and the library versions of space/constraints.txt (written by deploy_space.py from the local
# environment): the versions that trained and saved the models in artifacts/, so they load the same way.
FROM python:3.12-slim
# torch comes from its CPU index: the free Space hardware has no GPU (the agents use hosted LLMs).
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
# 1 = download the embedding model of the RAG search (bge-m3, 2.3 GB) during the build, so the Space starts
# without downloading anything; 0 = skip it (quicker test builds; the search then uses its TF-IDF backup).
ARG PRELOAD_EMBEDDER=1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MLFLOW_DISABLE_AGENT_HINT=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    CALLVERSE_ROOT=/app \
    CALLVERSE_STATIC_DIR=/app/web

# A C compiler, for the few packages that build native code.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
# Spaces run the container as the user with id 1000, not as root: create it and give it /app.
RUN useradd --create-home --uid 1000 user && mkdir /app && chown user /app
WORKDIR /app

# torch first (CPU build), then the package with the extras the API needs, at the pinned versions.
COPY space/constraints.txt space/
RUN pip install --upgrade pip \
    && pip install -c space/constraints.txt torch --index-url ${TORCH_INDEX}
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install -c space/constraints.txt ".[forecast,agents,mlops]"

# From here on, files belong to the Space user: the app writes new chats, traces and customers.
USER user
COPY --chown=user configs/ configs/
# The model's main branch only has pytorch_model.bin (the .safetensors copy is on a side branch that an
# offline server cannot find): download exactly those files, then prove that the model loads offline.
RUN if [ "$PRELOAD_EMBEDDER" = "1" ]; then \
      MODEL=$(python -c "import yaml; print(yaml.safe_load(open('configs/agents.yaml'))['advisor']['knowledge_base']['embedding_model'])") \
      && python -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1], allow_patterns=['*.json', '*.model', 'pytorch_model.bin', 'README.md'], ignore_patterns=['onnx/*'])" "$MODEL" \
      && HF_HUB_OFFLINE=1 python -c "import sys; from sentence_transformers import SentenceTransformer; SentenceTransformer(sys.argv[1], device='cpu'); print('loads offline:', sys.argv[1])" "$MODEL"; \
    fi
COPY --chown=user data/ data/
COPY --chown=user artifacts/ artifacts/
COPY --chown=user mlruns/ mlruns/
COPY --chown=user mlflow.db ./
COPY --from=web --chown=user /web/front-office/dist web/front-office/
COPY --from=web --chown=user /web/back-office/dist web/back-office/

# Nothing is downloaded while serving: the model is already here, and the LLMs are called over the internet.
ENV HF_HUB_OFFLINE=1
EXPOSE 7860
# --proxy-headers: Spaces put an https proxy in front of the app; trust the headers it forwards.
CMD ["uvicorn", "callverse.api.app:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
