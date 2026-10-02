"""Accounts created by an admin: Postgres table app.users, scrypt password hashes (stdlib only).

Each account carries the role (and branch) that Cube and the MCP server enforce through the JWT.
The first admin comes from ADMIN_USERNAME / ADMIN_PASSWORD in the environment.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime
from typing import Any

from . import db

log = logging.getLogger(__name__)

ROLES = ("cmo", "branch_manager", "analyst")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MIN_PASSWORD = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.users (
    username      text PRIMARY KEY,
    display_name  text NOT NULL,
    password_hash text NOT NULL,
    role          text NOT NULL CHECK (role IN ('cmo', 'branch_manager', 'analyst')),
    branch_id     integer,
    is_admin      boolean NOT NULL DEFAULT false,
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login    timestamptz,
    CHECK (role <> 'branch_manager' OR branch_id IS NOT NULL)
);
"""
PUBLIC_COLUMNS = "username, display_name, role, branch_id, is_admin, active, created_at, last_login"


class UserError(ValueError):
    """A request that breaks an account rule; the message is safe to show."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


def validate(role: str | None = None, branch_id: int | None = None, password: str | None = None,
             username: str | None = None) -> None:
    if username is not None and not USERNAME_RE.match(username):
        raise UserError("Username: 3-32 characters, lowercase letters, digits, dot, dash or underscore.")
    if role is not None and role not in ROLES:
        raise UserError(f"Role must be one of: {', '.join(ROLES)}.")
    if role == "branch_manager" and branch_id is None:
        raise UserError("A branch manager needs a branch.")
    if password is not None and len(password) < MIN_PASSWORD:
        raise UserError(f"Password must be at least {MIN_PASSWORD} characters.")


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items() if k != "password_hash"}


async def ensure_schema() -> None:
    """Create the table, and create or refresh the bootstrap admin from the environment."""
    for statement in filter(str.strip, SCHEMA_SQL.split(";")):  # one statement per execute (extended protocol)
        await db.run(statement)
    username, password = os.getenv("ADMIN_USERNAME", "").strip().lower(), os.getenv("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    try:
        validate(username=username, password=password)
    except UserError as exc:  # keep the API up; the admin account is simply not created
        log.error("ADMIN_USERNAME/ADMIN_PASSWORD rejected: %s", exc)
        return
    await db.run(
        "INSERT INTO app.users (username, display_name, password_hash, role, is_admin) VALUES (%s, %s, %s, 'cmo', true) "
        "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, is_admin = true, active = true",
        (username, os.getenv("ADMIN_DISPLAY_NAME", "Administrator"), hash_password(password)))


async def authenticate(username: str, password: str) -> dict[str, Any] | None:
    rows = await db.run("SELECT * FROM app.users WHERE username = %s AND active", (username.strip().lower(),), fetch=True)
    if not rows or not verify_password(password, rows[0]["password_hash"]):
        return None
    await db.run("UPDATE app.users SET last_login = now() WHERE username = %s", (rows[0]["username"],))
    return _public(rows[0])


async def get(username: str) -> dict[str, Any] | None:
    rows = await db.run(f"SELECT {PUBLIC_COLUMNS} FROM app.users WHERE username = %s", (username,), fetch=True)
    return _public(rows[0]) if rows else None


async def list_all() -> list[dict[str, Any]]:
    rows = await db.run(f"SELECT {PUBLIC_COLUMNS} FROM app.users ORDER BY created_at", fetch=True)
    return [_public(r) for r in rows]


async def create(username: str, display_name: str, password: str, role: str, branch_id: int | None,
                 is_admin: bool) -> dict[str, Any]:
    username = username.strip().lower()
    validate(role, branch_id, password, username)
    if await get(username):
        raise UserError(f"The username '{username}' is already taken.")
    await db.run(
        "INSERT INTO app.users (username, display_name, password_hash, role, branch_id, is_admin) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (username, display_name.strip() or username, hash_password(password), role,
         branch_id if role == "branch_manager" else None, is_admin))
    return await get(username) or {}


async def update(username: str, changes: dict[str, Any], acting_admin: str) -> dict[str, Any]:
    current = await get(username)
    if current is None:
        raise UserError(f"No user '{username}'.")
    if username == acting_admin and (changes.get("active") is False or changes.get("is_admin") is False):
        raise UserError("You cannot deactivate yourself or remove your own admin rights.")
    role = changes.get("role", current["role"])
    branch_id = changes.get("branch_id", current["branch_id"]) if role == "branch_manager" else None
    validate(role, branch_id, changes.get("password"))
    sets, params = ["role = %s", "branch_id = %s"], [role, branch_id]
    for column in ("display_name", "is_admin", "active"):
        if column in changes and changes[column] is not None:
            sets.append(f"{column} = %s")
            params.append(changes[column])
    if changes.get("password"):
        sets.append("password_hash = %s")
        params.append(hash_password(changes["password"]))
    await db.run(f"UPDATE app.users SET {', '.join(sets)} WHERE username = %s", (*params, username))
    return await get(username) or {}


async def delete(username: str, acting_admin: str) -> None:
    if username == acting_admin:
        raise UserError("You cannot delete your own account.")
    await db.run("DELETE FROM app.users WHERE username = %s", (username,))
