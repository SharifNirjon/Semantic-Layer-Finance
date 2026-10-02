# Decisions & Deviations

| # | Decision | Why |
|---|----------|-----|
| D1 | Added raw tables `customer_attribute_history` and `loan_monthly_snapshots` | Spec needs SCD2 (needs history source) and NPL *trends* (needs loan state per month). |
| D2 | `raw.transactions` carries `customer_id` | Core banking joins account→customer anyway; avoids a 2M-row join in staging. |
| D3 | Credit cards are `Loan`-category products with a `raw.loans` row | Keeps loans_outstanding == GL loans and one NPL population. |
| D4 | `churn_rate` = churned in period ÷ sum of monthly opening customers (monthly-average churn) | Exactly the spec for a single month; additive and rollup-safe for longer periods. Documented in metric meta. |
| D5 | `nim` = NII ÷ Σ monthly average loan balances × 12 | Annualised for any period length without counting months. Earning assets = loan book. |
| D6 | Point-in-time metrics (`period_end`, `average`) collapsed in MCP from Cube month-grain rows, driven by metric metadata | Cube cannot express range-relative "last value". |
| D7 | Branch/role security via Cube `queryRewrite` (JS `cube.js`), not data-access policies | Gives explicit, testable error messages and works with rollups; policies are the alternative. |
| D8 | Chat `tables` and `provenance` are assembled server-side from tool results; the LLM supplies narrative, chart spec and follow-ups | Prevents hallucinated cells; satisfies "every number traces to a Cube metric". |
| D9 | Dashboards call the MCP query tool (as an MCP client) | One execution path for chat and charts. |
| D10 | Gemini default model `gemini-3.6-flash`, fallback `gemini-3.1-flash-lite` | Measured 2026-10-02: `gemini-3.5-flash` took 50 s+ per call with 503 "high demand" errors; 3.6-flash answered tool calls in ~3 s and 3.1-flash-lite in ~1 s with no errors. Retries alternate main and fallback; overridable via `GEMINI_MODEL` / `GEMINI_FALLBACK_MODEL`. |
| D11 | Pre-aggregations use `external: false` (stored in Postgres schema `prod_pre_aggregations`) with `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory` and `CUBEJS_REFRESH_WORKER=true`; no Cube Store container | Keeps the compose to the services in the spec. Cube Store is the scale-out path for a real deployment (single-node demo only). |
| D12 | "attributed new customers" for CAC = converted responders (response led to a product) | Single clear definition; stated in the metric dictionary. |
| D13 | Default reference date pinned to 2026-09-30 (`REFERENCE_DATE`); `--reference-date last-full-month` is supported | Demo figures in docs/STORIES.md and docs/DEMO.md must stay exact; a floating default would invalidate them every month. |
| D14 | dbt pinned to dbt-core 1.10.23 + dbt-postgres 1.10.2 | dbt-core 1.12 fetches a Rust parser wheel from GitHub at install time, which fails on restricted networks. |
| D15 | `PIP_INDEX_URL` build arg (default pypi.org) | The dev machine could only reach a PyPI mirror; the override lives in the git-ignored `.env`. |
| D16 | Customer-level dimensions are the hashed `*_key` members; analyst is blocked from any member ending `_key`; there are no raw ids or PII columns anywhere in the marts' public members | Spec: "No PII dimensions are exposed; customer_id is hashed". |
| D17 | Anthropic default model `claude-opus-5-5` (from the Claude API reference); native structured output via `output_config.format`, no sampling parameters, no forced `tool_choice` | These constraints are mandatory on the current Claude 5.x models. |
| D18 | Chat answer = tool loop, then a separate tool-less structured-output call (JSON schema), then the number guardrail | Gemini and Claude both handle "tools" and "structured JSON" better as separate calls; also lets the retry feed back the exact problem. |
| D19 | Cached answers only for the six fixed demo questions, keyed by provider, model, role and branch | A branch manager must never be served a CMO answer; free-tier quotas stay safe. |
| D20 | `tests/eval` includes an `oracle` provider (scripted tool calls) used only to self-test the harness; it reports 25/25 by construction and says nothing about model quality | No LLM key was available while building; the real score needs `make eval`. |
| D21 | Playwright chat tests replay a recorded real agent run (`web/e2e/fixtures/chat-events.json`) instead of calling an LLM | CI has no key; the recording comes from the live MCP + Cube pipeline, so the UI is exercised with real structures. |
| D22 | Trend questions steer to 12-month windows (system prompt; the NPL demo question) | Branch-level NPL is lumpy over single quarters (small books); a 12-month window surfaces the planted story reliably. |
| D23 | Demo user `branch_manager_dhaka` is the manager of the Narayanganj branch (Dhaka region) | Makes planted story b visible in the branch-manager view. |
| D24 | Quarterly/period "churn rate" is a monthly-equivalent rate (see D4); the conflicting-reports page contrasts it with quarterly end/start-of-period variants | One comparable unit across months, quarters and years. |
