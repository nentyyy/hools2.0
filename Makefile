# Convenience targets. Everything works without them; they just save typing.
.PHONY: help install migrate backend bot frontend test lint docker-up docker-down

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install backend, bot and frontend dependencies
	cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pip install -e ../shared -e ../bot
	cd frontend && npm install

migrate: ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

backend: ## Run the API with reload
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

bot: ## Run the Telegram bot (polling)
	cd backend && .venv/bin/python -m gg_bot

frontend: ## Run the Mini App dev server
	cd frontend && npm run dev

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest

lint: ## Lint Python and type-check TypeScript
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npx tsc --noEmit

docker-up: ## Build and start the whole stack
	docker compose up -d --build

docker-down: ## Stop the stack
	docker compose down
