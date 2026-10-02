"""Admin-managed accounts: password hashing, rules, login and the admin endpoints' storage. DB tests need Postgres."""

from __future__ import annotations

import jwt
import psycopg
import pytest
from app import auth, db, users
from fastapi import HTTPException


def test_password_hash_round_trip_and_salting():
    h1, h2 = users.hash_password("correct horse"), users.hash_password("correct horse")
    assert h1 != h2  # random salt
    assert users.verify_password("correct horse", h1)
    assert not users.verify_password("wrong", h1)
    assert not users.verify_password("anything", "not-a-hash")


@pytest.mark.parametrize(("kwargs", "message"), [
    ({"username": "A"}, "Username"),
    ({"role": "ceo"}, "Role"),
    ({"role": "branch_manager", "branch_id": None}, "branch"),
    ({"password": "short"}, "at least"),
])
def test_account_rules(kwargs, message):
    with pytest.raises(users.UserError, match=message):
        users.validate(**kwargs)


def _db_available() -> bool:
    try:
        with psycopg.connect(db.dsn(), connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="needs Postgres (docker compose up -d postgres)")


@pytest.fixture
async def clean_users(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "boss")
    monkeypatch.setenv("ADMIN_PASSWORD", "boss-password")
    await users.ensure_schema()
    await db.run("DELETE FROM app.users WHERE username <> 'boss'")
    yield
    await db.run("DELETE FROM app.users WHERE username LIKE %s", ("test-%",))


@needs_db
async def test_bootstrap_admin_and_login_token(clean_users):
    user, token = await auth.login("boss", "boss-password")
    claims = jwt.decode(token, auth.JWT_SECRET, algorithms=["HS256"])
    assert (user.is_admin, claims["role"], claims["admin"]) == (True, "cmo", True)
    with pytest.raises(HTTPException):
        await auth.login("boss", "wrong-password")


@needs_db
async def test_branch_manager_token_carries_the_branch(clean_users):
    await users.create("test-bm", "Test BM", "bm-password", "branch_manager", 7, False)
    _, token = await auth.login("test-bm", "bm-password")
    claims = jwt.decode(token, auth.JWT_SECRET, algorithms=["HS256"])
    assert (claims["role"], claims["branch_id"], "admin" in claims) == ("branch_manager", 7, False)
    identity = await auth.current_identity(f"Bearer {token}")
    assert (identity.user, identity.role, identity.branch_id) == ("test-bm", "branch_manager", 7)
    await users.update("test-bm", {"branch_id": 3}, "boss")  # reassigned: the old token stops working at once
    with pytest.raises(HTTPException, match="sign in again"):
        await auth.current_identity(f"Bearer {token}")


@needs_db
async def test_deactivated_and_deleted_accounts_cannot_sign_in(clean_users):
    await users.create("test-analyst", "", "analyst-pass", "analyst", None, False)
    await users.update("test-analyst", {"active": False}, "boss")
    with pytest.raises(HTTPException):
        await auth.login("test-analyst", "analyst-pass")
    await users.delete("test-analyst", "boss")
    assert await users.get("test-analyst") is None


@needs_db
async def test_admin_cannot_lock_themselves_out_and_duplicates_are_rejected(clean_users):
    with pytest.raises(users.UserError):
        await users.update("boss", {"active": False}, "boss")
    with pytest.raises(users.UserError):
        await users.delete("boss", "boss")
    await users.create("test-dup", "", "dup-password", "analyst", None, False)
    with pytest.raises(users.UserError, match="taken"):
        await users.create("test-dup", "", "dup-password", "analyst", None, False)


@needs_db
async def test_admin_check_reads_the_database(clean_users):
    await users.create("test-plain", "", "plain-password", "cmo", None, False)
    _, token = await auth.login("test-plain", "plain-password")
    with pytest.raises(HTTPException) as err:
        await auth.current_admin(f"Bearer {token}")
    assert err.value.status_code == 403
    _, admin_token = await auth.login("boss", "boss-password")
    assert (await auth.current_admin(f"Bearer {admin_token}")).user == "boss"


@needs_db
async def test_password_change_and_role_change(clean_users):
    await users.create("test-change", "", "first-password", "branch_manager", 3, False)
    updated = await users.update("test-change", {"role": "analyst", "password": "second-password"}, "boss")
    assert (updated["role"], updated["branch_id"]) == ("analyst", None)
    user, _ = await auth.login("test-change", "second-password")
    assert user.role == "analyst"
