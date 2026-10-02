"""Provider-neutral tool-calling types. The agent only ever sees these; adapters translate them per provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ToolSpec:
    """A tool as the agent sees it: name, description and a JSON-schema for the arguments (from MCP)."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    content: str  # JSON text shown to the model
    is_error: bool = False


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # role == assistant
    tool_results: list[ToolResult] = field(default_factory=list)  # role == tool
    provider_state: Any = None  # opaque round-trip data an adapter attaches to its own assistant turns


@dataclass
class AssistantTurn:
    text: str
    tool_calls: list[ToolCall]
    provider_state: Any = None

    def as_message(self) -> Message:
        return Message("assistant", self.text, self.tool_calls, provider_state=self.provider_state)


class ProviderError(Exception):
    """Raised after retries are exhausted or for non-retryable provider failures."""


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        """One model turn with tools available."""

    async def generate_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> str:
        """One tool-less turn constrained (or instructed) to return JSON matching `schema`; returns the JSON text."""
