"""LLM agent: tool-use loop over MCP, structured final answer, number guardrail. Provider-agnostic."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .cache import ResponseCache
from .gateway import McpGateway, ToolRecord
from .guardrail import unsupported_numbers
from .models import AgentAnswer, ChatResponse, Guardrail
from .prompts import COMPOSE_PROMPT, SYSTEM_PROMPT
from .providers import LLMProvider, Message, ProviderError, ToolResult
from .results import llm_text, llm_view, provenance_from, resolve_chart, tables_from

MAX_STEPS = 6
SAFE_MESSAGE = ("I could not verify every figure in my draft answer against the governed data, so I am not showing a "
                "narrative. The certified results are in the table below; ask me to focus on one metric or period.")
Event = dict[str, Any]


@dataclass(frozen=True)
class Identity:
    user: str
    role: str
    branch_id: int | None
    token: str

    @property
    def scope(self) -> dict[str, Any]:
        return {"user": self.user, "role": self.role, "branch_id": self.branch_id}


def parse_answer(text: str) -> AgentAnswer:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return AgentAnswer.model_validate_json(cleaned)


def guardrail_sources(records: list[ToolRecord]) -> list[Any]:
    """Everything a model may legitimately quote: formatted values, raw values, definitions and notes."""
    sources: list[Any] = []
    for rec in records:
        if rec.error or not rec.result:
            continue
        sources.append(llm_view(rec))
        sources.append({k: rec.result[k] for k in ("rows", "top_increases", "top_decreases") if k in rec.result})
    return sources


class Agent:
    def __init__(self, provider: LLMProvider, gateway: McpGateway, cache: ResponseCache | None = None) -> None:
        self.provider = provider
        self.gateway = gateway
        self.cache = cache

    def _system(self, who: Identity) -> str:
        scope = f"\n\nSigned-in role: {who.role}."
        if who.role == "branch_manager":
            scope += " The signed-in user can only see their own branch; results are already restricted to it."
        if who.role == "analyst":
            scope += " The signed-in user cannot access customer-level data."
        return SYSTEM_PROMPT + scope

    async def run(self, question: str, history: list[dict[str, str]], who: Identity) -> AsyncIterator[Event]:
        if self.cache and (hit := self.cache.get(self.provider, who, question)):
            yield {"type": "status", "message": "Answer served from the demo cache"}
            yield {"type": "final", "response": hit.model_dump(mode="json")}
            return
        records: list[ToolRecord] = []
        try:
            messages = [Message(h["role"] if h["role"] in ("user", "assistant") else "user", h["text"])  # type: ignore[arg-type]
                        for h in history if h.get("text")]
            messages.append(Message("user", question))
            tools = self.gateway.tools
            for step in range(MAX_STEPS):
                yield {"type": "status", "message": "Thinking" if step == 0 else "Reviewing results"}
                turn = await self.provider.generate(self._system(who), messages, tools)
                if not turn.tool_calls:
                    break
                messages.append(turn.as_message())
                for call in turn.tool_calls:
                    yield {"type": "tool_call", "id": call.id, "name": call.name, "arguments": call.arguments}
                batch = await asyncio.gather(*(self.gateway.call(who.token, c.name, c.arguments, c.id)
                                               for c in turn.tool_calls))
                results = []
                for rec in batch:
                    records.append(rec)
                    ok = rec.error is None
                    count = len((rec.result or {}).get("rows", [])) if ok else 0
                    yield {"type": "tool_result", "id": rec.call_id, "name": rec.name, "ok": ok, "rows": count,
                           "latency_ms": rec.latency_ms, "error": rec.error}
                    results.append(ToolResult(rec.call_id, rec.name, json.dumps(llm_view(rec)), not ok))
                messages.append(Message("tool", tool_results=results))
            yield {"type": "status", "message": "Writing the answer"}
            response = await self._compose(question, history, records, who)
        except ProviderError as exc:
            yield {"type": "error", "message": f"The language model is unavailable: {exc}"}
            return
        if self.cache and response.guardrail.passed:
            self.cache.put(self.provider, who, question, response)
        yield {"type": "final", "response": response.model_dump(mode="json")}

    async def ask(self, question: str, who: Identity, history: list[dict[str, str]] | None = None) -> ChatResponse:
        """Run to completion (used by the eval runner and tests)."""
        final: ChatResponse | None = None
        async for event in self.run(question, history or [], who):
            if event["type"] == "final":
                final = ChatResponse.model_validate(event["response"])
            elif event["type"] == "error":
                raise ProviderError(event["message"])
        assert final is not None
        return final

    async def _compose(self, question: str, history: list[dict[str, str]], records: list[ToolRecord],
                       who: Identity) -> ChatResponse:
        context = "\n".join(f"{h['role']}: {h['text']}" for h in history[-6:] if h.get("text"))
        prompt = (f"Question: {question}\n\n" + (f"Earlier conversation:\n{context}\n\n" if context else "")
                  + f"Signed-in role: {who.role}\n\nTool results (JSON):\n{llm_text(records)}")
        schema = AgentAnswer.model_json_schema()
        sources = guardrail_sources(records)
        feedback: str | None = None
        last = ""
        parse_retried = guard_retried = False
        answer: AgentAnswer | None = None
        unsupported: list[str] = []
        while True:
            messages = [Message("user", prompt)]
            if feedback:
                messages += [Message("assistant", last), Message("user", feedback)]
            last = await self.provider.generate_json(COMPOSE_PROMPT, messages, schema)
            try:
                answer = parse_answer(last)
            except (ValidationError, ValueError) as exc:
                if parse_retried:
                    answer = None
                    break
                parse_retried = True
                feedback = f"That output was not valid for the schema ({str(exc)[:300]}). Return valid JSON only."
                continue
            unsupported = unsupported_numbers(answer.answer_text, sources)
            if not unsupported:
                break
            if guard_retried:
                answer = None
                break
            guard_retried = True
            feedback = ("These figures in answer_text do not appear in the tool results: "
                        f"{', '.join(unsupported)}. Rewrite using only figures exactly as shown in the results, "
                        "or leave them out.")
        tables = tables_from(records)
        passed = answer is not None
        final = answer or AgentAnswer(answer_text=SAFE_MESSAGE, follow_up_suggestions=[])
        return ChatResponse(
            answer_text=final.answer_text, tables=tables,
            chart_spec=resolve_chart(final.chart_spec, tables) if passed else None,
            provenance=provenance_from(records, who.scope), follow_up_suggestions=final.follow_up_suggestions,
            guardrail=Guardrail(passed=passed, retried=parse_retried or guard_retried,
                                unsupported_numbers=[] if passed else unsupported),
            provider=self.provider.name, model=self.provider.model)
