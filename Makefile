SIDECAR_PORT ?= 9000
AGENT_PORT ?= 8001

.PHONY: help db setup store seed dev snapshot reset test verify-audit style build clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

db: ## start postgres container for the store (evershop v2.2.1 is postgres, not mongo)
	@docker start rzp-postgres 2>/dev/null || docker run -d --name rzp-postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=evershop -e POSTGRES_DB=evershop -p 5432:5432 postgres:16

setup: ## idempotent install: store deps, python deps, .env
	@if [ ! -f store/config/local.json ]; then mkdir -p store/config && printf '{\n  "shop": { "language": "en", "timezone": "UTC", "currency": "INR", "weightUnit": "kg", "homeUrl": "http://localhost:8000" },\n  "system": { "file_storage": "local", "port": 8000, "session": { "cookieSecret": "dev-demo-secret" } },\n  "extensions": [{ "name": "session-shim", "resolve": "extensions/session-shim", "enabled": true }]\n}\n' > store/config/local.json; fi
	@cd store && npm install
	@if [ ! -d store/packages/evershop/dist ]; then cd store && npx tsc -p packages/evershop/tsconfig.json && npx copyfiles -u 1 "packages/evershop/src/**/*.{graphql,scss,css,json}" packages/evershop/dist; fi
	@uv sync
	@if [ ! -f .env ]; then cp .env.example .env && echo "created .env — fill in real test keys"; fi

store: ## build (if needed) + run store in prod mode on :8000 (fast; dev mode is per-page compile = slow)
	@if [ ! -f store/.evershop-built ]; then cd store && DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=evershop DB_NAME=evershop npm run build && touch .evershop-built; fi
	@cd store && DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=evershop DB_NAME=evershop PORT=8000 npm run start

seed: ## seed grocery catalog (re-runnable; needs postgres up; image-first: fetch_grocery_images.js first)
	@cd store && DB_HOST=localhost DB_PORT=5432 DB_USER=postgres DB_PASSWORD=evershop DB_NAME=evershop node ../scripts/seed_grocery.js

dev: ## run sidecar :9000 + agent backend :8001 concurrently
	@trap 'kill 0' EXIT; \
	uv run uvicorn sidecar.app:app --port $(SIDECAR_PORT) & \
	uv run uvicorn agent.app:app --port $(AGENT_PORT) & \
	wait

snapshot: ## catalog snapshot -> sidecar/snapshot.json (store must be up on :8000)
	@uv run python -m sidecar.snapshot

reset: ## re-seed grocery catalog + clear carts/audit/links between takes
	@rm -f audit.jsonl sidecar/links.json
	@$(MAKE) seed
	@echo "sidecar state cleared, grocery catalog re-seeded"

test: ## pytest + js smoke (cap, HMAC, hash-chain, poll, re-pricing, resume, 6 tools)
	@uv run pytest -q
	@node tests/test_webmcp_smoke.js

verify-audit: ## recompute hash chain: prev_hash = sha256(prev_line)
	@uv run python -m sidecar.core.audit

style: ## black + ruff (format + lint + import sort)
	@uv run black sidecar agent tests
	@uv run ruff check sidecar agent tests

build: ## no production build (spec §3: no deploy, localhost demo)
	@echo "no build step: demo is localhost only (spec §3)"

clean: ## remove artifacts, caches, audit.jsonl, links.json
	@rm -rf .pytest_cache .ruff_cache logs __pycache__ sidecar/__pycache__ sidecar/core/__pycache__ sidecar/utils/__pycache__ agent/__pycache__ agent/utils/__pycache__ tests/__pycache__ tests/sidecar/__pycache__ tests/agent/__pycache__
	@rm -f audit.jsonl sidecar/links.json
