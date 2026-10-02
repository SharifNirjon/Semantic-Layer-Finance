"""Record a real agent run (scripted oracle provider, live MCP + Cube data) as an SSE fixture for the UI tests."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "api"), str(ROOT / "tests" / "eval")]

from app.agent import Agent  # noqa: E402
from app.gateway import McpGateway  # noqa: E402
from oracle_provider import OracleProvider  # noqa: E402
from run_eval import identity  # noqa: E402

QUESTION_ID = "q06"
OUT = ROOT / "web" / "e2e" / "fixtures" / "chat-events.json"


async def main() -> None:
    questions = yaml.safe_load((ROOT / "tests" / "eval" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    q = next(x for x in questions if x["id"] == QUESTION_ID)
    gateway = McpGateway("http://localhost:8765/mcp")
    await gateway.discover()
    agent = Agent(OracleProvider([q]), gateway)  # type: ignore[arg-type]
    events = [e async for e in agent.run(q["question"], [], identity(q["role"]))]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"question": q["question"], "events": events}, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} with {len(events)} events")


if __name__ == "__main__":
    asyncio.run(main())
