"""LLM provider adapters. This package is the only place provider SDKs may be imported."""

from __future__ import annotations

import os

from .base import AssistantTurn, LLMProvider, Message, ProviderError, ToolCall, ToolResult, ToolSpec


def create_provider(name: str | None = None) -> LLMProvider:
    """Select a provider from LLM_PROVIDER (gemini | anthropic) using only environment variables."""
    name = (name or os.getenv("LLM_PROVIDER") or "gemini").lower()
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(os.getenv("ANTHROPIC_API_KEY", ""), os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5"))
    raise ProviderError(f"Unknown LLM_PROVIDER '{name}'. Use 'gemini' or 'anthropic'.")


__all__ = ["AssistantTurn", "LLMProvider", "Message", "ProviderError", "ToolCall", "ToolResult", "ToolSpec",
           "create_provider"]
