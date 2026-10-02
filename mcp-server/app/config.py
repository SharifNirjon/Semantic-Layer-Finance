"""Environment-driven settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cube_url: str
    jwt_secret: str
    transport: str
    host: str
    port: int
    pg_dsn: str
    stdio_token: str | None
    max_rows: int = 200

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        return cls(
            cube_url=env("CUBE_URL", "http://localhost:4000"),
            jwt_secret=env("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long"),
            transport=env("MCP_TRANSPORT", "stdio"),
            host=env("MCP_HOST", "0.0.0.0"),
            port=int(env("MCP_PORT", "8765")),
            pg_dsn="host={h} port={p} dbname={d} user={u} password={pw}".format(
                h=env("POSTGRES_HOST", "localhost"), p=env("POSTGRES_PORT", "5432"),
                d=env("POSTGRES_DB", "warehouse"), u=env("POSTGRES_USER", "bank"),
                pw=env("POSTGRES_PASSWORD", "bank_demo_pw"),
            ),
            stdio_token=env("MCP_JWT"),
        )
