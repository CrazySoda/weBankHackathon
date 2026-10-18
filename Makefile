# ClearTrade — single entry point for running, testing and reproducing.
#
# Everything Python goes through uv (hash-locked uv.lock). `make help` lists
# all targets. Common flows:
#
#   make install        first-time setup
#   make gates          everything CI checks (lint + types + tests + coverage)
#   make eval           the metrics table (recall / false alarms / completion)
#   make up / down          the production-style docker stack
#   make up-dev / down-dev  the docker stack with Vite hot reload
#   make reset-demo     wipe all demo state and start clean

.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND := backend
WEB := web

# ----------------------------------------------------------- llm proxy ----
.PHONY: llm-key
llm-key: ## create a budget-capped LiteLLM virtual key and save it to .env
	uv run --directory $(BACKEND) python ../scripts/generate_litellm_key.py

# ---------------------------------------------------------------- setup ----
.PHONY: install
install: ## Install backend deps from uv.lock (hashed) + web deps
	uv sync --frozen --directory $(BACKEND)
	cd $(WEB) && npm install

# ---------------------------------------------------------------- checks ----
.PHONY: lint
lint: ## ruff check + format check
	uv run --directory $(BACKEND) ruff check app tests
	uv run --directory $(BACKEND) ruff format --check app tests

.PHONY: format
format: ## ruff auto-format + autofix
	uv run --directory $(BACKEND) ruff check app tests --fix
	uv run --directory $(BACKEND) ruff format app tests

.PHONY: typecheck
typecheck: ## mypy strict on calc/ harness/ graph/
	uv run --directory $(BACKEND) mypy

.PHONY: test
test: ## full offline test suite (unit + graph + api + security + channels)
	uv run --directory $(BACKEND) pytest tests -q

.PHONY: coverage
coverage: ## calc/ money math at enforced 100% branch coverage
	uv run --directory $(BACKEND) pytest tests/unit/calc -q \
		--cov=app.calc --cov-branch --cov-fail-under=100

.PHONY: test-integration
test-integration: ## Postgres-backed tests (needs TEST_DATABASE_URL or `make up`)
	uv run --directory $(BACKEND) pytest tests/integration -q

.PHONY: gates
gates: lint typecheck test coverage ## everything CI checks

# ----------------------------------------------------------------- evals ----
.PHONY: eval
eval: ## seed-suite metrics table (offline; deterministic)
	uv run --directory $(BACKEND) python -m tests.eval.run_eval

.PHONY: eval-live
eval-live: ## same, through the LiteLLM proxy (needs LITELLM_VIRTUAL_KEY)
	uv run --directory $(BACKEND) python -m tests.eval.run_eval --live

.PHONY: redteam
redteam: ## promptfoo red-team suite (needs proxy + LITELLM_VIRTUAL_KEY)
	cd evals/promptfoo && npx --yes promptfoo@latest eval --config promptfooconfig.yaml

# ------------------------------------------------------------------ data ----
.PHONY: seeds
seeds: ## regenerate the synthetic PDFs (byte-identical; verify with make seeds-verify)
	uv run --directory $(BACKEND) python -I seed/generate_seed_docs.py
	uv run --directory $(BACKEND) python -I seed/generate_seed_docs.py --poisoned

.PHONY: seeds-verify
seeds-verify: ## prove regeneration is byte-identical (diffs committed checksums)
	uv run --directory $(BACKEND) python -I seed/verify_checksums.py

# ------------------------------------------------------------------ proxy ----
.PHONY: render-config
render-config: ## render the LiteLLM config from env (LLM_PROVIDER / *_API_KEYS)
	LLM_API_KEYS="$${ANTHROPIC_API_KEYS:-$${OPENAI_API_KEYS:-$${GOOGLE_API_KEYS:-}}}" \
		uv run --directory $(BACKEND) python -m app.harness.litellm_render \
		> litellm/config.yaml
	@echo "wrote litellm/config.yaml (gitignored)"

.PHONY: proxy
proxy: ## start the LiteLLM proxy on the host via uv/uvx
	./scripts/start_proxy.sh

# ------------------------------------------------------------------ stack ----
.PHONY: up
up: ## start the full docker stack (backend :8000, web :5173, proxy :4000)
	docker compose up --build -d
	@echo "web console: http://localhost:5173 · api: http://localhost:8000/health"

.PHONY: up-dev
up-dev: ## start the stack with Vite hot reload for web source changes
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
	@echo "web console with hot reload: http://localhost:5173"

.PHONY: down
down: ## stop the stack (keeps volumes)
	docker compose down

.PHONY: down-dev
down-dev: ## stop the stack started with make up-dev (keeps volumes)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml down

.PHONY: logs
logs: ## tail backend + proxy logs
	docker compose logs -f backend litellm

.PHONY: logs-dev
logs-dev: ## follow web, backend and proxy logs from the hot-reload stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail=100 --timestamps -f web backend litellm

.PHONY: logs-web
logs-web: ## follow only frontend/Vite logs from the hot-reload stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml logs --tail=100 --timestamps -f web

.PHONY: status-dev
status-dev: ## show service status for the hot-reload stack
	docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

# ------------------------------------------------------------------ demo ----
.PHONY: reset-demo
reset-demo: ## wipe ALL demo state: containers+volumes, uploads, rendered config
	docker compose down -v 2>/dev/null || true
	rm -rf $(BACKEND)/data uploads litellm/config.yaml
	@echo "demo state cleared — 'make up' for a clean stack"

# ------------------------------------------------------------------- web ----
.PHONY: web-dev
web-dev: ## vite dev server for the review console
	cd $(WEB) && npm run dev

.PHONY: web-build
web-build: ## type-check + production build of the console
	cd $(WEB) && npm run build

# ------------------------------------------------------------------ clean ----
.PHONY: clean
clean: ## caches, test artifacts, rendered config (keeps seed data)
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache \
		$(BACKEND)/.hypothesis $(BACKEND)/.coverage litellm/config.yaml
	find $(BACKEND) -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

.PHONY: help
help: ## list all targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
