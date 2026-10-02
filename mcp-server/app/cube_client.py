"""Thin async client for Cube's REST API. The caller's JWT is passed through unchanged."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from .errors import AccessDenied, ToolInputError


class CubeClient:
    def __init__(self, base_url: str) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=120)

    async def meta(self, token: str) -> dict[str, Any]:
        r = await self._http.get("/cubejs-api/v1/meta", headers={"Authorization": token})
        r.raise_for_status()
        return r.json()

    async def load(self, token: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        for _ in range(120):
            r = await self._http.post("/cubejs-api/v1/load", headers={"Authorization": token}, json={"query": query})
            body = r.json()
            if r.status_code == 200 and body.get("error") == "Continue wait":
                await asyncio.sleep(0.5)  # Cube is still building a pre-aggregation
                continue
            if r.status_code != 200:
                message = str(body.get("error", r.text))
                if "Access denied" in message:
                    raise AccessDenied(message.removeprefix("Error: "))
                raise ToolInputError(f"Cube rejected the query: {message}")
            return list(body["data"])
        raise TimeoutError("Cube did not finish the query in time")
