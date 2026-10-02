"""Helpers shared by the provider adapters: retry with exponential backoff and JSON-schema simplification."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")
MAX_ATTEMPTS = 5
BASE_DELAY_S = 1.0
MAX_DELAY_S = 30.0


async def with_backoff(call: Callable[[], Awaitable[T]], is_retryable: Callable[[Exception], float | None],
                       sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> T:
    """Run `call`, retrying with exponential backoff and jitter on rate limits / transient errors.

    `is_retryable` returns None for fatal errors, or a minimum delay in seconds (0 if the provider gave no hint).
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            return await call()
        except Exception as exc:
            hint = is_retryable(exc)
            if hint is None or attempt == MAX_ATTEMPTS - 1:
                raise
            delay = min(MAX_DELAY_S, max(hint, BASE_DELAY_S * 2 ** attempt)) + random.uniform(0, 0.5)
            await sleep(delay)
    raise AssertionError("unreachable")


def inline_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref/$defs, collapse nullable anyOf and drop keywords function-calling APIs reject."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(x) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
        if "anyOf" in node:
            options = [o for o in node["anyOf"] if o.get("type") != "null"]
            if len(options) == 1:
                merged = {**{k: v for k, v in node.items() if k != "anyOf"}, **options[0]}
                return walk(merged)
        out = {
            k: ({pk: walk(pv) for pk, pv in v.items()} if k == "properties" else walk(v))
            for k, v in node.items() if k not in {"$defs", "title", "default", "additionalProperties"}
        }
        if out.get("format") in {"date", "date-time"}:
            out.pop("format")
            out["description"] = (out.get("description", "") + " (format YYYY-MM-DD)").strip()
        return out

    return walk({k: v for k, v in schema.items() if k != "$defs"})  # type: ignore[no-any-return]
