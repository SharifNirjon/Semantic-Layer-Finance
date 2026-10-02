"""Shared fixtures. Integration tests need `docker compose up -d postgres cube` with data loaded."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest

CUBE_URL = os.getenv("CUBE_URL", "http://localhost:4000")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")


def make_token(role: str, branch_id: int | None = None, sub: str | None = None) -> str:
    claims: dict[str, Any] = {"role": role, "sub": sub or f"test-{role}", "exp": int(time.time()) + 3600}
    if branch_id is not None:
        claims["branch_id"] = branch_id
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


class CubeClient:
    def __init__(self, base_url: str = CUBE_URL) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=120)

    def load(self, token: str, query: dict[str, Any]) -> httpx.Response:
        for _ in range(60):
            r = self.client.post("/cubejs-api/v1/load", headers={"Authorization": token}, json={"query": query})
            if r.status_code == 200 and r.json().get("error") == "Continue wait":
                time.sleep(1)
                continue
            return r
        raise TimeoutError("Cube kept answering 'Continue wait'")

    def rows(self, token: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        r = self.load(token, query)
        assert r.status_code == 200, r.text
        return r.json()["data"]

    def value(self, token: str, measure: str, date_range: tuple[str, str], filters: list[dict[str, Any]] | None = None,
              cube_dims: list[str] | None = None) -> float:
        cube = measure.split(".")[0]
        rows = self.rows(token, {
            "measures": [measure],
            "dimensions": cube_dims or [],
            "filters": filters or [],
            "timeDimensions": [{"dimension": f"{cube}.business_date", "dateRange": list(date_range)}],
        })
        assert len(rows) == 1, rows
        return float(rows[0][measure])


@pytest.fixture(scope="session")
def cube() -> CubeClient:
    c = CubeClient()
    try:
        httpx.get(f"{CUBE_URL}/readyz", timeout=5).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("Cube is not running (docker compose up -d postgres cube)")
    return c


@pytest.fixture(scope="session")
def cmo_token() -> str:
    return make_token("cmo")


@pytest.fixture(scope="session")
def token_for() -> Callable[..., str]:
    return make_token
