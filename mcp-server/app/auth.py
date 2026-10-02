"""Caller identity from the JWT. The raw token is forwarded to Cube, which enforces row and member security."""

from __future__ import annotations

from dataclasses import dataclass

import jwt

from .errors import AccessDenied

ROLES = {"cmo", "branch_manager", "analyst"}


@dataclass(frozen=True)
class Caller:
    user: str
    role: str
    branch_id: int | None
    token: str


def caller_from_token(token: str | None, secret: str) -> Caller:
    if not token:
        raise AccessDenied("Authentication required: send 'Authorization: Bearer <jwt>' (or set MCP_JWT for stdio).")
    try:
        claims = jwt.decode(token.removeprefix("Bearer ").strip(), secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AccessDenied(f"Invalid token: {exc}") from exc
    role = claims.get("role")
    if role not in ROLES:
        raise AccessDenied(f"Token role {role!r} is not one of {sorted(ROLES)}.")
    branch = claims.get("branch_id")
    return Caller(str(claims.get("sub", "unknown")), role, int(branch) if branch is not None else None,
                  token.removeprefix("Bearer ").strip())
