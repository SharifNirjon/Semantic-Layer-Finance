"""Query planning and execution against Cube.

Metrics carry a `time_semantics` (flow / period_end / average). Flow metrics are summed by Cube over the requested
range. Period-end and average metrics are fetched at month grain and collapsed here, so a quarter shows the value at the
last month end (or the mean of the month values) instead of a meaningless sum of balances.
"""

from __future__ import annotations

import asyncio
import calendar
import difflib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from .auth import Caller
from .catalog import TIME_DIM, Catalog, Metric
from .cube_client import CubeClient
from .errors import ToolInputError
from .formatting import format_change, format_pct_change, format_value

Granularity = Literal["day", "month", "quarter", "year"]
CUBE_ROW_LIMIT = 50_000
CATALOG_TTL_S = 300


class DateRange(BaseModel):
    start: date = Field(description="First day of the period, inclusive, YYYY-MM-DD.")
    end: date = Field(description="Last day of the period, inclusive, YYYY-MM-DD.")


class Filter(BaseModel):
    dimension: str = Field(description="Dimension name from list_catalog, e.g. 'segment', 'branch', 'region'.")
    operator: Literal["equals", "not_equals"] = Field(
        "equals", description="'equals' keeps rows whose value is any of `values`; 'not_equals' excludes them.")
    values: list[str] = Field(min_length=1, description="Exact dimension values, e.g. ['Young Professionals'].")


class OrderBy(BaseModel):
    field: str = Field(description="A requested metric or dimension name, or 'period' when granularity is set.")
    direction: Literal["asc", "desc"] = "desc"


@dataclass
class Plan:
    cube: str
    metrics: list[Metric]
    collapse: str  # none | last | avg
    query: dict[str, Any]
    time_key: str | None


@dataclass
class Result:
    columns: list[str]
    rows: list[dict[str, Any]]
    display_rows: list[dict[str, str]]
    metrics: list[Metric]
    cube_queries: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)
    truncated: bool = False
    total_rows: int = 0
    latency_ms: int = 0


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def bucket_label(month: str, granularity: str | None) -> str:
    """month is 'YYYY-MM'."""
    if granularity is None:
        return ""
    y, m = int(month[:4]), int(month[5:7])
    return {"month": month, "quarter": f"{y}-Q{(m - 1) // 3 + 1}", "year": str(y)}[granularity]


def cube_time_label(raw: str, granularity: str) -> str:
    return {"day": raw[:10], "month": raw[:7], "quarter": bucket_label(raw[:7], "quarter"), "year": raw[:4]}[granularity]


def prior_period(p: DateRange) -> DateRange:
    if p.start.day == 1 and p.end == month_end(p.end):
        n = (p.end.year - p.start.year) * 12 + p.end.month - p.start.month + 1
        return DateRange(start=add_months(p.start, -n), end=p.start - timedelta(days=1))
    days = (p.end - p.start).days + 1
    end = p.start - timedelta(days=1)
    return DateRange(start=end - timedelta(days=days - 1), end=end)


