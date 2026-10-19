# CallVerse shortcuts (Windows: run the commands of docs/RUN_GUIDE.md directly).
.PHONY: install lint test data forecast train evaluate all serve ui dev mlflow docker

install:
	python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
	python -m pip install -e ".[all]"
	cd frontend && npm install

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

ui:
	cd frontend && npm run dev

mlflow:
	mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

docker:
	docker compose up --build
