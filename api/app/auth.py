"""Demo authentication: three fixed users, HS256 JWTs. Cube and the MCP server verify the same token."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from .agent import Identity

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")
TOKEN_TTL_S = 8 * 3600
DEMO_PASSWORD = "demo123"


@dataclass(frozen=True)
class DemoUser:
    username: str
    role: str
    branch_id: int | None
    display_name: str


DEMO_USERS = {
    "cmo": DemoUser("cmo", "cmo", None, "Chief Marketing Officer"),
    "branch_manager_dhaka": DemoUser("branch_manager_dhaka", "branch_manager", 7, "Branch Manager - Narayanganj (Dhaka)"),
    "analyst": DemoUser("analyst", "analyst", None, "Marketing Analyst"),
}


def issue_token(user: DemoUser) -> str:
    claims: dict[str, object] = {"sub": user.username, "role": user.role, "exp": int(time.time()) + TOKEN_TTL_S}
    if user.branch_id is not None:
        claims["branch_id"] = user.branch_id
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


def login(username: str, password: str) -> tuple[DemoUser, str]:
    user = DEMO_USERS.get(username)
    if user is None or password != DEMO_PASSWORD:
        raise HTTPException(401, "Invalid username or password")
    return user, issue_token(user)


def current_identity(authorization: Annotated[str | None, Header()] = None) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"Invalid token: {exc}") from exc
    return Identity(str(claims.get("sub", "")), str(claims.get("role", "")), claims.get("branch_id"), token)


CurrentUser = Annotated[Identity, Depends(current_identity)]
