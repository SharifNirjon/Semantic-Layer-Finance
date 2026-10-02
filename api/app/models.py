"""Pydantic models for the structured chat response."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChartSpec(BaseModel):
    type: Literal["line", "bar", "pie", "none"] = "none"
    x: str = ""
    y: list[str] = Field(default_factory=list)
    series: str | None = None
    title: str = ""
    source_call_id: str = ""


class AgentAnswer(BaseModel):
    """What the LLM must return (validated; one retry on malformed output)."""

    answer_text: str = Field(min_length=1)
    chart_spec: ChartSpec | None = None
    follow_up_suggestions: list[str] = Field(default_factory=list, max_length=4)


class Table(BaseModel):
    call_id: str
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]  # raw values (used for charts)
    display_rows: list[dict[str, str]]  # formatted values (shown to people)
    metric: str | None = None  # set for comparison tables, whose value columns are period_a / period_b / change


class Provenance(BaseModel):
    metrics_used: list[str]
    definitions: list[dict[str, Any]]
    cube_queries: list[dict[str, Any]]
    tool_call_ids: list[str]
    tool_calls: list[dict[str, Any]]
    executed_as: dict[str, Any]


class ChartPayload(ChartSpec):
    data: list[dict[str, Any]] = Field(default_factory=list)


class Guardrail(BaseModel):
    passed: bool
    retried: bool = False
    unsupported_numbers: list[str] = Field(default_factory=list)
    cached: bool = False


class ChatResponse(BaseModel):
    answer_text: str
    tables: list[Table]
    chart_spec: ChartPayload | None
    provenance: Provenance
    follow_up_suggestions: list[str]
    guardrail: Guardrail
    provider: str
    model: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
