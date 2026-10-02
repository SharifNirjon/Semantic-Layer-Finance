"""FastAPI service: login, SSE chat agent, dashboards, audit log, reconciliation."""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db, users
from .agent import Agent
from .auth import DEMO_LOGINS, DEMO_USERS, JWT_SECRET, AdminUser, CurrentUser, login
from .cache import ResponseCache
from .dashboard import Dashboards
from .demo_questions import DEMO_QUESTIONS
from .gateway import McpGateway
from .models import ChatRequest
from .providers import LLMProvider, ProviderError, create_provider

MCP_URL = os.getenv("MCP_URL", "http://localhost:8765/mcp")
CUBE_URL = os.getenv("CUBE_URL", "http://localhost:4000")
CACHE_PATH = Path(os.getenv("CACHE_DIR", "/tmp/copilot-cache")) / "demo_answers.json"


class State:
    gateway: McpGateway
    provider: LLMProvider | None = None
    provider_error: str | None = None
    cache: ResponseCache
    dashboards: Dashboards


state = State()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    state.gateway = McpGateway(MCP_URL)
    state.dashboards = Dashboards(state.gateway)
    state.cache = ResponseCache(CACHE_PATH)
    await users.ensure_schema()
    try:
        state.provider = create_provider()
    except ProviderError as exc:  # the API still serves dashboards and the audit log without an LLM key
        state.provider_error = str(exc)
    await state.gateway.discover()  # tools are discovered from the MCP server at startup
    yield


app = FastAPI(title="Governed Banking Analytics API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "tools": [t.name for t in state.gateway.tools], "llm_configured": state.provider is not None,
            "llm": {"provider": state.provider.name, "model": state.provider.model} if state.provider else None,
            "llm_error": state.provider_error}


class LoginRequest(BaseModel):
    username: str
    password: str


def session_payload(username: str, role: str, branch_id: int | None, display_name: str, is_admin: bool,
                    token: str | None = None) -> dict[str, Any]:
    body = {"username": username, "role": role, "branch_id": branch_id, "display_name": display_name, "is_admin": is_admin}
    return {"token": token, **body} if token else body


@app.post("/login")
async def login_endpoint(body: LoginRequest) -> dict[str, Any]:
    user, token = await login(body.username, body.password)
    return session_payload(user.username, user.role, user.branch_id, user.display_name, user.is_admin, token)


@app.get("/me")
async def me(who: CurrentUser) -> dict[str, Any]:
    account = await users.get(who.user)
    if account:
        if not account["active"]:
            raise HTTPException(401, "This account has been deactivated")
        return session_payload(who.user, account["role"], account["branch_id"], account["display_name"], account["is_admin"])
    demo = DEMO_USERS.get(who.user) if DEMO_LOGINS else None
    if demo is None:
        raise HTTPException(401, "Unknown account")
    return session_payload(demo.username, demo.role, demo.branch_id, demo.display_name, False)


@app.get("/demo-users")
async def demo_users() -> list[dict[str, Any]]:
    if not DEMO_LOGINS:
        return []
    return [{"username": u.username, "role": u.role, "display_name": u.display_name} for u in DEMO_USERS.values()]


# -- user administration ------------------------------------------------------------------------------------------
class NewUser(BaseModel):
    username: str
    display_name: str = ""
    password: str
    role: str
    branch_id: int | None = None
    is_admin: bool = False


class UserChanges(BaseModel):
    display_name: str | None = None
    password: str | None = None
    role: str | None = None
    branch_id: int | None = None
    is_admin: bool | None = None
    active: bool | None = None


@app.get("/admin/users")
async def admin_list_users(_: AdminUser) -> list[dict[str, Any]]:
    return await users.list_all()


@app.post("/admin/users", status_code=201)
async def admin_create_user(body: NewUser, _: AdminUser) -> dict[str, Any]:
    try:
        return await users.create(body.username, body.display_name, body.password, body.role, body.branch_id, body.is_admin)
    except users.UserError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/admin/users/{username}")
async def admin_update_user(username: str, body: UserChanges, who: AdminUser) -> dict[str, Any]:
    try:
        return await users.update(username, body.model_dump(exclude_unset=True), who.user)
    except users.UserError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/admin/users/{username}", status_code=204)
async def admin_delete_user(username: str, who: AdminUser) -> None:
    try:
        await users.delete(username, who.user)
    except users.UserError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/admin/branches")
