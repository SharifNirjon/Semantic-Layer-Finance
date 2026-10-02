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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db
from .agent import Agent
from .auth import DEMO_USERS, CurrentUser, login
from .cache import ResponseCache
from .dashboard import Dashboards
from .demo_questions import DEMO_QUESTIONS
from .gateway import McpGateway
from .models import ChatRequest
from .providers import LLMProvider, ProviderError, create_provider

MCP_URL = os.getenv("MCP_URL", "http://localhost:8765/mcp")
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


@app.post("/login")
async def login_endpoint(body: LoginRequest) -> dict[str, Any]:
    user, token = login(body.username, body.password)
    return {"token": token, "username": user.username, "role": user.role, "branch_id": user.branch_id,
            "display_name": user.display_name}


@app.get("/demo-users")
async def demo_users() -> list[dict[str, Any]]:
    return [{"username": u.username, "role": u.role, "display_name": u.display_name} for u in DEMO_USERS.values()]


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
    return {"enabled": body.enabled, "delta_pct": body.delta_pct if body.enabled else None}
