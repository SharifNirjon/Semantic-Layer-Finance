"""Authentication: admin-managed accounts (app.users) plus optional fixed demo users; HS256 JWTs.

Cube and the MCP server verify the same token, so its role and branch_id are what every query is filtered by.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from . import users
from .agent import Identity

log = logging.getLogger(__name__)

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")
TOKEN_TTL_S = 8 * 3600
DEMO_PASSWORD = "demo123"
# Fixed demo logins are for local development and the test suite; production sets DEMO_LOGINS=false.
DEMO_LOGINS = os.getenv("DEMO_LOGINS", "true").lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class DemoUser:
    username: str
    role: str
    branch_id: int | None
    display_name: str
    is_admin: bool = False


DEMO_USERS = {
    "cmo": DemoUser("cmo", "cmo", None, "Chief Marketing Officer"),
    "branch_manager_dhaka": DemoUser("branch_manager_dhaka", "branch_manager", 7, "Branch Manager - Narayanganj (Dhaka)"),
    "analyst": DemoUser("analyst", "analyst", None, "Marketing Analyst"),
}


def issue_token(user: DemoUser) -> str:
    claims: dict[str, object] = {"sub": user.username, "role": user.role, "exp": int(time.time()) + TOKEN_TTL_S}
    if user.branch_id is not None:
        claims["branch_id"] = user.branch_id
    if user.is_admin:
        claims["admin"] = True
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


async def login(username: str, password: str) -> tuple[DemoUser, str]:
    account = None
    try:
        account = await users.authenticate(username, password)
    except Exception:  # database unreachable: only demo logins (if enabled) can work
        log.exception("account lookup failed")
    if account is not None:
        user = DemoUser(account["username"], account["role"], account["branch_id"], account["display_name"],
                        account["is_admin"])
        return user, issue_token(user)
    demo = DEMO_USERS.get(username) if DEMO_LOGINS else None
    if demo is None or password != DEMO_PASSWORD:
        raise HTTPException(401, "Invalid username or password")
    return demo, issue_token(demo)


def _claims(authorization: str | None) -> dict[str, object]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    try:
        return dict(jwt.decode(authorization.split(" ", 1)[1].strip(), JWT_SECRET, algorithms=["HS256"]))
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"Invalid token: {exc}") from exc


def identity_from(authorization: str | None) -> Identity:
    claims = _claims(authorization)
    token = authorization.split(" ", 1)[1].strip() if authorization else ""
    branch = claims.get("branch_id")
    branch_id = int(str(branch)) if branch is not None else None
    return Identity(str(claims.get("sub", "")), str(claims.get("role", "")), branch_id, token)


async def current_identity(authorization: Annotated[str | None, Header()] = None) -> Identity:
    """Valid token, and for managed accounts: still active with the same role/branch (changes apply at once)."""
    who = identity_from(authorization)
    try:
        account = await users.get(who.user)
    except Exception:  # database unreachable: fall back to the signed token alone
        log.exception("account lookup failed")
        return who
    if account is not None and (not account["active"] or (account["role"], account["branch_id"]) != (who.role, who.branch_id)):
        raise HTTPException(401, "Your access has changed. Please sign in again.")
    return who


async def current_admin(authorization: Annotated[str | None, Header()] = None) -> Identity:
    """Admin endpoints re-check the account in the database, so revoked admin rights apply immediately."""
    who = identity_from(authorization)
    account = await users.get(who.user)
    if not account or not account["active"] or not account["is_admin"]:
        raise HTTPException(403, "Only an administrator can manage users")
    return who


CurrentUser = Annotated[Identity, Depends(current_identity)]
AdminUser = Annotated[Identity, Depends(current_admin)]
