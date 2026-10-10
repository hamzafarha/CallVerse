.PHONY: install lint import-lint test smoke

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check .

import-lint:
	lint-imports

test:
	pytest tests/

smoke:
	pytest tests/smoke/
