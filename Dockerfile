# CallVerse API (FastAPI + the whole Python pipeline). CPU by default; the GPU override
# (docker-compose.gpu.yml) installs the CUDA build of torch for the local LLMs.
FROM python:3.11-slim

ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=0 \
    MLFLOW_DISABLE_AGENT_HINT=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# torch first, from the CPU (default) or CUDA index
RUN pip install --upgrade pip && pip install torch --index-url ${TORCH_INDEX}

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install ".[forecast,agents,mlops]"

COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY notebooks/ ./notebooks/
# data/ and artifacts/ are mounted as volumes (see docker-compose.yml)

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "callverse.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
