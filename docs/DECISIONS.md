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
| D10 | Gemini default model `gemini-3.5-flash` (stable per ai.google.dev/gemini-api/docs/models, checked 2026-10) | Looked up, not guessed; overridable via `GEMINI_MODEL`. |
| D11 | Pre-aggregations use `external: false` (stored in Postgres schema `prod_pre_aggregations`) with `CUBEJS_CACHE_AND_QUEUE_DRIVER=memory` and `CUBEJS_REFRESH_WORKER=true`; no Cube Store container | Keeps the compose to the services in the spec. Cube Store is the scale-out path for a real deployment (single-node demo only). |
| D12 | "attributed new customers" for CAC = converted responders (response led to a product) | Single clear definition; stated in the metric dictionary. |
| D13 | Default reference date pinned to 2026-09-30 (`REFERENCE_DATE`); `--reference-date last-full-month` is supported | Demo figures in docs/STORIES.md and docs/DEMO.md must stay exact; a floating default would invalidate them every month. |
| D14 | dbt pinned to dbt-core 1.10.23 + dbt-postgres 1.10.2 | dbt-core 1.12 fetches a Rust parser wheel from GitHub at install time, which fails on restricted networks. |
| D15 | `PIP_INDEX_URL` build arg (default pypi.org) | The dev machine could only reach a PyPI mirror; the override lives in the git-ignored `.env`. |
| D16 | Customer-level dimensions are the hashed `*_key` members; analyst is blocked from any member ending `_key`; there are no raw ids or PII columns anywhere in the marts' public members | Spec: "No PII dimensions are exposed; customer_id is hashed". |
