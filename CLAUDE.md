# CLAUDE.md

Governed Banking Analytics: synthetic bank data -> dbt marts -> Cube semantic layer -> MCP server -> LLM agent API -> Next.js UI.
Read `README.md` for the picture and `docs/DECISIONS.md` for why things are the way they are.

## Architecture (one line per service)

* `postgres` warehouse: schemas `raw`, `staging`, `marts`, `audit`.
* `dbt` (`/dbt`): staging views, mart tables (`fct_*`, `dim_*`; `dim_customer` is SCD Type 2), tests incl. GL reconciliation.
* `cube` (`/cube`): the **only** reader of `marts`. `model/cubes/*.yml` = metrics (title, description, `meta.owner/formula/time_semantics/unit`),
  `cube.js` = `queryRewrite` security (roles `cmo`, `branch_manager` + `branch_id` row filter, `analyst` blocked from `*_key` dims).
* `mcp-server` (`/mcp-server/app`): 5 read-only tools, validates names against the catalog (built from Cube `/meta`), collapses
  `period_end`/`average` metrics from month-grain rows, writes `audit.tool_calls`. stdio + streamable HTTP.
* `api` (`/api/app`): FastAPI. `agent.py` (tool loop, structured answer, guardrail), `providers/` (ONLY place with SDK-specific code),
  `gateway.py` (MCP client), `dashboard.py`, `main.py` (routes).
* `web` (`/web`): Next.js 16 + Tailwind 4 + Recharts. Pages: `/copilot`, `/dashboard`, `/trust`.

## Commands

```
make demo | up | seed | warmup | down        # stack lifecycle (see Makefile)
make test        # pytest: tests/{data,golden,mcp,api,eval}; integration tests need the stack up
make test-web    # Playwright against http://localhost:3000
make eval PROVIDER=gemini|anthropic          # needs an API key; oracle self-test: python tests/eval/run_eval.py --provider oracle
make lint        # ruff, mypy (api, mcp-server, scripts separately: both have a package called `app`), eslint, tsc
python scripts/generate_data.py [--scale 0.1]   # data/raw/*.csv (gitignored); python scripts/load_raw.py to load
python scripts/data_quality_report.py --write-docs   # regenerates docs/STORIES.md
python scripts/build_metric_dictionary.py            # regenerates docs/METRIC_DICTIONARY.md from cube/model
python tests/eval/build_eval_set.py                  # regenerates tests/eval/questions.yaml from the pandas reference
```

Host dev env: `py -3.13 -m venv .venv && pip install -r requirements-dev.txt`. On networks that block pypi.org set `PIP_INDEX_URL` in `.env`
(and `pip.ini` in the venv); `NPM_REGISTRY` likewise.

## Conventions and rules that must hold

* **Every number traces to a Cube metric.** No figures hardcoded in UI, prompts or answers. The UI only formats.
* **The LLM never writes SQL and never sees raw tables.** There is no SQL tool. Chat tables/provenance are built server-side from tool results.
* **No provider-specific code outside `api/app/providers/`** (a test enforces it). Provider swap = env vars only.
* Metric time semantics: `flow` (summed), `period_end` (last month end in range), `average` (mean of monthly values). Business date = posting date
  for transactions; snapshot cubes use month end. Segment/branch are as-of the business date (SCD2).
* New metric = edit `cube/model/cubes/*.yml` with full `meta`, add a golden test in `tests/golden/`, regenerate the dictionary.
* After changing data or marts: `make seed` (drops Cube rollups and rebuilds). Cube rollup refresh keys are data-driven, polled every 5 min.
* Python: type hints, ruff (line length 130), mypy clean, concise comments only where non-obvious. Web: eslint + tsc clean.
* Secrets only in `.env` (git-ignored); `.env.example` lists every variable.
* Shell tip for Claude sessions on this Windows machine: large multi-file heredocs in Bash can fail to parse; use the Write tool.

## Gotchas learned the hard way

* pandas 3 returns date columns in `us` units; always normalise with `d64()` in `generate_data.py` before `.astype(int)` day maths.
* Cube needs `external: false` on pre-aggregations and `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory` + `CUBEJS_REFRESH_WORKER=true` without Cube Store.
* MCP SDK is v2 (`MCPServer`, `Client`, `httpx2`); only `ToolError` subclasses surface their message to the model.
* React: an effect callback must not return a value (`scrollIntoView` returns a Promise in new Chromium).
