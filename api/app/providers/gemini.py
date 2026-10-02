"""Google Gemini adapter (google-genai SDK, generate_content with manual function calling)."""

from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import errors, types

from .base import AssistantTurn, Message, ProviderError, ToolCall, ToolSpec
from .common import inline_schema, with_backoff


def _retry_hint(exc: Exception) -> float | None:
    """Seconds to wait for rate limits / server errors; None for errors that retrying cannot fix."""
    if isinstance(exc, errors.ServerError):
        return 0.0
    if isinstance(exc, errors.ClientError) and exc.code == 429:
        match = re.search(r"retry in ([\d.]+)s", str(exc)) or re.search(r"'retryDelay': '([\d.]+)s'", str(exc))
        return float(match.group(1)) if match else 0.0
    return None


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, client: genai.Client | None = None) -> None:
        if not api_key and client is None:
            raise ProviderError("GEMINI_API_KEY is not set")
        self.model = model
        self._client = client or genai.Client(api_key=api_key)

    # -- translation ---------------------------------------------------------------------------------------------
    @staticmethod
    def to_contents(messages: list[Message]) -> list[types.Content]:
        contents: list[types.Content] = []
        for m in messages:
            if m.role == "user":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m.text)]))
            elif m.role == "assistant":
                if m.provider_state is not None:  # keeps thought signatures intact between turns
                    contents.append(m.provider_state)
                    continue
                parts = [types.Part.from_text(text=m.text)] if m.text else []
                parts += [types.Part(function_call=types.FunctionCall(name=c.name, args=c.arguments, id=c.id))
                          for c in m.tool_calls]
                contents.append(types.Content(role="model", parts=parts))
            else:
                contents.append(types.Content(role="user", parts=[
                    types.Part(function_response=types.FunctionResponse(
                        id=r.call_id, name=r.name,
                        response={"error": r.content} if r.is_error else {"result": json.loads(r.content)}))
                    for r in m.tool_results]))
        return contents

    @staticmethod
    def to_tools(tools: list[ToolSpec]) -> list[Any]:
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(name=t.name, description=t.description,
                                      parameters_json_schema=inline_schema(t.input_schema))
            for t in tools])]

    # -- LLMProvider ---------------------------------------------------------------------------------------------
    async def generate(self, system: str, messages: list[Message], tools: list[ToolSpec]):
        config = types.GenerateContentConfig(
            system_instruction=system, tools=self.to_tools(tools), temperature=0.0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
        response = await self._call(self.to_contents(messages), config)
        if not response.candidates or not response.candidates[0].content:
            raise ProviderError(f"Gemini returned no content (finish reason: "
                                f"{response.candidates[0].finish_reason if response.candidates else 'none'})")
        content = response.candidates[0].content
        text, calls = "", []
        for i, part in enumerate(content.parts or []):
            if part.function_call:
                fc = part.function_call
                calls.append(ToolCall(fc.id or f"call_{i}_{fc.name}", fc.name or "", dict(fc.args or {})))
            elif part.text and not part.thought:
                text += part.text
        return AssistantTurn(text, calls, provider_state=content)

    async def generate_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system, temperature=0.0, response_mime_type="application/json",
            response_json_schema=inline_schema(schema))
        response = await self._call(self.to_contents(messages), config)
        return response.text or ""

    async def _call(self, contents: list[types.Content], config: types.GenerateContentConfig):
        return await with_backoff(
            lambda: self._client.aio.models.generate_content(model=self.model, contents=contents, config=config),
            _retry_hint)
