"""MCP client used by the agent and the dashboards. The API never touches Cube or the marts directly."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .providers import ToolSpec


@dataclass
class ToolRecord:
    """One executed tool call, kept for provenance and for the post-check."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class McpGateway:
    def __init__(self, url: str) -> None:
        self.url = url
        self.tools: list[ToolSpec] = []

    def _client(self, token: str | None) -> Client:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return Client(streamable_http_client(self.url, http_client=httpx2.AsyncClient(headers=headers)))

    async def discover(self, attempts: int = 30) -> list[ToolSpec]:
        """Load the tool list from the MCP server (waits for it to come up)."""
        last: Exception | None = None
        for _ in range(attempts):
            try:
                async with self._client(None) as client:
                    listed = await client.list_tools()
                self.tools = [ToolSpec(t.name, t.description or "", dict(t.input_schema or {})) for t in listed.tools]
                return self.tools
            except Exception as exc:  # server still starting
                last = exc
                await asyncio.sleep(2)
        raise RuntimeError(f"MCP server at {self.url} is not reachable: {last}")

    async def call(self, token: str, name: str, arguments: dict[str, Any], call_id: str = "") -> ToolRecord:
        loop = asyncio.get_running_loop()
        started = loop.time()
        record = ToolRecord(call_id or name, name, arguments)
        try:
            async with self._client(token) as client:
                result = await client.call_tool(name, arguments)
            text = "".join(getattr(c, "text", "") for c in result.content)
            if result.is_error:
                record.error = text or "tool error"
            else:
                record.result = result.structured_content or json.loads(text)
        except Exception as exc:
            record.error = f"{type(exc).__name__}: {exc}"
        record.latency_ms = int((loop.time() - started) * 1000)
        return record
