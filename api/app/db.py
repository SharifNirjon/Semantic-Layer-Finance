"""Small Postgres helpers for the audit log and the demo GL adjustment. (No mart access: marts go through Cube.)"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def dsn() -> str:
    env = os.environ.get
    return "host={h} port={p} dbname={d} user={u} password={pw}".format(
        h=env("POSTGRES_HOST", "localhost"), p=env("POSTGRES_PORT", "5432"), d=env("POSTGRES_DB", "warehouse"),
        u=env("POSTGRES_USER", "bank"), pw=env("POSTGRES_PASSWORD", "bank_demo_pw"))


def _run(sql: str, params: tuple[Any, ...] = (), fetch: bool = False) -> list[dict[str, Any]]:
    with psycopg.connect(dsn(), autocommit=True, row_factory=dict_row) as conn:  # type: ignore[arg-type]
        cur = conn.execute(sql, params)  # type: ignore[arg-type]
        return cur.fetchall() if fetch else []


async def run(sql: str, params: tuple[Any, ...] = (), fetch: bool = False) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_run, sql, params, fetch)


async def record_chat(user: str, role: str, question: str, provider: str, tool_calls: int, latency_ms: int,
                      status: str, error: str | None = None) -> None:
    await run(
        "INSERT INTO audit.tool_calls (user_name, role, tool, args, row_count, latency_ms, status, error) "
        "VALUES (%s, %s, 'chat', %s, %s, %s, %s, %s)",
        (user, role, Jsonb({"question": question, "provider": provider}), tool_calls, latency_ms, status, error))


async def audit_entries(user: str | None, tool: str | None, status: str | None, hours: int | None,
                        limit: int, only_user: str | None) -> list[dict[str, Any]]:
    clauses, params = [], []
    for column, value in (("user_name", only_user or user), ("tool", tool), ("status", status)):
        if value:
            clauses.append(f"{column} = %s")
            params.append(value)
    if hours:
        clauses.append("ts >= now() - make_interval(hours => %s)")
        params.append(hours)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await run(
        f"SELECT id, ts, user_name AS \"user\", role, tool, args, cube_query, row_count, latency_ms, status, error "
        f"FROM audit.tool_calls {where} ORDER BY id DESC LIMIT %s", (*params, limit), fetch=True)
    for r in rows:
        if isinstance(r["ts"], datetime):
            r["ts"] = r["ts"].isoformat()
    return rows


async def set_gl_break(delta_pct: float | None) -> None:
    if delta_pct is None:
        await run("DELETE FROM audit.gl_adjustments WHERE gl_code = 'DEPOSITS'")
    else:
        await run(
            "INSERT INTO audit.gl_adjustments (gl_code, delta_pct, note) VALUES ('DEPOSITS', %s, 'demo reconciliation break') "
            "ON CONFLICT (gl_code) DO UPDATE SET delta_pct = EXCLUDED.delta_pct, created_at = now()", (delta_pct,))


async def gl_break() -> float | None:
    rows = await run("SELECT delta_pct FROM audit.gl_adjustments WHERE gl_code = 'DEPOSITS'", fetch=True)
    return float(rows[0]["delta_pct"]) if rows else None
