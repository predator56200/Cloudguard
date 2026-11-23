# =============================================================================
# CloudGuard AI — the developer interface
# =============================================================================
# Why: an engineer should memorise ~8 commands, not 8 tool invocations with 4 flags each.
# Every command in CI is ALSO a make target, so "green locally" and "green in CI" mean the
# same thing. When those two diverge, people stop trusting CI, and then CI is decoration.
#
# Windows: use `.\make.ps1 <target>` (same targets). See README.md.
# Roadmap: M0 task 0.12.
# =============================================================================

.PHONY: help dev down logs shell migrate migration test test-unit test-int lint fmt typecheck types seed clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Environment -----------------------------------------------------------
dev: ## Start the full local stack (postgres, redis, api, worker, web)
	docker compose up --build

down: ## Stop the stack (data volumes are preserved)
	docker compose down

clean: ## Stop the stack AND destroy all data. Nuclear option.
	docker compose down -v

logs: ## Tail all logs
	docker compose logs -f

shell: ## Open a shell inside the api container
	docker compose exec api /bin/bash

# --- Database --------------------------------------------------------------
migrate: ## Apply all pending migrations
	docker compose exec api alembic upgrade head

migration: ## Create a new migration:  make migration m="add findings table"
	docker compose exec api alembic revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration (test this — every migration must be reversible)
	docker compose exec api alembic downgrade -1

# --- Quality ---------------------------------------------------------------
lint: ## Lint everything (python + typescript)
	docker compose exec api ruff check .
	docker compose exec api black --check .
	cd apps/web && npm run lint

fmt: ## Auto-format everything
	docker compose exec api ruff check --fix .
	docker compose exec api black .
	cd apps/web && npm run format

typecheck: ## Static type checking (mypy --strict + tsc)
	docker compose exec api mypy packages/core apps/api
	cd apps/web && npm run typecheck

test: test-unit test-int ## Run all backend tests

test-unit: ## Fast tests: pure domain, no DB, no network (<5s — keep it that way)
	docker compose exec api pytest -m "not integration" -q

test-int: ## Integration tests: real Postgres + Redis
	docker compose exec api pytest -m integration -q

test-web: ## Frontend tests
	cd apps/web && npm run test

# --- Codegen ---------------------------------------------------------------
types: ## Regenerate packages/ts-types from the API's OpenAPI schema (M5)
	@echo "Not wired until M5 — the API has no domain endpoints yet."
