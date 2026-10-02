"""Dashboard and reconciliation data. Everything goes through the MCP tools, so charts and chat always agree."""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException

from .agent import Identity
from .gateway import McpGateway, ToolRecord

RECON_TOLERANCE = float(os.getenv("RECON_TOLERANCE", "0.0001"))  # 0.01 %
KPIS = ["total_deposits", "casa_ratio", "npl_ratio", "nim", "active_customers", "churn_rate"]
VIEWS = ("overview", "segments", "branches", "campaigns")


def _ok(rec: ToolRecord) -> dict[str, Any]:
    if rec.error or rec.result is None:
        raise HTTPException(502, rec.error or "tool returned nothing")
    return rec.result


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def _month_end(d: date) -> date:
    return _add_months(_month_start(d), 1) - timedelta(days=1)


def _rng(start: date, end: date) -> dict[str, str]:
    return {"start": start.isoformat(), "end": end.isoformat()}


def _block(rec: ToolRecord, block_id: str, title: str, **extra: Any) -> dict[str, Any]:
    r = _ok(rec)
    prov = r["provenance"]
    return {"id": block_id, "title": title, "columns": r["columns"], "rows": r["rows"], "display_rows": r["display_rows"],
            "notes": r["notes"], "metrics_used": [m["name"] for m in prov["metrics"]],
            "definitions": prov["metrics"], "cube_queries": prov["cube_queries"], **extra}


