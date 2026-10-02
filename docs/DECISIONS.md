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
| D11 | Pre-aggregations stored in the source Postgres (`cube_preagg` schema); no Cube Store container | Keeps the compose to the six services in the spec. |
| D12 | "attributed new customers" for CAC = converted responders (response led to a product) | Single clear definition; stated in the metric dictionary. |
