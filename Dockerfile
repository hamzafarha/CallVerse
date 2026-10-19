# CallVerse API (FastAPI + the whole Python pipeline), CPU only.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=0 \
    MLFLOW_DISABLE_AGENT_HINT=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# CPU wheels of torch first (avoids pulling the 2 GB CUDA build)
RUN pip install --upgrade pip && pip install torch --index-url https://download.pytorch.org/whl/cpu

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
