# CallVerse shortcuts (Windows: run the commands of docs/RUN_GUIDE.md directly).
.PHONY: install install-gpu llm-pull lint test data forecast train evaluate all serve front back mlflow docker docker-gpu

# Install everything: torch (CPU build), the Python package with all extras (editable: code changes apply at
# once), and the frontend packages.
install:
	python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
	python -m pip install -e ".[all]"
	cd frontend && npm install

# NVIDIA GPU (local Hugging Face LLMs in 4-bit): CUDA build of torch
install-gpu:
	python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
	python -m pip install -e ".[all]"
	cd frontend && npm install

# Download the local backup LLMs once and pin their versions.
llm-pull:
	callverse llm-pull

# Code checks: ruff (style, real errors, import order) and import-linter (each layer only imports the layers
# below it, see pyproject.toml).
lint:
	ruff check .
	lint-imports

# Run the tests, except the ones that need a real LLM (marker "llm").
test:
	pytest -m "not llm"

# Pipeline steps: data (notebooks -> contacts, tickets, SQLite), forecast (backtest + next week), train-rl
# (PPO router), evaluate (scenarios x seeds, scorecard), or all of them in order.
data:
	callverse data

forecast:
	callverse forecast

train:
	callverse train-rl

evaluate:
	callverse evaluate

all:
	callverse all

# Start the API (port 8000), the front office (5173) and the back office (5174): one terminal each.
serve:
	callverse serve

front:
	cd frontend && npm run dev:front

back:
	cd frontend && npm run dev:back

# MLflow web page on port 5000, reading the local SQLite store.
mlflow:
	mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

# Docker: everything in containers (see docker-compose.yml); docker-gpu adds the NVIDIA GPU.
docker:
	docker compose up --build

docker-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
