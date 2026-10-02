# 10-minute demo script

Audience: the bank's CMO. Message: **every number has one governed definition, an owner, a formula and an audit trail,
and the AI can only speak with certified numbers.**

All figures below come from the fixed seed (42) and reference date 2026-09-30. If the copilot's numbers differ, the data
was regenerated with different settings (see `docs/STORIES.md` for the full set).

**Before you start:** `make demo`, open <http://localhost:3000>, sign in is automatic (CMO). Have `docs/CONFLICTING_REPORTS.md`
open in a second tab. The copilot needs `GEMINI_API_KEY` in `.env` (or `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`).
Run each suggested question once before the meeting: answers to the six chips are cached afterwards, so the live demo is
instant and immune to free-tier rate limits. No key or no network? Use the screenshots in `docs/fallback/`.

---

## 1. Two conflicting reports, one governed definition (1.5 min)

Open `docs/CONFLICTING_REPORTS.md`.

| Question | Marketing deck | Branch operations / Finance | Governed metric |
|---|---|---|---|
| Active customers | **31,443** (transacted in 30 days) | **43,200** (not churned) | **38,680** (transacted in 90 days to period end) |
| Young Professionals churn, Q3 2026 | **7.84%** (churned / customers at end) | **7.92%** (churned / customers at start) | **2.61%** a month (churned / sum of monthly opening customers) |

Say: "Nobody is wrong; they use different definitions. Here there is one." Then:

* **Trust center -> Metric dictionary**: search "active". Show the definition, owner (Head of Retail Banking), formula, source tables and caveats.
* **Executive dashboard**: the *Active customers* card shows **38,680** - hover for the definition.

## 2. Five CMO questions (4 min) - Copilot page

Click the suggestion chips (or type them). For each answer point to the **chart, table, Definition panel and "How this was
calculated"** (shows the exact Cube query and that figures were verified).

| # | Question | What you should see |
|---|---|---|
| 1 | *Why did Young Professionals churn rise last quarter?* | Young Professionals monthly churn **2.61%** in Q3 2026 vs **0.89%** in Q2 (**+1.72 pp, +193.5%**). Monthly: Apr 0.79%, May 0.97%, Jun 0.90%, **Jul 2.00%, Aug 2.64%, Sep 3.16%**. Other segments moved by 0.1 pp or less (SME 0.81%, Student 1.01%, Premium 0.38%, Retail 0.73%). Action: retention offer / early-warning outreach to the segment. |
| 2 | *Over the last 12 months, which branches saw their NPL ratio rise the most, and which sector is behind it?* | **Gazipur 4.44% -> 9.90% (+5.46 pp)** and **Narayanganj 5.29% -> 8.09% (+2.79 pp)** lead the increases. Sector: **RMG / Garments 4.65% -> 13.18% (+8.53 pp)**. Drill: RMG loans in Gazipur are **17.80%** NPL, in Narayanganj **15.14%**. Bank-wide NPL ratio is **3.10%**. Action: tighten RMG supply-chain exposure review in those two branches. |
| 3 | *Is our CASA ratio improving, and what is driving it?* | **No - it fell from 59.19% (Q4 2024) to 49.03% (Q3 2026)** while deposits grew from BDT 15.07 billion to BDT 29.21 billion. Driver: Fixed Deposits (BDT 13.94 billion of BDT 29.21 billion). Action: price/promote current and savings accounts to rebalance funding costs. |
| 4 | *Which campaign had the best cost per acquired customer, and which had high response but poor conversion?* | Best CAC: **Student Referral Rewards, BDT 2,055** (response 11.14%, conversion 37.44%). High response, poor conversion: **Eid Cashback Blast**, response **26.72%**, conversion **2.52%**, CAC **BDT 54,286** on BDT 1.90 million spend. |
| 5 | *How are mobile transactions trending against ATM transactions?* | Q4 2024: ATM **73,273** vs Mobile **49,218**. Q3 2026: Mobile **124,943** vs ATM **60,591**. Mobile overtook ATM in **Q3 2025** (July 2025 is the first month). |

Bonus chip: *What are our total deposits and CASA ratio for September 2026?* -> **BDT 29.21 billion**, **49.03%**.

Point out the live **steps** line above each answer (tool calls to the governed layer) and that the model never sees raw tables.

## 3. Switch role to Branch manager and re-ask (1.5 min)

Use the **Viewing as** switcher in the header: **Branch manager** (Narayanganj branch).

* Click **Ask again as Branch manager** under answer 2, or open the **Executive dashboard**: every card now shows only the
  branch - deposits **BDT 2.90 billion**, NPL **8.09%**, active customers **2,584**; the branch table has a single row.
  RMG / Garments NPL for the branch is **15.14%**.
* Ask: *Show me the total deposits of the Gulshan branch for September 2026.* -> declined; only the signed-in branch is available.
* Switch to **Analyst**: ask *List the top 10 customers by transaction value in Q3 2026.* -> declined (no customer-level data; no raw table access).

Say: "Security is enforced in the semantic layer, not in the prompt. The same token rules apply to the dashboard and to any MCP client."

## 4. Audit log (1 min) - Trust center -> Audit log

As the CMO: refresh and show rows for the chat questions, each `query_metrics` / `compare_periods` / `top_movers` call with
latency and row count; expand one to see the exact Cube query. Filter **Status = denied** (the analyst and branch-manager attempts).

## 5. Reconciliation (1 min) - Trust center -> Reconciliation

* Green tick: deposits and loans in the marts agree with the general ledger at every month end (deposit difference about -0.001%, tolerance 0.01%).
* Click **Demo: inject a GL discrepancy**: red cross, deposits **-0.35%** off the GL. (`make recon-break` does the same from the terminal.)
* Click **Demo: remove the discrepancy** to restore. The same check exists in dbt (`dbt test` fails while the break is injected).

## 6. Optional: an external MCP client on the same governed metrics (1 min)

Add the server from the README to Claude Desktop (or any MCP client) with a CMO token (`python scripts/make_token.py cmo`),
and ask *"What is our NPL ratio for September 2026?"* -> **3.10%**, with the same definition and the same audit trail
(the call appears in the Trust center).

---

### If something goes wrong

| Symptom | Fix |
|---|---|
| Chat input disabled, banner "AI model is not configured" | Set `GEMINI_API_KEY` in `.env`, `docker compose up -d api` |
| Gemini free tier "rate limited" | The API backs off and retries automatically; cached chips answer instantly; slow down or use screenshots |
| Dashboard slow on first load | `make warmup` (Cube builds its rollups once after seeding) |
| Numbers differ from this script | Data was regenerated with another scale/date: run `make seed` with defaults |
