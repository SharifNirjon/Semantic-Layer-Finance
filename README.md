# Governed Banking Analytics

A demo-ready system for a bank's CMO: **one governed definition for every number**, a semantic layer over a synthetic
Bangladesh retail/SME bank, an MCP server, an LLM copilot that can only quote certified metrics, an executive dashboard
and a trust center (audit log, GL reconciliation, metric dictionary).

> All data is synthetic, generated with a fixed seed. Nothing here touches real customer data.

```mermaid
flowchart LR
    U[Browser<br/>Next.js UI] -->|SSE chat / REST + JWT| API
    subgraph api["api (FastAPI)"]
        API[Agent loop<br/>guardrail, cache] --> P{{LLMProvider}}
        P --> G[GeminiProvider<br/>default]
        P --> A[AnthropicProvider<br/>env switch]
    end
    API -->|MCP client, caller's JWT| MCP[mcp-server<br/>5 read-only tools]
    X[External MCP client<br/>Claude Desktop, etc.] -->|stdio or HTTP + JWT| MCP
    MCP -->|REST + JWT| CUBE[Cube Core<br/>semantic layer<br/>roles, row security, rollups]
    CUBE -->|only reader of marts| PG[(Postgres<br/>raw, staging, marts, audit)]
    DBT[dbt<br/>staging, marts, tests] --> PG
    MCP -. audit.tool_calls .-> PG
```

Data flow: question -> `api` (LLM agent) -> `mcp-server` -> Cube -> Postgres marts. Dashboards call the same MCP tools, so
charts and chat always agree. The LLM never writes SQL and never receives raw table access.

## Run it (about 10 minutes, mostly Docker pulls)

Requirements: Docker Desktop (4 GB+ RAM for the VM), Python 3.13 and Node 24 for the host-side tests/warm-up, `make`.

```bash
cp .env.example .env            # add GEMINI_API_KEY (free tier works) or ANTHROPIC_API_KEY + LLM_PROVIDER=anthropic
pip install -r requirements-dev.txt
make demo                       # first run: build, generate + load data, dbt build, build Cube rollups, print URLs
```

No `make` (Windows)? The targets are thin wrappers; run the commands in the Makefile by hand, e.g.
`docker compose up -d postgres --wait`, `docker compose --profile tools run --rm seed`,
`docker compose --profile tools run --rm dbt build`, `docker compose up -d --build`, `python scripts/warmup.py`.

| URL | What |
|---|---|
| <http://localhost:3000> | Copilot, Executive dashboard, Trust center |
| <http://localhost:8000/docs> | API (OpenAPI) |
| <http://localhost:8765/mcp> | MCP server (streamable HTTP) |
| <http://localhost:4000> | Cube REST API (JWT required) |

Demo logins (password `demo123`; the header role switcher signs in for you): `cmo` (everything), `branch_manager_dhaka`
(Narayanganj branch only), `analyst` (aggregates only, no customer-level dimensions).

Other targets: `make test`, `make test-web`, `make eval PROVIDER=gemini`, `make screenshots`, `make recon-break` /
`make recon-fix`, `make lint`. The 10-minute presentation is in [docs/DEMO.md](docs/DEMO.md).

## Deploy to a VPS (live URL with HTTPS)

Tested layout for one Ubuntu/Debian server with 4 GB+ RAM (e.g. a Hostinger KVM VPS):

1. Point a domain or subdomain at the server (DNS `A` record) and open ports 80 and 443.
2. On the server: `git clone <this repo> && cd Semantic-Layer-Finance && sudo ./deploy/deploy.sh analytics.example.com`
3. It asks for the Gemini API key and a site login, installs Docker if needed, seeds the warehouse on the first run,
   and starts everything. Re-run it to deploy new commits after `git pull`.
4. Optional, automatic deploys: every push to `main` redeploys via `.github/workflows/deploy.yml`. Once:
   `ssh-keygen -t ed25519 -f gh_deploy -N ""`, append `gh_deploy.pub` to the server's `~/.ssh/authorized_keys`, then add
   repo secrets `VPS_HOST` (server IP) and `VPS_SSH_KEY` (contents of `gh_deploy`). Set `VPS_APP_DIR` if the repo is not in
   `/root/Semantic-Layer-Finance`. Runs show under the Actions tab; "Run workflow" deploys on demand.

