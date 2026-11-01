# CallVerse shortcuts (Windows: run the commands of docs/RUN_GUIDE.md directly).
.PHONY: install install-gpu llm-pull lint test data forecast train evaluate all serve front back mlflow docker docker-gpu

install:
	python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
	python -m pip install -e ".[all]"
	cd frontend && npm install

# NVIDIA GPU (local Hugging Face LLMs in 4-bit): CUDA build of torch
install-gpu:
	python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
	python -m pip install -e ".[all]"
	cd frontend && npm install

llm-pull:
	callverse llm-pull

lint:
	ruff check .
	lint-imports

test:
	pytest -m "not llm"

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

serve:
	callverse serve

front:
	cd frontend && npm run dev:front

back:
	cd frontend && npm run dev:back

mlflow:
	mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

docker:
	docker compose up --build

docker-gpu:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
