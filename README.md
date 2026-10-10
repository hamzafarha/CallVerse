# CallVerse

CallVerse is a digital twin of an e-commerce customer-contact center. It models the complete lifecycle of customer interactions: data generation and preprocessing, demand forecasting, discrete-event simulation, multi-agent workforce and advisor policies, closed-loop evaluation, and interactive dashboards/APIs.

The system is designed for high-fidelity simulation and optimization with zero budget, running locally with no network calls and no mandatory external LLM APIs.

## Architecture & Project Pipeline

```
Data -> Forecasting -> Discrete-Event Simulation -> Agents -> Evaluation -> API / Dashboard
```

- **Data**: Synthetic call-center generator, contact schemas, preprocessing, and validation.
- **Forecasting**: Arrival and demand modeling (baselines, feature pipelines, multi-horizon predictors).
- **Simulation**: SimPy-based discrete-event queueing system (events, customers, resources, policies, scenarios).
- **Twin**: Digital twin state management, replay, and calibration against historical traces.
- **Agents**: Client simulator, advisor copilot (RAG/tools), quality reviewer, and workforce RL manager (routing/scheduling).
- **Evaluation**: Closed-loop business KPIs, forecast metrics, advisor quality metrics, and experimentation harness.
- **API & Dashboard**: FastAPI services and Streamlit analytics control room.

## Quickstart

### Prerequisites

- Python 3.11+
- Virtual environment manager (`venv` recommended)
- Docker & Docker Compose (optional, for containerized run)

### Installation

Clone the repository and install core and development dependencies:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install CallVerse in editable mode with development tools
make install
```

### Running Tests and Linters

```bash
# Run code linting
make lint

# Run import boundary enforcement checks
make import-lint

# Run test suite
make test

# Run smoke tests
make smoke
```

### CLI Usage

```bash
# Inspect available CLI commands
callverse --help
```

Available commands include:
- `callverse generate-data`: Generate synthetic customer contact center dataset
- `callverse simulate`: Run discrete-event simulation
- `callverse compare`: Compare baseline and twin simulation scenarios
- `callverse train-forecast`: Train call arrival and demand forecasting models
- `callverse train-rl`: Train workforce routing and scheduling RL policy
- `callverse experiments`: Run evaluation and experimentation pipeline

### Docker

Build and run using Docker:

```bash
docker build -t callverse .
docker run --rm callverse
```

Or with Docker Compose:

```bash
docker compose run --rm cli
```

## Documentation

Detailed documentation is available in [`docs/`](file:///docs):
- [`docs/architecture.md`](file:///docs/architecture.md): System architecture, dependency boundaries, and BO/DSO mapping
- [`docs/data_dictionary.md`](file:///docs/data_dictionary.md): Schema specifications and entity definitions
- [`docs/experiments.md`](file:///docs/experiments.md): Evaluation experiments and benchmarking protocol
