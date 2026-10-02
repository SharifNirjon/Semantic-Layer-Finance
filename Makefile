SHELL := /bin/bash
PY ?= python
PROVIDER ?= gemini
SCALE ?= 1.0
PSQL = docker compose exec -T postgres psql -U $${POSTGRES_USER:-bank} -d $${POSTGRES_DB:-warehouse}

.PHONY: help up seed warmup demo down test test-web lint eval screenshots recon-break recon-fix logs

help:
	@echo "make up          build and start every service (postgres, cube, mcp-server, api, web)"
	@echo "make seed        generate synthetic data, load it, run dbt build, rebuild Cube rollups"
	@echo "make demo        up + seed (first run) + warm-up, then print URLs and logins"
	@echo "make test        python tests (data, golden, security, MCP, agent, eval harness)"
	@echo "make test-web    Playwright demo-script tests against http://localhost:3000"
	@echo "make eval        LLM evaluation, PROVIDER=gemini|anthropic (needs the API key in .env)"
	@echo "make screenshots record fallback screenshots to docs/fallback/"
	@echo "make recon-break inject a GL discrepancy;  make recon-fix  removes it"
	@echo "make lint        ruff, mypy, eslint, tsc"

up:
	@test -f .env || cp .env.example .env
	docker compose up -d --build --wait

seed:
	@test -f .env || cp .env.example .env
	docker compose up -d postgres --wait
	SCALE=$(SCALE) docker compose --profile tools run --rm seed
	docker compose --profile tools run --rm dbt build
	-$(PSQL) -c "drop schema if exists prod_pre_aggregations cascade"
	-docker compose restart cube
	@$(MAKE) --no-print-directory warmup

warmup:
	$(PY) scripts/warmup.py

demo:
	@test -f .env || cp .env.example .env
	docker compose up -d postgres --wait
	@if [ "$$($(PSQL) -tAc "select to_regclass('marts.fct_transactions') is not null" 2>/dev/null)" != "t" ]; then $(MAKE) --no-print-directory seed; fi
	$(MAKE) --no-print-directory up
	@$(MAKE) --no-print-directory warmup
	@echo
	@echo "=============================================================="
	@echo " Governed Banking Analytics is ready"
	@echo "   Web (copilot, dashboard, trust center)  http://localhost:3000"
	@echo "   API docs                                http://localhost:8000/docs"
	@echo "   MCP server (streamable HTTP)            http://localhost:8765/mcp"
	@echo "   Cube playground-less REST API           http://localhost:4000"
	@echo " Demo logins (password demo123 for all; the UI role switcher logs in for you)"
	@echo "   cmo                   Chief Marketing Officer, all data"
	@echo "   branch_manager_dhaka  Narayanganj branch only"
	@echo "   analyst               aggregates only, no customer-level data"
	@echo " Chat needs GEMINI_API_KEY (or ANTHROPIC_API_KEY + LLM_PROVIDER=anthropic) in .env"
	@echo "=============================================================="

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

test:
	$(PY) -m pytest -q

test-web:
	cd web && npx playwright test

lint:
	$(PY) -m ruff check .
	cd api && $(PY) -m mypy app --config-file ../pyproject.toml
	cd mcp-server && $(PY) -m mypy app --config-file ../pyproject.toml
	$(PY) -m mypy scripts --config-file pyproject.toml
	cd web && npx tsc --noEmit && npx eslint .

eval:
	$(PY) tests/eval/run_eval.py --provider $(PROVIDER) --delay 5 --min-pass-rate 0.9

screenshots:
	mkdir -p docs/fallback
	cd web && CAPTURE=1 npx playwright test screenshots.spec.ts

recon-break:
	@TOKEN=$$($(PY) -c "import time,jwt;print(jwt.encode({'role':'cmo','sub':'cmo','exp':int(time.time())+600},'$${JWT_SECRET:-change-me-demo-secret-at-least-32-chars-long}',algorithm='HS256'))"); \
	curl -s -X POST localhost:8000/admin/recon-break -H "Authorization: Bearer $$TOKEN" -H 'content-type: application/json' -d '{"enabled":true,"delta_pct":0.35}'; echo

recon-fix:
	@TOKEN=$$($(PY) -c "import time,jwt;print(jwt.encode({'role':'cmo','sub':'cmo','exp':int(time.time())+600},'$${JWT_SECRET:-change-me-demo-secret-at-least-32-chars-long}',algorithm='HS256'))"); \
	curl -s -X POST localhost:8000/admin/recon-break -H "Authorization: Bearer $$TOKEN" -H 'content-type: application/json' -d '{"enabled":false}'; echo