class Engine:
    def __init__(self, cube: CubeClient, max_rows: int = 200) -> None:
        self.cube = cube
        self.max_rows = max_rows
        self._catalog: tuple[float, Catalog] | None = None
        self._values: dict[tuple[str, int | None, str], list[str]] = {}
        self._data_range: dict[tuple[str, int | None], tuple[date, date]] = {}

    async def catalog(self, token: str) -> Catalog:
        if self._catalog is None or time.monotonic() - self._catalog[0] > CATALOG_TTL_S:
            self._catalog = (time.monotonic(), Catalog.from_meta(await self.cube.meta(token)))
        return self._catalog[1]

    async def dimension_values(self, caller: Caller, cat: Catalog, name: str) -> list[str]:
        key = (caller.role, caller.branch_id, name)
        if key not in self._values:
            dim = cat.dimension(name, caller.role)
            member = next(iter(dim.members.values()))
            rows = await self.cube.load(caller.token, {"dimensions": [member], "limit": 500})
            self._values[key] = sorted(str(r[member]) for r in rows if r.get(member) is not None)
        return self._values[key]

    async def data_range(self, caller: Caller) -> tuple[date, date] | None:
        key = (caller.role, caller.branch_id)
        if key not in self._data_range:
            rows = await self.cube.load(caller.token, {
                "measures": ["balances.total_deposits"],
                "timeDimensions": [{"dimension": "balances.business_date", "granularity": "month",
                                    "dateRange": ["2000-01-01", "2100-12-31"]}]})
            months = sorted(r["balances.business_date.month"][:7] for r in rows)
            if not months:
                return None
            first = date(int(months[0][:4]), int(months[0][5:7]), 1)
            last = month_end(date(int(months[-1][:4]), int(months[-1][5:7]), 1))
            self._data_range[key] = (first, last)
        return self._data_range[key]

    # ------------------------------------------------------------------------------------------------------------
    async def query(self, caller: Caller, metrics: list[str], date_range: DateRange,
                    dimensions: list[str] | None = None, granularity: Granularity | None = None,
                    filters: list[Filter] | None = None, order_by: list[OrderBy] | None = None,
                    limit: int = 50) -> Result:
        started = time.perf_counter()
        cat = await self.catalog(caller.token)
        if not metrics:
            raise ToolInputError("Provide at least one metric. Call list_catalog to see the available metrics.")
        if not 1 <= limit <= self.max_rows:
            raise ToolInputError(f"limit must be between 1 and {self.max_rows}.")
        if date_range.start > date_range.end:
            raise ToolInputError("date_range.start must not be after date_range.end.")
        ms = [cat.metric(n, caller.role) for n in dict.fromkeys(metrics)]
        dim_names = list(dict.fromkeys(dimensions or []))
        ds = [cat.dimension(n, caller.role) for n in dim_names]
        for m in ms:
            for d in ds:
                cat.check_combination(m, d)
        notes: list[str] = []
        cube_filters = await self._cube_filters(caller, cat, filters or [], {m.cube for m in ms})
        plans = self._plan(ms, ds, date_range, granularity, cube_filters, notes)
        data = await asyncio.gather(*(self.cube.load(caller.token, p.query) for p in plans))

        merged: dict[tuple[tuple[str, ...], str], dict[str, float | None]] = {}
        as_of: dict[str, set[str]] = defaultdict(set)
        for plan, rows in zip(plans, data, strict=True):
            self._merge(plan, rows, [d.members[plan.cube] for d in ds], granularity, merged, as_of)

        columns = (["period"] if granularity else []) + dim_names + [m.name for m in ms]
        out = []
        for (dims, bucket), values in merged.items():
            row: dict[str, Any] = {}
            if granularity:
                row["period"] = bucket
            row.update(zip(dim_names, dims, strict=True))
            row.update({m.name: values.get(m.name) for m in ms})
            out.append(row)
        out = self._sort(out, order_by, columns, ms, granularity)
        total = len(out)
        out = out[:limit]
        display = [{**{c: str(r[c]) for c in columns if c not in {m.name for m in ms}},
                    **{m.name: format_value(r[m.name], m.unit) for m in ms}} for r in out]
        self._period_notes(ms, date_range, granularity, as_of, notes)
        if not out:
            rng = await self.data_range(caller)
            span = f" Data is available from {rng[0]} to {rng[1]}." if rng else ""
            notes.append(f"No rows matched the request.{span}")
        return Result(columns, out, display, ms, [p.query for p in plans], notes, total > limit, total,
                      int((time.perf_counter() - started) * 1000))

    async def _cube_filters(self, caller: Caller, cat: Catalog, filters: list[Filter],
                            cubes: set[str]) -> list[tuple[str, str, list[str]]]:
        out = []
        for f in filters:
            dim = cat.dimension(f.dimension, caller.role)
            known = await self.dimension_values(caller, cat, f.dimension)
            bad = [v for v in f.values if v not in known]
            if bad and known:
                close = [c for v in bad for c in _close(v, known)]
                raise ToolInputError(
                    f"Unknown {f.dimension} value(s) {bad}. Valid values: {', '.join(known[:40])}"
                    + (f". Closest: {', '.join(close)}" if close else "") + ".")
            missing = [c for c in cubes if c not in dim.members]
            if missing:
                raise ToolInputError(f"Dimension '{f.dimension}' cannot filter metrics from: {', '.join(missing)}.")
            out.append((f.dimension, "equals" if f.operator == "equals" else "notEquals", f.values))
        return out

    def _plan(self, ms: list[Metric], ds: list[Any], dr: DateRange, gran: str | None,
              filters: list[tuple[str, str, list[str]]], notes: list[str]) -> list[Plan]:
        by_cube: dict[str, list[Metric]] = defaultdict(list)
        for m in ms:
            by_cube[m.cube].append(m)
        plans: list[Plan] = []
        for cube, cms in by_cube.items():
            grain = cms[0].grain
            if gran == "day" and grain != "day":
                bad = ", ".join(m.name for m in cms)
                raise ToolInputError(f"Daily granularity is not available for {bad} (month-grain data). "
                                     "Use granularity 'month', 'quarter' or 'year'.")
            start, end = dr.start, dr.end
            if grain == "month":
                start, end = date(start.year, start.month, 1), month_end(end)
                if (start, end) != (dr.start, dr.end):
                    notes.append(f"{', '.join(m.name for m in cms)} are month-grain: range widened to whole months "
                                 f"{start}..{end}.")
            by_sem: dict[str, list[Metric]] = defaultdict(list)
            for m in cms:
                by_sem[m.time_semantics].append(m)
            for sem, group in by_sem.items():
                collapse = {"flow": "none", "period_end": "last", "average": "avg"}[sem]
                cube_gran = gran if collapse == "none" else "month"
                td: dict[str, Any] = {"dimension": f"{cube}.{TIME_DIM}", "dateRange": [start.isoformat(), end.isoformat()]}
                if cube_gran:
                    td["granularity"] = cube_gran
                query = {
                    "measures": [m.member for m in group],
                    "dimensions": [d.members[cube] for d in ds],
                    "filters": [{"member": f"{cube}.{dim}", "operator": op, "values": vals}
                                for dim, op, vals in filters],
                    "timeDimensions": [td],
                    "limit": CUBE_ROW_LIMIT,
                }
                plans.append(Plan(cube, group, collapse, query, f"{cube}.{TIME_DIM}.{cube_gran}" if cube_gran else None))
        return plans

    @staticmethod
    def _merge(plan: Plan, rows: list[dict[str, Any]], dim_members: list[str], gran: str | None,
               merged: dict[tuple[tuple[str, ...], str], dict[str, float | None]], as_of: dict[str, set[str]]) -> None:
        def num(row: dict[str, Any], m: Metric) -> float | None:
            v = row.get(m.member)
            return None if v is None else float(v)

        def dims_of(row: dict[str, Any]) -> tuple[str, ...]:
            return tuple(str(row.get(d)) for d in dim_members)

        if plan.collapse == "none":
            for row in rows:
                bucket = cube_time_label(row[plan.time_key], gran) if plan.time_key and gran else ""
                merged.setdefault((dims_of(row), bucket), {}).update({m.name: num(row, m) for m in plan.metrics})
            return
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            month = cube_time_label(row[plan.time_key], "month")  # type: ignore[index]
            buckets[bucket_label(month, gran)].append({**row, "_month": month})
        for bucket, brows in buckets.items():
            months = sorted({r["_month"] for r in brows})
            if plan.collapse == "last":
                as_of[bucket].add(months[-1])
                for r in (r for r in brows if r["_month"] == months[-1]):
                    merged.setdefault((dims_of(r), bucket), {}).update({m.name: num(r, m) for m in plan.metrics})
            else:
                acc: dict[tuple[str, ...], dict[str, float]] = defaultdict(lambda: defaultdict(float))
                for r in brows:
                    for m in plan.metrics:
                        acc[dims_of(r)][m.name] += num(r, m) or 0.0
                for dims, vals in acc.items():
                    merged.setdefault((dims, bucket), {}).update({k: v / len(months) for k, v in vals.items()})

    @staticmethod
    def _sort(rows: list[dict[str, Any]], order_by: list[OrderBy] | None, columns: list[str], ms: list[Metric],
              gran: str | None) -> list[dict[str, Any]]:
        spec = order_by or ([OrderBy(field="period", direction="asc")] if gran else []) + [
            OrderBy(field=ms[0].name, direction="desc")]
        for o in reversed(spec):
            if o.field not in columns:
                raise ToolInputError(f"order_by field '{o.field}' is not in the result columns: {', '.join(columns)}.")
            rows.sort(key=lambda r, f=o.field: (r[f] is None, r[f]), reverse=o.direction == "desc")  # type: ignore[misc]
        return rows

    @staticmethod
    def _period_notes(ms: list[Metric], dr: DateRange, gran: str | None, as_of: dict[str, set[str]],
                      notes: list[str]) -> None:
        last = sorted(m for months in as_of.values() for m in months)
        for sem, text in (("period_end", "period-end values"), ("average", "averages of monthly values")):
            names = [m.name for m in ms if m.time_semantics == sem]
            if not names or not last:
                continue
            if gran:
                notes.append(f"{', '.join(names)}: {text} for each {gran} (the last month end within it).")
            else:
                d = month_end(date(int(last[-1][:4]), int(last[-1][5:7]), 1))
                notes.append(f"{', '.join(names)}: {text} as of {d}.")
        flows = [m.name for m in ms if m.time_semantics == "flow"]
        if flows:
            notes.append(f"{', '.join(flows)}: totals over {dr.start}..{dr.end}" + (f" by {gran}." if gran else "."))

    # ------------------------------------------------------------------------------------------------------------
    async def compare(self, caller: Caller, metric: str, period_a: DateRange, period_b: DateRange,
                      dimensions: list[str] | None = None, filters: list[Filter] | None = None,
                      limit: int = 50) -> dict[str, Any]:
        a, b = await asyncio.gather(
            self.query(caller, [metric], period_a, dimensions, None, filters, None, self.max_rows),
            self.query(caller, [metric], period_b, dimensions, None, filters, None, self.max_rows))
        m = a.metrics[0]
        dim_names = list(dict.fromkeys(dimensions or []))
        va = {tuple(r[d] for d in dim_names): r[metric] for r in a.rows}
        vb = {tuple(r[d] for d in dim_names): r[metric] for r in b.rows}
        rows = []
        for key in dict.fromkeys([*va, *vb]):
            x, y = va.get(key), vb.get(key)
            change = None if x is None or y is None else y - x
            pct = None if change is None or not x else change / abs(x)
            rows.append({**dict(zip(dim_names, key, strict=True)), "period_a": x, "period_b": y, "change": change,
                         "change_pct": pct})
        rows.sort(key=lambda r: (r["change"] is None, -abs(r["change"] or 0)))
        total, rows = len(rows), rows[:limit]
        return {
            "metric": metric, "dimensions": dim_names, "period_a": period_a.model_dump(mode="json"),
            "period_b": period_b.model_dump(mode="json"),
            "definition": "change = period_b minus period_a; change_pct = change / |period_a|; "
                          "percent-unit metrics report change in percentage points.",
            "rows": rows, "display_rows": [self._display_change(r, dim_names, m) for r in rows],
            "notes": [*a.notes, *b.notes], "truncated": total > limit, "total_rows": total,
            "metrics_used": [m], "cube_queries": [*a.cube_queries, *b.cube_queries],
        }

    @staticmethod
    def _display_change(row: dict[str, Any], dim_names: list[str], m: Metric) -> dict[str, str]:
        out = {d: str(row[d]) for d in dim_names}
        out.update({"period_a": format_value(row["period_a"], m.unit), "period_b": format_value(row["period_b"], m.unit),
                    "change": format_change(row["change"], m.unit), "change_pct": format_pct_change(row["change_pct"])})
        return out

    async def top_movers(self, caller: Caller, metric: str, dimension: str, period: DateRange, top_n: int = 5,
                         rank_by: Literal["absolute", "percent"] = "absolute",
                         filters: list[Filter] | None = None) -> dict[str, Any]:
        prior = prior_period(period)
        res = await self.compare(caller, metric, prior, period, [dimension], filters, self.max_rows)
        key = "change" if rank_by == "absolute" else "change_pct"
        ranked = [(r, d) for r, d in zip(res["rows"], res["display_rows"], strict=True) if r[key] is not None]
        ranked.sort(key=lambda rd: rd[0][key], reverse=True)

        def pack(items: list[tuple[dict[str, Any], dict[str, str]]]) -> dict[str, Any]:
            return {"rows": [r for r, _ in items], "display_rows": [d for _, d in items]}

        res.update({
            "period": period.model_dump(mode="json"), "prior_period": prior.model_dump(mode="json"),
            "rank_by": rank_by,
            "top_increases": pack([x for x in ranked[:top_n] if x[0][key] > 0]),
            "top_decreases": pack([x for x in ranked[::-1][:top_n] if x[0][key] < 0]),
        })
        for k in ("rows", "display_rows", "period_a", "period_b"):
            res.pop(k)
        return res


def _close(value: str, options: list[str]) -> list[str]:
    return difflib.get_close_matches(value, options, n=2, cutoff=0.5)
