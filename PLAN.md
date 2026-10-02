# PLAN — Governed Banking Analytics

Question → `api` (LLM agent) → `mcp-server` → `cube` → Postgres `marts`. Dashboards use the same path.

## Phases (each ends with: tests pass → commit)

| # | Phase | Key files | Gate |
|---|-------|-----------|------|
| 0 | Scaffold, compose skeleton, env | `docker-compose.yml`, `.env.example`, `Makefile`, `CLAUDE.md` | `docker compose config` valid |
| 1 | Synthetic data | `scripts/generate_data.py`, `scripts/load_raw.py`, `scripts/data_quality_report.py`, `docs/STORIES.md`, `tests/data/` | counts, RI, story checks pass |
| 2 | dbt | `dbt/models/{staging,marts}`, `dbt/tests/` | `dbt build` green |
| 3 | Cube | `cube/model/*.yml`, `cube/cube.js`, `tests/golden/`, `docs/METRIC_DICTIONARY.md` | 12 golden metrics ±0.01%; branch token isolation; p95 < 1 s |
| 4 | MCP server | `mcp-server/app/*`, `tests/mcp/` | valid / invalid / role / audit tests |
| 5 | Agent API | `api/app/*`, `api/app/providers/*`, `tests/eval/` | unit tests; eval runner; Gemini ≥ 90 % (needs key) |
| 6 | Web UI | `web/` | build OK, Playwright smoke |
| 7 | Hardening | `docs/DEMO.md`, recon-break toggle, `make demo`, fallback screenshots | full e2e |

## Core design

* **Grain strategy.** Every Cube fact is a denormalised mart (branch, region, segment-as-of, product) so metric-by-dimension never needs fan-out joins. Joins to dimension cubes are declared for exploration.
* **Time semantics** are metric metadata (`meta.time_semantics`): `flow` (summed over the period), `period_end` (value at last month-end of the period), `average` (mean of month values). The MCP server executes `period_end`/`average` at month grain and collapses — rollup-friendly and exact.
* **Business date = posting_date** (value_date retained, not used for metrics).
* **Security**: JWT (`role`, `branch_id`) → Cube `queryRewrite` (row filter for branch_manager; analyst blocked from customer-level members). MCP passes the caller JWT to Cube unchanged.
* **Provider isolation**: all Gemini / Anthropic code lives in `api/app/providers/`.
* **Numbers**: LLM never computes; tool results carry `formatted` values; a post-check verifies every cited number.

## Risks

| Risk | Mitigation |
|------|-----------|
| No LLM keys on the dev machine | Provider logic unit-tested with a scripted fake; eval runner proven against an oracle provider; real pass rate reported honestly |
| 2M-row dbt + Cube performance | Postgres tuned in compose, indexes, Cube rollups at month/day grain |
| MCP SDK / google-genai API drift | Versions pinned after reading current docs; thin wrappers |
| SCD2 as-of joins slow | Indexed validity ranges; computed once in marts |
| Windows host | Everything runs in Docker; Makefile targets mirrored in `scripts/dev.ps1` |
