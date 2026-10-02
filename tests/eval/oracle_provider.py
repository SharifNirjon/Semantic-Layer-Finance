"""A scripted stand-in for an LLM, used ONLY to self-test the eval harness and the agent pipeline.

It replays the `oracle.calls` stored with each question and writes a templated answer from the tool results. Its pass
rate says nothing about model quality; it proves the harness, the MCP path, the guardrail and the checks work end to end.
"""

from __future__ import annotations

import json
from typing import Any

from app.providers import AssistantTurn, Message, ToolCall, ToolSpec

DECLINE = ("I can't provide that: this assistant only answers from governed metrics and cannot run SQL, list customers "
           "or show data your role is restricted from. Suggested action: ask about a catalogued metric, for example "
           "churn rate or deposits by segment.")


class OracleProvider:
    name = "oracle"
    model = "scripted-oracle"

    def __init__(self, questions: list[dict[str, Any]]) -> None:
        self._by_question = {q["question"]: q["oracle"] for q in questions}

    def _question(self, messages: list[Message]) -> str:
        return next(m.text for m in messages if m.role == "user" and m.text in self._by_question)

    async def generate(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        if any(m.role == "tool" for m in messages):
            return AssistantTurn("", [])
        plan = self._by_question[self._question(messages)]
        calls = [ToolCall(f"call_{i}", c["tool"], c["arguments"]) for i, c in enumerate(plan["calls"])]
        return AssistantTurn("", calls)

    async def generate_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> str:
        prompt = messages[0].text
        question = prompt.split("\n", 1)[0].removeprefix("Question: ")
        plan = self._by_question[question]
        results = json.loads(prompt.split("Tool results (JSON):\n", 1)[1])
        usable = [r for r in results if not r.get("error")]
        if plan.get("decline") or not usable:
            text = DECLINE
        else:
            first = usable[0]
            rows = first.get("display_rows") or first.get("top_increases") or []
            row = rows[0] if rows else {}
            facts = ", ".join(f"{k} is {v}" for k, v in row.items())
            definition = (first.get("metric_definitions") or [{"definition": "see metric dictionary"}])[0]["definition"]
            text = (f"For the requested period the leading result is {facts}. Definition: {definition} "
                    "Suggested action: review the trend with the relevant owner.")
        follow_ups = ["What changed versus last quarter?"]
        return json.dumps({"answer_text": text, "chart_spec": None, "follow_up_suggestions": follow_ups})
