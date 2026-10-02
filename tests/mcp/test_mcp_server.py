"""MCP server acceptance: valid calls, invalid input, role enforcement, audit logging, transports."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import httpx2
import jwt
import psycopg
import pytest
from conftest import JWT_SECRET, make_token
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]
PORT = 18765
URL = f"http://localhost:{PORT}/mcp"
Q3 = {"start": "2026-07-01", "end": "2026-09-30"}
Q2 = {"start": "2026-04-01", "end": "2026-06-30"}
PG_DSN = "host=localhost port=5432 dbname=warehouse user=bank password=bank_demo_pw"
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def server(cube):  # noqa: ARG001 - ensures Cube is up
    env = {**os.environ, "MCP_TRANSPORT": "http", "MCP_PORT": str(PORT), "CUBE_URL": "http://localhost:4000",
           "JWT_SECRET": JWT_SECRET}
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT / "mcp-server", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            if httpx.get(f"http://localhost:{PORT}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        proc.kill()
        pytest.fail("MCP server did not start")
    yield
    proc.kill()


async def call(role: str, tool: str, args: dict[str, Any], branch: int | None = None, token: str | None = None):
    tok = token if token is not None else make_token(role, branch)
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {tok}"})
    async with Client(streamable_http_client(URL, http_client=http)) as client:
        return await client.call_tool(tool, args)


def audit_rows(tool: str, since: float) -> list[tuple]:
    with psycopg.connect(PG_DSN) as conn:
        return conn.execute(
            "SELECT user_name, role, status, row_count, cube_query IS NOT NULL, error FROM audit.tool_calls "
            "WHERE tool = %s AND ts >= to_timestamp(%s) ORDER BY id", (tool, since)).fetchall()


async def test_exposes_only_read_only_governed_tools():
    http = httpx2.AsyncClient(headers={"Authorization": f"Bearer {make_token('cmo')}"})
    async with Client(streamable_http_client(URL, http_client=http)) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"list_catalog", "describe_metric", "query_metrics", "compare_periods",
                                       "top_movers"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools)
    for t in tools:  # no raw SQL escape hatch anywhere in the schemas
        props = (t.input_schema or {}).get("properties", {})
        assert not {"sql", "query", "raw_sql"} & set(props), t.name
    qm = next(t for t in tools if t.name == "query_metrics")
    assert qm.input_schema["properties"]["limit"]["maximum"] == 200


async def test_list_catalog_and_describe_metric():
    cat = (await call("cmo", "list_catalog", {})).structured_content
    names = {m["name"] for g in cat["metric_groups"] for m in g["metrics"]}
    assert {"total_deposits", "churn_rate", "npl_ratio", "nim", "cac"} <= names
    assert cat["data_available"] == {"from": "2024-10-01", "to": "2026-09-30"}
    seg = next(d for d in cat["dimensions"] if d["name"] == "segment")
    assert "Young Professionals" in seg["values"]
    d = (await call("cmo", "describe_metric", {"name": "churn_rate"})).structured_content
    assert d["owner"] and d["definition"] and d["source_tables"] and d["time_semantics"] == "flow"
    assert "segment" in d["available_dimensions"]


async def test_query_returns_rows_provenance_and_definitions():
    r = await call("cmo", "query_metrics", {"metrics": ["churn_rate", "new_customers"], "date_range": Q3,
                                            "dimensions": ["segment"], "order_by": [{"field": "churn_rate"}]})
    sc = r.structured_content
    assert not r.is_error and sc["row_count"] == 5
    assert sc["rows"][0]["segment"] == "Young Professionals"  # planted story a)
    assert sc["display_rows"][0]["churn_rate"].endswith("%")
    prov = sc["provenance"]
    assert {m["name"] for m in prov["metrics"]} == {"churn_rate", "new_customers"}
    assert prov["cube_queries"] and prov["cube_queries"][0]["timeDimensions"][0]["dateRange"] == [
        "2026-07-01", "2026-09-30"]
    assert prov["executed_as"] == {"role": "cmo", "branch_id": None}


async def test_period_end_metric_over_quarter_reports_last_month_end_not_a_sum():
    ref_total = (await call("cmo", "query_metrics", {
        "metrics": ["total_deposits"], "date_range": {"start": "2026-09-01", "end": "2026-09-30"}})).structured_content
    q = (await call("cmo", "query_metrics", {"metrics": ["total_deposits"], "date_range": Q3})).structured_content
    assert q["rows"][0]["total_deposits"] == pytest.approx(ref_total["rows"][0]["total_deposits"])
    assert any("as of 2026-09-30" in n for n in q["notes"])
    by_q = (await call("cmo", "query_metrics", {"metrics": ["total_deposits"], "date_range": Q3,
                                                "granularity": "quarter"})).structured_content
    assert by_q["rows"][0]["period"] == "2026-Q3"
    assert by_q["rows"][0]["total_deposits"] == pytest.approx(q["rows"][0]["total_deposits"])


async def test_flow_metric_sums_and_monthly_trend_is_ordered():
    r = (await call("cmo", "query_metrics", {"metrics": ["txn_count"], "date_range": Q3,
                                             "granularity": "month"})).structured_content
    assert [x["period"] for x in r["rows"]] == ["2026-07", "2026-08", "2026-09"]
    total = (await call("cmo", "query_metrics", {"metrics": ["txn_count"], "date_range": Q3})).structured_content
    assert sum(x["txn_count"] for x in r["rows"]) == total["rows"][0]["txn_count"]


async def test_mixed_cubes_merge_on_shared_dimensions():
    r = (await call("cmo", "query_metrics", {"metrics": ["total_deposits", "txn_count", "npl_ratio"],
                                             "date_range": Q3, "dimensions": ["region"]})).structured_content
    row = next(x for x in r["rows"] if x["region"] == "Dhaka")
    assert row["total_deposits"] and row["txn_count"] and row["npl_ratio"] is not None


@pytest.mark.parametrize(("args", "needle"), [
    ({"metrics": ["churn"], "date_range": Q3}, "Did you mean: churn_rate"),
    ({"metrics": ["churn_rate"], "dimensions": ["colour"], "date_range": Q3}, "Unknown dimension"),
    ({"metrics": ["nim"], "dimensions": ["channel"], "date_range": Q3}, "not available for metric 'nim'"),
    ({"metrics": ["churn_rate"], "date_range": Q3,
      "filters": [{"dimension": "segment", "values": ["Youth"]}]}, "Valid values"),
    ({"metrics": ["churn_rate"], "date_range": {"start": "2026-09-30", "end": "2026-01-01"}}, "must not be after"),
    ({"metrics": ["total_deposits"], "date_range": Q3, "granularity": "day"}, "Daily granularity"),
    ({"metrics": ["churn_rate"], "date_range": Q3, "limit": 201}, "limit"),
    ({"metrics": [], "date_range": Q3}, "metrics"),
])
async def test_invalid_requests_get_helpful_errors(args, needle):
    r = await call("cmo", "query_metrics", args)
    assert r.is_error
    assert needle in r.content[0].text


async def test_sql_requests_are_impossible():
    r = await call("cmo", "query_metrics", {"metrics": ["select * from raw.customers"], "date_range": Q3})
    assert r.is_error and "Unknown metric" in r.content[0].text


async def test_branch_manager_is_confined_to_own_branch():
    r = (await call("branch_manager", "query_metrics", {
        "metrics": ["total_deposits", "loans_outstanding"], "date_range": Q3, "dimensions": ["branch"]},
        branch=7)).structured_content
    assert [x["branch"] for x in r["rows"]] == ["Narayanganj"]
    other = await call("branch_manager", "query_metrics", {
        "metrics": ["total_deposits"], "date_range": Q3, "dimensions": ["branch"],
        "filters": [{"dimension": "branch", "values": ["Gulshan"]}]}, branch=7)
    assert other.is_error  # rejected up front; the valid values listed are only the caller's own
    text = other.content[0].text
    assert "Valid values: Narayanganj" in text and "Gulshan" not in text.split("Valid values")[1]


async def test_branch_manager_cannot_see_bank_wide_or_missing_branch():
    r = await call("branch_manager", "query_metrics", {"metrics": ["gl_deposits"], "date_range": Q3}, branch=7)
    assert r.is_error and "Unknown metric" in r.content[0].text
    r = await call("branch_manager", "query_metrics", {"metrics": ["total_deposits"], "date_range": Q3}, branch=None)
    assert r.is_error and "no branch_id" in r.content[0].text


async def test_analyst_has_no_customer_level_dimensions():
    cat = (await call("analyst", "list_catalog", {})).structured_content
    assert not any(d["customer_level"] for d in cat["dimensions"])
    r = await call("analyst", "query_metrics", {"metrics": ["txn_count"], "dimensions": ["customer_key"],
                                                "date_range": Q3})
    assert r.is_error
    cmo = (await call("cmo", "list_catalog", {})).structured_content
    assert any(d["customer_level"] for d in cmo["dimensions"])


async def test_bad_or_missing_token_is_denied():
    assert (await call("cmo", "list_catalog", {}, token="garbage")).is_error
    forged = jwt.encode({"role": "cmo", "sub": "mallory", "exp": int(time.time()) + 600}, "wrong-secret-wrong-secret-wrong!",
                        algorithm="HS256")
    assert (await call("cmo", "list_catalog", {}, token=forged)).is_error


async def test_compare_periods_and_top_movers():
    r = (await call("cmo", "compare_periods", {"metric": "churn_rate", "period_a": Q2, "period_b": Q3,
                                               "dimensions": ["segment"]})).structured_content
    yp = next(x for x in r["rows"] if x["segment"] == "Young Professionals")
    assert yp["change"] == pytest.approx(yp["period_b"] - yp["period_a"])
    assert yp["change_pct"] == pytest.approx(yp["change"] / yp["period_a"])
    assert r["rows"][0]["segment"] == "Young Professionals"  # largest mover first
    assert "pp" in r["display_rows"][0]["change"]
    m = (await call("cmo", "top_movers", {"metric": "churn_rate", "dimension": "segment", "period": Q3,
                                          "top_n": 2})).structured_content
    assert m["prior_period"] == Q2
    assert m["top_increases"]["rows"][0]["segment"] == "Young Professionals"
    changes = [x["change"] for x in m["top_increases"]["rows"]]
    assert changes == sorted(changes, reverse=True)


async def test_every_call_is_audited_including_denials_and_errors():
    start = time.time() - 1
    await call("cmo", "query_metrics", {"metrics": ["txn_count"], "date_range": Q3, "dimensions": ["channel"]})
    await call("cmo", "query_metrics", {"metrics": ["nonsense"], "date_range": Q3})
    await call("analyst", "query_metrics", {"metrics": ["txn_count"], "dimensions": ["customer_key"], "date_range": Q3})
    await call("cmo", "list_catalog", {}, token="garbage")
    rows = audit_rows("query_metrics", start)
    ok = [r for r in rows if r[2] == "ok"]
    assert ok and ok[-1][0] == "test-cmo" and ok[-1][1] == "cmo" and ok[-1][3] == 5 and ok[-1][4] is True
    assert any(r[2] == "error" and "Unknown metric" in (r[5] or "") for r in rows)
    assert any(r[1] == "analyst" and r[2] == "error" for r in rows)
    denied = audit_rows("list_catalog", start)
    assert any(r[0] == "anonymous" and r[2] == "denied" for r in denied)


async def test_stdio_transport_uses_token_from_environment():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app"], cwd=str(ROOT / "mcp-server"),
        env={**os.environ, "MCP_TRANSPORT": "stdio", "MCP_JWT": make_token("analyst"), "JWT_SECRET": JWT_SECRET,
             "CUBE_URL": "http://localhost:4000"})
    async with Client(params) as client:
        r = await client.call_tool("query_metrics", {"metrics": ["txn_count"], "date_range": Q3})
    assert not r.is_error and r.structured_content["rows"][0]["txn_count"] > 0
