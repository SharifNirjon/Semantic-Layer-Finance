"""Audit trail: every tool call (allowed or not) is written to audit.tool_calls before the response is returned."""

from __future__ import annotations

import asyncio
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

INSERT = """
INSERT INTO audit.tool_calls (user_name, role, tool, args, cube_query, row_count, latency_ms, status, error)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class AuditLog:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _insert(self, params: tuple[Any, ...]) -> None:
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(INSERT, params)

    async def record(self, *, user: str, role: str, tool: str, args: dict[str, Any],
                     cube_queries: list[dict[str, Any]] | None, row_count: int | None, latency_ms: int, status: str,
                     error: str | None = None) -> None:
        params = (user, role, tool, Jsonb(args), Jsonb(cube_queries) if cube_queries else None, row_count, latency_ms,
                  status, error)
        await asyncio.to_thread(self._insert, params)
