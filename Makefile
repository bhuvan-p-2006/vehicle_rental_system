# Vehicle Rental System — developer task runner (SPEC §13.4)
#
# Every target is a thin wrapper around `uv run` (backend) or `npm` (frontend).
# Docs should point here rather than duplicating command lines.
#
# Backend commands `cd` into ./backend first: ruff, mypy and pytest each discover
# their configuration from the working directory, so running them from the repo
# root would silently ignore backend/pyproject.toml.

BACKEND  := backend
FRONTEND := frontend
COMPOSE  := docker compose

# Run a command inside the backend project environment.
UVRUN := cd $(BACKEND) && uv run

.DEFAULT_GOAL := help
.PHONY: help install env-bootstrap doctor dev up down logs ps restart shell \
        migrate migration downgrade seed reset-db \
        test test-cov lint format typecheck check \
        frontend-install frontend-dev frontend-build \
        clean

## ---------------------------------------------------------------- help ----
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

## --------------------------------------------------------- environment ----
doctor: ## Verify prerequisites are installed
	@command -v uv     >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/"; exit 1; }
	@command -v docker >/dev/null || { echo "docker not found"; exit 1; }
	@command -v node  >/dev/null || { echo "node not found"; exit 1; }
	@echo "uv      $$(uv --version)"
	@echo "node    $$(node --version)"
	@echo "docker  $$(docker --version)"

install: ## Sync backend deps (from uv.lock) and install frontend deps
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm install
	@$(MAKE) --no-print-directory env-bootstrap

env-bootstrap: ## Create backend/.env from the example (host-side config)
	@if [ -f $(BACKEND)/.env ]; then \
		echo "backend/.env already exists; leaving it alone"; \
	else \
		cp $(BACKEND)/.env.example $(BACKEND)/.env; \
		echo "created backend/.env from .env.example"; \
	fi

## ------------------------------------------------------------- stack -----
up: ## Build and start the full stack
	$(COMPOSE) up --build -d
	@echo "frontend  http://localhost:30"
	@echo "api       http://localhost:8000/health"
	@echo "minio     http://localhost:9001  (minioadmin/minioadmin)"

down: ## Stop the stack
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Tail container logs
	$(COMPOSE) logs -f --tail=100

ps: ## Show container status
	$(COMPOSE) ps

shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend /bin/bash

frontend-dev: ## Run the Vite dev server locally
	cd $(FRONTEND) && npm run dev

frontend-build: ## Type-check and build the frontend
	cd $(FRONTEND) && npm run build

frontend-install: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

## --------------------------------------------------------- backend run ----
dev: ## Run the API locally with auto-reload (needs db + minio running)
	$(UVRUN) uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## --------------------------------------------------------- migrations ----
migrate: ## Apply all migrations
	$(UVRUN) alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add foo"
	$(UVRUN) alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	$(UVRUN) alembic downgrade -1

seed: ## Insert demo users and vehicles
	$(UVRUN) python -m app.seed

reset-db: ## Drop and recreate the schema, then seed (destructive)
	$(UVRUN) alembic downgrade base
	$(UVRUN) alembic upgrade head
	$(UVRUN) python -m app.seed

## ------------------------------------------------------------ quality ----
test: ## Run the backend test suite
	$(UVRUN) pytest

test-cov: ## Run tests with a coverage report
	$(UVRUN) pytest --cov=app --cov-report=term-missing

lint: ## Lint with ruff
	$(UVRUN) ruff check .

format: ## Format with ruff
	$(UVRUN) ruff format .
	$(UVRUN) ruff check --fix .

typecheck: ## Type-check with mypy
	$(UVRUN) mypy app

check: ## Run every quality gate
	@echo "== lint =="   && $(UVRUN) ruff check .
	@echo "== format ==" && $(UVRUN) ruff format --check .
	@echo "== types =="  && $(UVRUN) mypy app
	@echo "== tests =="  && $(UVRUN) pytest

## -------------------------------------------------------------- misc -----
clean: ## Remove caches and build artifacts
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(BACKEND)/.mypy_cache
	rm -rf $(BACKEND)/.coverage htmlcov $(FRONTEND)/dist
	find $(BACKEND) -name '__pycache__' -type d -prune -exec rm -rf {} +