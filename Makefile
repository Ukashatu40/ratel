# Common developer commands. Run `make help`.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help venv install lint format typecheck test test-integration contract mock migrate-heads up down audit check

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-18s %s\n", $$1, $$2}'

venv: ## Create the virtualenv
	$(PY) -m venv $(VENV)

install: venv ## Install dev dependencies (pinned by requirements/constraints.txt)
	$(BIN)/pip install -r requirements/dev.txt -c requirements/constraints.txt

lint: ## Ruff lint and format check
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## Apply ruff formatting and safe fixes
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

typecheck: ## mypy (strict) over services/
	$(BIN)/mypy

test: ## Unit tests (no databases needed, lab tests excluded)
	$(BIN)/pytest

test-integration: ## Tests that need compose.dev.yaml services
	$(BIN)/pytest -m integration

contract: ## Validate openapi.yaml, check drift, run Schemathesis on implemented operations
	$(BIN)/pytest tests/contract
	BIN=$(BIN) scripts/ci/run_schemathesis.sh

mock: ## Serve contracts/openapi.yaml as a mock on http://127.0.0.1:4010
	npx --yes @stoplight/prism-cli@5 mock -h 127.0.0.1 -p 4010 contracts/openapi.yaml

migrate-heads: ## Show Alembic heads (offline, no database needed)
	$(BIN)/alembic -c services/app/alembic.ini heads

up: ## Start local PostgreSQL, Redis and MongoDB
	docker compose -f compose.dev.yaml up -d

down: ## Stop local dependencies
	docker compose -f compose.dev.yaml down

audit: ## Dependency vulnerability scan
	$(BIN)/pip-audit -r requirements/dev.txt

check: lint typecheck test contract ## Everything CI runs for Python
