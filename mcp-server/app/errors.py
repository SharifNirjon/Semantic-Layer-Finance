"""Errors that are safe and useful to show to the caller (and the LLM). ToolError messages reach the model verbatim."""

from __future__ import annotations

from mcp.server.mcpserver.exceptions import ToolError


class ToolInputError(ToolError):
    """The request is invalid; the message says how to fix it."""


class AccessDenied(ToolError):
    """The caller's role does not permit the request."""
