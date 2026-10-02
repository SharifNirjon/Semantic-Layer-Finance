"""Governed-metrics MCP server. Read-only: there is no raw-SQL tool and no write tool.

Transports: stdio (token from MCP_JWT) and streamable HTTP (token from the Authorization header).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp_types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from .audit import AuditLog
from .auth import Caller, caller_from_token
from .catalog import Catalog, Metric
from .config import Settings
from .cube_client import CubeClient
from .engine import DateRange, Engine, Filter, Granularity, OrderBy, Result
from .errors import AccessDenied, ToolInputError

SETTINGS = Settings.from_env()
ENGINE = Engine(CubeClient(SETTINGS.cube_url), SETTINGS.max_rows)
AUDIT = AuditLog(SETTINGS.pg_dsn)
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

mcp = MCPServer(
    "governed-banking-metrics",
    instructions=(
        "Governed banking analytics. Every figure comes from a certified metric definition in the semantic layer; "
        "there is no raw SQL access. Start with list_catalog, then use query_metrics, compare_periods or top_movers. "
        "Quote numbers exactly as returned (use display_rows) and state the period and filters."
    ),
)

DEFINITIONS_NOTE = ("Business date is posting date for transactions; snapshot metrics use month end. Segment and branch "
                    "are as of the business date.")


def metric_definition(m: Metric) -> dict[str, Any]:
    return {"name": m.name, "title": m.title, "definition": m.formula, "description": m.description, "owner": m.owner,
            "unit": m.unit, "time_semantics": m.time_semantics, "source_tables": m.source_tables,
            "caveats": m.caveats or None}


def provenance(caller: Caller, metrics: list[Metric], cube_queries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"metrics": [metric_definition(m) for m in metrics], "cube_queries": cube_queries,
            "executed_as": {"role": caller.role, "branch_id": caller.branch_id}, "note": DEFINITIONS_NOTE}


def result_payload(caller: Caller, res: Result) -> dict[str, Any]:
    return {"columns": res.columns, "rows": res.rows, "display_rows": res.display_rows, "row_count": len(res.rows),
            "total_rows": res.total_rows, "truncated": res.truncated, "notes": res.notes,
            "provenance": provenance(caller, res.metrics, res.cube_queries)}


def _token(ctx: Context) -> str | None:
    headers = ctx.headers
    if headers is not None and headers.get("authorization"):
        return headers["authorization"]
    return SETTINGS.stdio_token


async def audited(tool: str, ctx: Context, args: dict[str, Any],
                  run: Callable[[Caller], Awaitable[tuple[dict[str, Any], list[dict[str, Any]], int]]]) -> dict[str, Any]:
    """Authenticate, run, and write exactly one audit row whatever the outcome."""
    started = time.perf_counter()
    caller: Caller | None = None
    status, error, cube_queries, rows = "ok", None, None, None
    try:
        caller = caller_from_token(_token(ctx), SETTINGS.jwt_secret)
        payload, cube_queries, rows = await run(caller)
        return payload
    except AccessDenied as exc:
        status, error = "denied", str(exc)
        raise
    except (ToolInputError, TimeoutError) as exc:
        status, error = "error", str(exc)
        raise
    finally:
        await AUDIT.record(user=caller.user if caller else "anonymous", role=caller.role if caller else "none",
                           tool=tool, args=args, cube_queries=cube_queries, row_count=rows,
                           latency_ms=int((time.perf_counter() - started) * 1000), status=status, error=error)


async def _catalog_for(caller: Caller) -> Catalog:
    return await ENGINE.catalog(caller.token)


@mcp.tool(annotations=READ_ONLY)
async def list_catalog(ctx: Context) -> dict[str, Any]:
    """List every certified metric and dimension you may query, with short definitions and valid dimension values.

    Call this first. Metrics are grouped by the data they come from; a metric can only be broken down by the
    dimensions listed in its group. Dimension values (e.g. segment names, branch names) are the exact strings
    accepted by query_metrics filters. Results depend on the caller's role.
    """
    async def run(caller: Caller) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        cat = await _catalog_for(caller)
        metrics = cat.visible_metrics(caller.role)
        dims = cat.visible_dimensions(caller.role)
        values = await asyncio.gather(*(
            ENGINE.dimension_values(caller, cat, d.name) for d in dims if not d.customer_level))
        by_dim = {d.name: v for d, v in zip((d for d in dims if not d.customer_level), values, strict=True)}
        rng = await ENGINE.data_range(caller)
        groups: dict[str, list[Metric]] = {}
        for m in metrics:
            groups.setdefault(m.cube, []).append(m)
        payload = {
            "data_available": {"from": str(rng[0]), "to": str(rng[1])} if rng else None,
            "conventions": [DEFINITIONS_NOTE,
                            "time_semantics: flow = summed over the period; period_end = value at the last month end "
                            "of the period; average = mean of monthly values.",
                            "Month-grain metrics widen date ranges to whole months; daily granularity is only "
                            "available for transaction metrics."],
            "granularities": ["day", "month", "quarter", "year"],
            "metric_groups": [{
                "metrics": [{"name": m.name, "title": m.title, "definition": m.formula, "unit": m.unit,
                             "time_semantics": m.time_semantics, "owner": m.owner, "caveats": m.caveats or None,
                             "source_tables": m.source_tables} for m in ms],
                "dimensions": sorted(cat.cube_dims[cube] - {d.name for d in cat.dimensions.values() if d.customer_level}
                                     | ({d.name for d in dims if d.customer_level and cube in d.members})),
            } for cube, ms in groups.items()],
            "dimensions": [{"name": d.name, "description": d.description, "customer_level": d.customer_level,
                            "values": by_dim.get(d.name) if len(by_dim.get(d.name, [])) <= 40 else None}
                           for d in dims],
        }
        return payload, [], len(metrics)

    return await audited("list_catalog", ctx, {}, run)


@mcp.tool(annotations=READ_ONLY)
async def describe_metric(
    name: Annotated[str, Field(description="Metric name from list_catalog, e.g. 'npl_ratio'.")], ctx: Context,
) -> dict[str, Any]:
    """Explain one metric: plain-English formula, owner, grain, caveats, source tables and breakdown dimensions.

    Use this to show the user the exact definition behind a number, or to resolve ambiguity between similar metrics.
    """
    async def run(caller: Caller) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        cat = await _catalog_for(caller)
        m = cat.metric(name, caller.role)
        sem = {"flow": "summed over the selected period", "period_end": "value at the last month end of the period",
               "average": "mean of the monthly values in the period"}[m.time_semantics]
        dims = sorted(d for d in cat.cube_dims[m.cube]
                      if not (caller.role == "analyst" and cat.dimensions[d].customer_level))
        payload = {**metric_definition(m), "grain": f"{m.grain} (business date convention: {DEFINITIONS_NOTE})",
                   "time_semantics_meaning": sem, "available_dimensions": dims,
                   "example_call": {"tool": "query_metrics", "arguments": {
                       "metrics": [m.name], "dimensions": dims[:1],
                       "date_range": {"start": "2026-07-01", "end": "2026-09-30"}}}}
        return payload, [], 1

    return await audited("describe_metric", ctx, {"name": name}, run)


@mcp.tool(annotations=READ_ONLY)
async def query_metrics(
    metrics: Annotated[list[str], Field(min_length=1, max_length=6, description="Metric names from list_catalog.")],
    date_range: Annotated[DateRange, Field(description="Reporting period (inclusive). Month-grain metrics are "
                                                       "widened to whole months.")],
    ctx: Context,
    dimensions: Annotated[list[str] | None, Field(description="Dimension names to group by, e.g. ['segment'] or "
                                                              "['branch']. Each must be valid for every metric.")] = None,
    granularity: Annotated[Granularity | None, Field(description="Add a time axis: 'month', 'quarter', 'year' or "
                                                                 "'day' (transactions only). Omit for a single total "
                                                                 "over the period.")] = None,
    filters: Annotated[list[Filter] | None, Field(description="Restrict rows, e.g. segment equals "
                                                              "['Young Professionals'].")] = None,
    order_by: Annotated[list[OrderBy] | None, Field(description="Sort; defaults to period then the first metric "
                                                                "descending.")] = None,
    limit: Annotated[int, Field(ge=1, le=200, description="Maximum rows returned (1-200).")] = 50,
) -> dict[str, Any]:
    """Query certified metrics, optionally broken down by dimensions and over time.

    Returns rows (raw numbers), display_rows (formatted strings: quote these), notes on how the period was applied
    (e.g. a period-end metric over a quarter reports the last month end), the metric definitions and the exact semantic
    layer query executed. All figures come from governed definitions; no ad-hoc calculations are possible.
    Metrics and dimensions are validated against the catalog and the caller's role.
    """
    args = {"metrics": metrics, "dimensions": dimensions, "date_range": date_range.model_dump(mode="json"),
            "granularity": granularity, "filters": [f.model_dump() for f in filters or []],
            "order_by": [o.model_dump() for o in order_by or []], "limit": limit}

    async def run(caller: Caller) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        res = await ENGINE.query(caller, metrics, date_range, dimensions, granularity, filters, order_by, limit)
        return result_payload(caller, res), res.cube_queries, len(res.rows)

    return await audited("query_metrics", ctx, args, run)


@mcp.tool(annotations=READ_ONLY)
async def compare_periods(
    metric: Annotated[str, Field(description="One metric name from list_catalog.")],
    period_a: Annotated[DateRange, Field(description="Baseline period.")],
    period_b: Annotated[DateRange, Field(description="Comparison period.")],
    ctx: Context,
    dimensions: Annotated[list[str] | None, Field(description="Optional dimensions to compare within.")] = None,
    filters: Annotated[list[Filter] | None, Field(description="Optional row restrictions.")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    """Compare one metric between two periods: absolute change and percentage change (period_b minus period_a).

    Percent-unit metrics (churn rate, NPL ratio...) report absolute change in percentage points plus the relative
    change. Use for questions like 'how did X change versus last quarter'. Rows are sorted by size of change.
    """
    args = {"metric": metric, "period_a": period_a.model_dump(mode="json"), "period_b": period_b.model_dump(mode="json"),
            "dimensions": dimensions, "filters": [f.model_dump() for f in filters or []], "limit": limit}

    async def run(caller: Caller) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        res = await ENGINE.compare(caller, metric, period_a, period_b, dimensions, filters, limit)
        metrics = res.pop("metrics_used")
        res["provenance"] = provenance(caller, metrics, res.pop("cube_queries"))
        return res, res["provenance"]["cube_queries"], len(res["rows"])

    return await audited("compare_periods", ctx, args, run)


@mcp.tool(annotations=READ_ONLY)
async def top_movers(
    metric: Annotated[str, Field(description="One metric name from list_catalog.")],
    dimension: Annotated[str, Field(description="Dimension whose values are ranked, e.g. 'branch' or 'segment'.")],
    period: Annotated[DateRange, Field(description="Period of interest; it is compared with the immediately "
                                                   "preceding period of the same length.")],
    ctx: Context,
    top_n: Annotated[int, Field(ge=1, le=20)] = 5,
    rank_by: Annotated[str, Field(pattern="^(absolute|percent)$",
                                  description="'absolute' ranks by size of change, 'percent' by relative change.")] = "absolute",
    filters: Annotated[list[Filter] | None, Field(description="Optional row restrictions.")] = None,
) -> dict[str, Any]:
    """Find which values of a dimension moved the most: biggest increases and biggest decreases of a metric.

    Compares `period` with the preceding period of equal length and returns the top_n positive and negative movers.
    Use for 'what is driving the change' and 'which branches/segments got worse' questions.
    """
    args = {"metric": metric, "dimension": dimension, "period": period.model_dump(mode="json"), "top_n": top_n,
            "rank_by": rank_by, "filters": [f.model_dump() for f in filters or []]}

    async def run(caller: Caller) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        res = await ENGINE.top_movers(caller, metric, dimension, period, top_n, rank_by,  # type: ignore[arg-type]
                                      filters)
        metrics = res.pop("metrics_used")
        res["provenance"] = provenance(caller, metrics, res.pop("cube_queries"))
        return res, res["provenance"]["cube_queries"], res["total_rows"]

    return await audited("top_movers", ctx, args, run)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def main() -> None:
    if SETTINGS.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=SETTINGS.host, port=SETTINGS.port, stateless_http=True, json_response=True)


if __name__ == "__main__":
    main()
