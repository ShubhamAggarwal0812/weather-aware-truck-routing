.DEFAULT_GOAL := help
API := cd apps/api &&
WEB := cd apps/web &&

.PHONY: help install dev dev-api dev-web test lint format typecheck schema check build up down

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install API (uv) and web (npm) dependencies
	$(API) uv sync
	$(WEB) npm ci

dev: ## Run the API on :8000 and the web app on :5173
	$(MAKE) -j2 dev-api dev-web

dev-api:
	$(API) uv run python manage.py runserver 8000

dev-web:
	$(WEB) npm run dev

test: ## Run every test suite
	$(API) uv run pytest
	$(WEB) npm test

lint: ## Lint and check formatting
	$(API) uv run ruff check . && uv run ruff format --check .
	$(WEB) npm run lint && npm run format:check

format: ## Auto-fix lint and formatting
	$(API) uv run ruff check --fix . && uv run ruff format .
	$(WEB) npm run format

typecheck: ## mypy + tsc
	$(API) uv run mypy .
	$(WEB) npm run typecheck

schema: ## Regenerate openapi.yaml and the TypeScript API types after API changes
	$(API) uv run python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
	$(WEB) npm run gen:api

check: lint typecheck test ## Everything CI runs

build: ## Production build of the web app
	$(WEB) npm run build

up: ## Full stack in Docker on http://localhost:8080
	docker compose up --build

down:
	docker compose down