class Dashboards:
    def __init__(self, gateway: McpGateway) -> None:
        self.gw = gateway

    async def data_range(self, who: Identity) -> tuple[date, date]:
        r = _ok(await self.gw.call(who.token, "list_catalog", {}))
        window = r["data_available"]
        if not window:
            raise HTTPException(404, "No data available for this role")
        return date.fromisoformat(window["from"]), date.fromisoformat(window["to"])

    async def q(self, who: Identity, metrics: list[str], start: date, end: date, dims: list[str] | None = None,
                gran: str | None = None, **extra: Any) -> ToolRecord:
        args = {"metrics": metrics, "date_range": _rng(start, end), "dimensions": dims or [], "limit": 200, **extra}
        if gran:
            args["granularity"] = gran
        return await self.gw.call(who.token, "query_metrics", args)

    async def view(self, who: Identity, view: str) -> dict[str, Any]:
        if view not in VIEWS:
            raise HTTPException(404, f"Unknown view '{view}'. Available: {', '.join(VIEWS)}")
        first, last = await self.data_range(who)
        latest_month = _month_start(last)
        builder = getattr(self, f"_{view}")
        body = await builder(who, first, last, latest_month)
        return {"view": view, "as_of": last.isoformat(), "role": who.role, "branch_id": who.branch_id, **body}

    async def _overview(self, who: Identity, first: date, last: date, latest_month: date) -> dict[str, Any]:
        prior = _add_months(latest_month, -1)
        compare = [self.gw.call(who.token, "compare_periods", {
            "metric": m, "period_a": _rng(prior, _month_end(prior)), "period_b": _rng(latest_month, last)})
            for m in KPIS]
        trends = [
            ("deposits", "Deposits and CASA ratio", self.q(who, ["total_deposits", "casa_ratio"], first, last, None, "month")),
            ("npl", "NPL ratio", self.q(who, ["npl_ratio"], first, last, None, "month")),
            ("nim", "Net interest margin", self.q(who, ["nim"], first, last, None, "month")),
            ("churn_segment", "Monthly churn rate by segment", self.q(who, ["churn_rate"], first, last, ["segment"], "month")),
            ("channels", "Transactions by channel", self.q(who, ["txn_count"], first, last, ["channel"], "month")),
        ]
        done = await asyncio.gather(*compare, *(t[2] for t in trends))
        cmp_res, trend_res = done[:len(KPIS)], done[len(KPIS):]
        kpis = []
        for metric, rec in zip(KPIS, cmp_res, strict=True):
            r = _ok(rec)
            row, disp = r["rows"][0], r["display_rows"][0]
            prov = r["provenance"]
            kpis.append({"metric": metric, "title": prov["metrics"][0]["title"], "value": row["period_b"],
                         "display": disp["period_b"], "previous_display": disp["period_a"], "change": row["change"],
                         "change_display": disp["change"], "change_pct_display": disp["change_pct"],
                         "unit": prov["metrics"][0]["unit"], "definition": prov["metrics"][0]["definition"],
                         "cube_queries": prov["cube_queries"]})
        charts = [_block(rec, cid, title) for (cid, title, _), rec in zip(trends, trend_res, strict=True)]
        return {"kpis": kpis, "charts": charts}

    async def _segments(self, who: Identity, first: date, last: date, latest_month: date) -> dict[str, Any]:
        quarter_start = _add_months(latest_month, -2)
        table, trend = await asyncio.gather(
            self.q(who, ["total_customers", "active_customers", "churn_rate", "cross_sell_rate", "total_deposits",
                         "npl_ratio"], quarter_start, last, ["segment"]),
            self.q(who, ["churn_rate"], first, last, ["segment"], "month"))
        return {"tables": [_block(table, "segments", "Segments, latest quarter")],
                "charts": [_block(trend, "churn_segment", "Monthly churn rate by segment")]}

    async def _branches(self, who: Identity, first: date, last: date, latest_month: date) -> dict[str, Any]:
        table, npl = await asyncio.gather(
            self.q(who, ["total_deposits", "loans_outstanding", "npl_ratio", "active_customers", "txn_count"],
                   latest_month, last, ["branch"], order_by=[{"field": "total_deposits", "direction": "desc"}]),
            self.q(who, ["npl_ratio"], first, last, ["region"], "quarter"))
        return {"tables": [_block(table, "branches", "Branches, latest month")],
                "charts": [_block(npl, "npl_region", "NPL ratio by region")]}

    async def _campaigns(self, who: Identity, first: date, last: date, latest_month: date) -> dict[str, Any]:
        table = await self.q(who, ["campaign_cost", "campaign_response_rate", "campaign_conversion_rate", "cac"],
                             first, last, ["campaign"], order_by=[{"field": "cac", "direction": "asc"}])
        return {"tables": [_block(table, "campaigns", "Campaign performance")], "charts": []}

    # -- reconciliation ---------------------------------------------------------------------------------------------
    async def reconciliation(self, who: Identity) -> dict[str, Any]:
        if who.role == "branch_manager":
            raise HTTPException(403, "Reconciliation is bank-wide and not available to branch managers")
        _, last = await self.data_range(who)
        start = _add_months(_month_start(last), -5)
        rec = await self.q(who, ["total_deposits", "gl_deposits", "loans_outstanding", "gl_loans"], start, last,
                           None, "month")
        r = _ok(rec)
        history = []
        for row in r["rows"]:
            checks = []
            for name, marts_key, gl_key in (("Deposits", "total_deposits", "gl_deposits"),
                                            ("Loans", "loans_outstanding", "gl_loans")):
                marts, gl = row[marts_key], row[gl_key]
                diff = marts - gl
                pct = diff / gl if gl else None
                checks.append({"name": name, "marts": marts, "gl": gl, "difference": diff, "difference_pct": pct,
                               "status": "pass" if pct is not None and abs(pct) <= RECON_TOLERANCE else "fail"})
            history.append({"month": row["period"], "checks": checks,
                            "status": "pass" if all(c["status"] == "pass" for c in checks) else "fail"})
        latest = history[-1] if history else None
        return {"tolerance_pct": RECON_TOLERANCE, "as_of": last.isoformat(),
                "overall": latest["status"] if latest else "unknown", "latest": latest, "history": history,
                "cube_queries": r["provenance"]["cube_queries"]}
