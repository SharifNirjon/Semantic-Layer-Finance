"""Turn raw tool results into: the compact view the LLM sees, tables for people, and chart payloads."""

from __future__ import annotations

import json
from typing import Any

from .gateway import ToolRecord
from .models import ChartPayload, ChartSpec, Provenance, Table

QUERY_TOOLS = {"query_metrics", "compare_periods", "top_movers"}


def _defs(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"name": m["name"], "definition": m["definition"], "unit": m["unit"],
             "time_semantics": m["time_semantics"]} for m in result.get("provenance", {}).get("metrics", [])]


def llm_view(rec: ToolRecord) -> dict[str, Any]:
    """Compact, number-formatted view. Raw floats are deliberately left out so the model quotes display values."""
    base: dict[str, Any] = {"call_id": rec.call_id, "tool": rec.name, "arguments": rec.arguments}
    if rec.error:
        return {**base, "error": rec.error}
    r = rec.result or {}
    if rec.name == "query_metrics":
        return {**base, "columns": r["columns"], "display_rows": r["display_rows"], "notes": r["notes"],
                "truncated": r["truncated"], "total_rows": r["total_rows"], "metric_definitions": _defs(r)}
    if rec.name == "compare_periods":
        return {**base, "display_rows": r["display_rows"], "change_definition": r["definition"], "notes": r["notes"],
                "metric_definitions": _defs(r)}
    if rec.name == "top_movers":
        return {**base, "period": r["period"], "prior_period": r["prior_period"], "rank_by": r["rank_by"],
                "top_increases": r["top_increases"]["display_rows"], "top_decreases": r["top_decreases"]["display_rows"],
                "change_definition": r["definition"], "metric_definitions": _defs(r)}
    if rec.name == "list_catalog":
        return {**base, "data_available": r["data_available"], "conventions": r["conventions"],
                "metric_groups": [{"metrics": [{"name": m["name"], "title": m["title"], "definition": m["definition"]}
                                               for m in g["metrics"]], "dimensions": g["dimensions"]}
                                  for g in r["metric_groups"]],
                "dimension_values": {d["name"]: d["values"] for d in r["dimensions"] if d.get("values")}}
    return {**base, **{k: v for k, v in r.items() if k != "provenance"}}


def llm_text(records: list[ToolRecord]) -> str:
    return json.dumps([llm_view(r) for r in records], ensure_ascii=False, indent=1)


def tables_from(records: list[ToolRecord]) -> list[Table]:
    out: list[Table] = []
    for rec in records:
        r = rec.result
        if not r or rec.name not in QUERY_TOOLS:
            continue
        if rec.name == "query_metrics":
            out.append(Table(call_id=rec.call_id, title=", ".join(rec.arguments.get("metrics", [])),
                             columns=r["columns"], rows=r["rows"], display_rows=r["display_rows"]))
        elif rec.name == "compare_periods":
            cols = [*r["dimensions"], "period_a", "period_b", "change", "change_pct"]
            out.append(Table(call_id=rec.call_id, title=f"{r['metric']}: period comparison", columns=cols,
                             rows=r["rows"], display_rows=r["display_rows"]))
        else:
            cols = [rec.arguments["dimension"], "period_a", "period_b", "change", "change_pct"]
            for key, label in (("top_increases", "biggest increases"), ("top_decreases", "biggest decreases")):
                if r[key]["rows"]:
                    out.append(Table(call_id=f"{rec.call_id}:{key}", title=f"{r['metric']}: {label}", columns=cols,
                                     rows=r[key]["rows"], display_rows=r[key]["display_rows"]))
    return out


def provenance_from(records: list[ToolRecord], executed_as: dict[str, Any]) -> Provenance:
    metrics: dict[str, dict[str, Any]] = {}
    queries: list[dict[str, Any]] = []
    for rec in records:
        prov = (rec.result or {}).get("provenance")
        if not prov:
            continue
        for m in prov["metrics"]:
            metrics[m["name"]] = m
        queries.extend(prov["cube_queries"])
    return Provenance(
        metrics_used=list(metrics), definitions=list(metrics.values()), cube_queries=queries,
        tool_call_ids=[r.call_id for r in records],
        tool_calls=[{"id": r.call_id, "tool": r.name, "arguments": r.arguments, "error": r.error,
                     "latency_ms": r.latency_ms} for r in records],
        executed_as=executed_as)


def _numeric(table: Table, col: str) -> bool:
    return any(isinstance(r.get(col), int | float) and not isinstance(r.get(col), bool) for r in table.rows)


def resolve_chart(spec: ChartSpec | None, tables: list[Table]) -> ChartPayload | None:
    """Validate the model's chart choice against the real result columns; fall back to a sensible default."""
    if not tables:
        return None
    if spec and spec.type == "none":
        return None
    table = next((t for t in tables if spec and t.call_id == spec.source_call_id), None)
    if spec and table and spec.x in table.columns and spec.y and all(_numeric(table, y) for y in spec.y) \
            and (spec.series is None or spec.series in table.columns):
        return ChartPayload(**spec.model_dump(), data=table.rows)
    return _auto_chart(tables[0])


def _auto_chart(table: Table) -> ChartPayload | None:
    if len(table.rows) < 2:
        return None
    metrics = [c for c in table.columns if _numeric(table, c)]
    dims = [c for c in table.columns if c not in metrics]
    if not metrics or not dims:
        return None
    x = "period" if "period" in dims else dims[0]
    series = next((d for d in dims if d != x), None)
    y = metrics[:1] if series else metrics[:3]
    return ChartPayload(type="line" if x == "period" else "bar", x=x, y=y, series=series, title=table.title,
                        source_call_id=table.call_id, data=table.rows)