Caddy is the only public service: it serves the UI and the API on one origin (`/api` is proxied to the API), gets the
TLS certificate automatically, and puts a password in front of the site so strangers cannot spend the LLM quota.
Postgres, Cube, the MCP server and the API bind to `127.0.0.1` only. See `deploy/`.

## Switching the LLM provider

Set `LLM_PROVIDER=gemini|anthropic` plus the matching `*_API_KEY` / `*_MODEL` in `.env` and restart the `api` service.
Nothing else changes: all provider-specific code lives in `api/app/providers/`; the MCP server, Cube model and UI are
provider-neutral. Model names are not hard-coded in logic (defaults: `gemini-3.5-flash`, `claude-opus-5-5`).

## Connect an external MCP client

Create a token for the role you want (add `--branch 7` for a branch manager):

```bash
python scripts/make_token.py cmo
```

**Claude Desktop, remote HTTP** (via the `mcp-remote` bridge; works with any client that speaks stdio):

```json
{
  "mcpServers": {
    "governed-banking": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8765/mcp", "--header", "Authorization: Bearer <TOKEN>"]
    }
  }
}
```

**Claude Desktop, local stdio** (the server reads the token from `MCP_JWT`):

```json
{
  "mcpServers": {
    "governed-banking": {
      "command": "python",
      "args": ["-m", "app"],
      "env": {
        "PYTHONPATH": "/abs/path/to/repo/mcp-server",
        "MCP_TRANSPORT": "stdio",
        "MCP_JWT": "<TOKEN>",
        "JWT_SECRET": "<same as .env>",
        "CUBE_URL": "http://localhost:4000",
        "POSTGRES_HOST": "localhost"
      }
    }
  }
}
```

Any MCP-capable client with a streamable-HTTP transport can connect directly to `http://localhost:8765/mcp` with an
`Authorization: Bearer <TOKEN>` header. Tools: `list_catalog`, `describe_metric`, `query_metrics`, `compare_periods`,
`top_movers` (all read-only; there is no SQL tool). Every call, allowed or denied, is written to `audit.tool_calls` and shows up in
the Trust center.

## What is in the box

| Folder | Purpose |
|---|---|
| `scripts/` | Synthetic data generator (seed 42), loader, data-quality and story checks, warm-up, token helper |
| `dbt/` | staging -> marts (SCD Type 2 on customer segment and branch), tests incl. GL reconciliation |
| `cube/` | Semantic layer: cubes, metric definitions with owner/formula, JWT roles, pre-aggregations |
| `mcp-server/` | Governed MCP server: validation, role pass-through, audit |
| `api/` | FastAPI agent, provider adapters, guardrail, dashboards, audit and reconciliation endpoints |
| `web/` | Next.js UI and Playwright demo-script tests |
| `tests/` | Data, golden (pandas vs Cube), security, MCP, agent and eval tests |
| `docs/` | `STORIES.md`, `METRIC_DICTIONARY.md`, `DEMO.md`, `DECISIONS.md`, fallback screenshots |

## How this connects to a real bank

* **Read-only warehouse connection.** Cube is the only component with warehouse credentials, and it needs `SELECT` on the
  curated marts (plus a scratch schema if you keep rollups in the source database). Point `CUBEJS_DB_*` at a read replica or
  warehouse (Snowflake, BigQuery, Postgres, Oracle...) - the model files stay the same apart from table names.
* **No data movement.** Nothing is copied into the demo stack; dbt models run where the warehouse already is. In production Cube Store
  (rollups) replaces the in-memory driver used here for the single-node demo.
* **On-prem option.** Every component is a container with no SaaS dependency except the LLM. Run the whole stack inside the
  bank's network and use a self-hosted or private-endpoint model behind the `LLMProvider` interface (one new adapter in
  `api/app/providers/`). Without any LLM, dashboards, MCP and the audit trail still work.
* **Identity.** Replace the demo `/login` with the bank's SSO/OIDC: Cube and the MCP server only need a signed JWT carrying
  `role` and (for branch managers) `branch_id`; point Cube at the IdP's JWKS instead of a shared secret.
* **Governance.** Metric definitions live in code review (`cube/model`), carry an owner, and generate the dictionary; the audit
  table records who asked what and which query ran; reconciliation to the GL is a first-class check.

## Known limitations

See [docs/DECISIONS.md](docs/DECISIONS.md) for the full list of deviations. Highlights: demo auth uses fixed passwords and a
shared HS256 secret; the NLP quality figure depends on the LLM you configure (run `make eval`); rollups live in Postgres and
Cube uses its in-memory queue (single node).