async def admin_branches(_: AdminUser) -> list[dict[str, Any]]:
    """Branch ids and names for assigning a branch manager, read through the semantic layer."""
    token = jwt.encode({"sub": "admin-ui", "role": "cmo", "exp": int(time.time()) + 60}, JWT_SECRET, algorithm="HS256")
    query = {"dimensions": ["branches.branch_id", "branches.branch", "branches.region"], "order": {"branches.branch": "asc"}}
    async with httpx.AsyncClient(base_url=CUBE_URL, timeout=30) as http:
        for _attempt in range(10):
            r = await http.post("/cubejs-api/v1/load", headers={"Authorization": token}, json={"query": query})
            body = r.json()
            if body.get("error") != "Continue wait":
                break
            await asyncio.sleep(1)
    if r.status_code != 200 or "data" not in body:
        raise HTTPException(502, body.get("error", "Could not load branches"))
    return [{"branch_id": int(row["branches.branch_id"]), "branch": row["branches.branch"], "region": row["branches.region"]}
            for row in body["data"]]


@app.get("/suggestions")
async def suggestions(_: CurrentUser) -> list[str]:
    return DEMO_QUESTIONS


@app.get("/catalog")
async def catalog(who: CurrentUser) -> dict[str, Any]:
    rec = await state.gateway.call(who.token, "list_catalog", {})
    if rec.error or rec.result is None:
        raise HTTPException(502, rec.error)
    return rec.result


def sse(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


@app.post("/chat")
async def chat(body: ChatRequest, who: CurrentUser) -> StreamingResponse:
    if state.provider is None:
        raise HTTPException(503, state.provider_error or "No LLM provider configured. Set GEMINI_API_KEY in .env.")
    agent = Agent(state.provider, state.gateway, state.cache)

    async def stream() -> AsyncIterator[str]:
        started = time.perf_counter()
        calls, status, error = 0, "ok", None
        try:
            async for event in agent.run(body.question, body.history, who):
                if event["type"] == "tool_call":
                    calls += 1
                if event["type"] == "error":
                    status, error = "error", event["message"]
                if event["type"] == "final":
                    answer = event["response"]["answer_text"]
                    yield sse({"type": "answer_start"})
                    for i in range(0, len(answer), 24):  # progressive reveal of the validated answer
                        yield sse({"type": "answer_chunk", "text": answer[i:i + 24]})
                        await asyncio.sleep(0.012)
                yield sse(event)
        except Exception as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
            yield sse({"type": "error", "message": "Something went wrong while answering. Please try again."})
        finally:
            await db.record_chat(who.user, who.role, body.question, state.provider.name if state.provider else "",
                                 calls, int((time.perf_counter() - started) * 1000), status, error)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/dashboard/{view}")
async def dashboard(view: str, who: CurrentUser) -> dict[str, Any]:
    return await state.dashboards.view(who, view)


@app.get("/audit")
async def audit(who: CurrentUser, user: str | None = None, tool: str | None = None, status: str | None = None,
                hours: int | None = Query(None, ge=1, le=24 * 365), limit: int = Query(100, ge=1, le=500)
                ) -> dict[str, Any]:
    only = None if who.role == "cmo" else who.user  # only the CMO sees everyone's activity
    rows = await db.audit_entries(user, tool, status, hours, limit, only)
    return {"scope": "all users" if only is None else f"own activity ({who.user})", "entries": rows}


@app.get("/reconciliation")
async def reconciliation(who: CurrentUser) -> dict[str, Any]:
    result = await state.dashboards.reconciliation(who)
    result["injected_break_pct"] = await db.gl_break()
    return result


class ReconBreak(BaseModel):
    enabled: bool
    delta_pct: float = 0.35


@app.post("/admin/recon-break")
async def recon_break(body: ReconBreak, who: CurrentUser) -> dict[str, Any]:
    """Demo toggle: inject (or remove) a small GL discrepancy so the reconciliation visibly fails."""
    if who.role != "cmo":
        raise HTTPException(403, "Only the CMO demo user may toggle the reconciliation break")
    await db.set_gl_break(body.delta_pct if body.enabled else None)
    state.cache.clear()
    expected = "fail" if body.enabled else "pass"
    effective = False
    for _ in range(20):  # wait until the semantic layer reflects the change
        if (await state.dashboards.reconciliation(who))["overall"] == expected:
            effective = True
            break
        await asyncio.sleep(1)
    return {"enabled": body.enabled, "delta_pct": body.delta_pct if body.enabled else None, "effective": effective}
