"""Anthropic Claude adapter (Messages API with client tools and native structured output)."""

from __future__ import annotations

from typing import Any

import anthropic

from .base import AssistantTurn, Message, ProviderError, ToolCall, ToolSpec
from .common import inline_schema, with_backoff

MAX_TOKENS = 16000


def _retry_hint(exc: Exception) -> float | None:
    if isinstance(exc, anthropic.RateLimitError):
        try:
            return float(exc.response.headers.get("retry-after", 0))
        except (TypeError, ValueError):
            return 0.0
    if isinstance(exc, anthropic.APIConnectionError) or (
            isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500):
        return 0.0
    return None


def _strict_objects(schema: Any) -> Any:
    """Structured output requires additionalProperties: false on every object."""
    if isinstance(schema, dict):
        out = {k: _strict_objects(v) for k, v in schema.items()}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [_strict_objects(v) for v in schema]
    return schema


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, client: anthropic.AsyncAnthropic | None = None) -> None:
        if not api_key and client is None:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    @staticmethod
    def to_messages(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.text})
            elif m.role == "assistant":
                if m.provider_state is not None:  # keeps any thinking blocks intact between turns
                    out.append({"role": "assistant", "content": m.provider_state})
                    continue
                blocks: list[dict[str, Any]] = [{"type": "text", "text": m.text}] if m.text else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                           for c in m.tool_calls]
                out.append({"role": "assistant", "content": blocks})
            else:  # all results of one assistant turn go in a single user message
                out.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content, "is_error": r.is_error}
                    for r in m.tool_results]})
        return out

    @staticmethod
    def to_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "input_schema": inline_schema(t.input_schema)}
                for t in tools]

    async def generate(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        response = await self._create(system=system, messages=self.to_messages(messages),
                                      tools=self.to_tools(tools))
        if response.stop_reason == "refusal":
            raise ProviderError("The model declined to answer this request.")
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        return AssistantTurn(text, calls, provider_state=response.content)

    async def generate_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> str:
        response = await self._create(
            system=system, messages=self.to_messages(messages),
            output_config={"format": {"type": "json_schema", "schema": _strict_objects(inline_schema(schema))}})
        if response.stop_reason == "refusal":
            raise ProviderError("The model declined to answer this request.")
        return next((b.text for b in response.content if b.type == "text"), "")

    async def _create(self, **kwargs: Any) -> Any:
        return await with_backoff(
            lambda: self._client.messages.create(model=self.model, max_tokens=MAX_TOKENS, **kwargs), _retry_hint)


