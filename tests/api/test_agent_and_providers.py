"""Agent loop, guardrail, retries, cache and provider adapters. No network, no Cube, no LLM key."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from app.agent import Agent, Identity
from app.cache import ResponseCache
from app.gateway import ToolRecord
from app.guardrail import unsupported_numbers
from app.providers import (
    AssistantTurn,
    Message,
    ProviderError,
    ToolCall,
    ToolSpec,
    create_provider,
)
from app.providers.common import inline_schema, with_backoff

ROOT = Path(__file__).resolve().parents[2]
CMO = Identity("cmo", "cmo", None, "tok")
QUESTION = "Why did Young Professionals churn rise last quarter?"
QUERY_ARGS = {"metrics": ["churn_rate"], "dimensions": ["segment"],
              "date_range": {"start": "2026-07-01", "end": "2026-09-30"}}


def churn_result() -> dict[str, Any]:
    return {
        "columns": ["segment", "churn_rate"],
        "rows": [{"segment": "Young Professionals", "churn_rate": 0.02612}, {"segment": "Retail", "churn_rate": 0.00731}],
        "display_rows": [{"segment": "Young Professionals", "churn_rate": "2.61%"},
                         {"segment": "Retail", "churn_rate": "0.73%"}],
        "notes": ["churn_rate: totals over 2026-07-01..2026-09-30."], "truncated": False, "total_rows": 2,
        "provenance": {"metrics": [{"name": "churn_rate", "title": "Churn rate (monthly)",
                                    "definition": "Customers churned divided by monthly opening customers.",
                                    "unit": "percent", "time_semantics": "flow", "owner": "x", "source_tables": [],
                                    "description": "", "caveats": None}],
                       "cube_queries": [{"measures": ["customers.churn_rate"]}], "executed_as": {}},
    }


class FakeGateway:
    def __init__(self) -> None:
        self.tools = [ToolSpec("query_metrics", "q", {"type": "object", "properties": {}})]
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, token: str, name: str, arguments: dict[str, Any], call_id: str = "") -> ToolRecord:
        self.calls.append((name, arguments))
        return ToolRecord(call_id or name, name, arguments, result=churn_result(), latency_ms=3)


class ScriptedProvider:
    name, model = "fake", "fake-1"

    def __init__(self, json_outputs: list[str]) -> None:
        self.turns = [AssistantTurn("", [ToolCall("c1", "query_metrics", QUERY_ARGS)]), AssistantTurn("done", [])]
        self.json_outputs = list(json_outputs)
        self.json_calls: list[list[Message]] = []

    async def generate(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        return self.turns.pop(0)

    async def generate_json(self, system: str, messages: list[Message], schema: dict[str, Any]) -> str:
        self.json_calls.append(messages)
        return self.json_outputs.pop(0)


def answer(text: str, chart: dict | None = None) -> str:
    return json.dumps({"answer_text": text, "chart_spec": chart, "follow_up_suggestions": ["What about Student churn?"]})


GOOD = ("Young Professionals churn reached 2.61% a month in Q3 2026 (Jul-Sep), versus 0.73% for Retail. "
        "Definition: customers churned divided by monthly opening customers. Suggested action: launch a retention offer.")
CHART = {"type": "bar", "x": "segment", "y": ["churn_rate"], "series": None, "title": "Churn", "source_call_id": "c1"}


async def test_happy_path_builds_tables_chart_and_provenance():
    agent = Agent(ScriptedProvider([answer(GOOD, CHART)]), FakeGateway())  # type: ignore[arg-type]
    resp = await agent.ask(QUESTION, CMO)
    assert resp.guardrail.passed and not resp.guardrail.retried
    assert resp.tables[0].display_rows[0]["churn_rate"] == "2.61%"
    assert resp.chart_spec and resp.chart_spec.type == "bar" and len(resp.chart_spec.data) == 2
    assert resp.provenance.metrics_used == ["churn_rate"]
    assert resp.provenance.tool_call_ids == ["c1"] and resp.provenance.cube_queries
    assert resp.follow_up_suggestions == ["What about Student churn?"]
    assert (resp.provider, resp.model) == ("fake", "fake-1")


async def test_malformed_output_is_retried_once():
    provider = ScriptedProvider(["not json at all", answer(GOOD)])
    resp = await Agent(provider, FakeGateway()).ask(QUESTION, CMO)  # type: ignore[arg-type]
    assert resp.guardrail.passed and resp.guardrail.retried
    assert "not valid" in provider.json_calls[1][-1].text


async def test_malformed_twice_falls_back_to_safe_message():
    resp = await Agent(ScriptedProvider(["nope", "{}"]), FakeGateway()).ask(QUESTION, CMO)  # type: ignore[arg-type]
    assert not resp.guardrail.passed and "could not verify" in resp.answer_text
    assert resp.tables  # governed data still shown


async def test_invented_figure_triggers_retry_then_passes():
    bad = GOOD.replace("0.73%", "1.9%")
    provider = ScriptedProvider([answer(bad), answer(GOOD)])
    resp = await Agent(provider, FakeGateway()).ask(QUESTION, CMO)  # type: ignore[arg-type]
    assert resp.guardrail.passed and resp.guardrail.retried and "0.73%" in resp.answer_text
    assert "1.9%" in provider.json_calls[1][-1].text


async def test_persistent_invented_figure_falls_back():
    bad = GOOD.replace("0.73%", "1.9%")
    resp = await Agent(ScriptedProvider([answer(bad), answer(bad)]), FakeGateway()).ask(QUESTION, CMO)  # type: ignore[arg-type]
    assert not resp.guardrail.passed and resp.guardrail.unsupported_numbers == ["1.9%"]
    assert "1.9%" not in resp.answer_text and resp.chart_spec is None


async def test_invalid_chart_columns_fall_back_to_a_sensible_default():
    bad_chart = {**CHART, "x": "no_such_column"}
    resp = await Agent(ScriptedProvider([answer(GOOD, bad_chart)]), FakeGateway()).ask(QUESTION, CMO)  # type: ignore[arg-type]
    assert resp.chart_spec and resp.chart_spec.x == "segment" and resp.chart_spec.y == ["churn_rate"]


async def test_demo_question_answers_are_cached(tmp_path):
    cache = ResponseCache(tmp_path / "c.json")
    first = ScriptedProvider([answer(GOOD)])
    await Agent(first, FakeGateway(), cache).ask(QUESTION, CMO)  # type: ignore[arg-type]
    second = ScriptedProvider([])  # would raise if the model were called
    hit = await Agent(second, FakeGateway(), cache).ask(QUESTION.lower(), CMO)  # type: ignore[arg-type]
    assert hit.guardrail.cached and hit.answer_text == GOOD
    other_role = Identity("bm", "branch_manager", 7, "t")
    assert cache.get(first, other_role, QUESTION) is None  # cache is per role/branch
    assert cache.get(first, CMO, "an ad hoc question") is None  # only the fixed demo questions are cached


# -- guardrail ----------------------------------------------------------------------------------------------------------
SOURCES = [{"display_rows": [{"v": "BDT 29.43 billion", "r": "48.68%", "n": "140,753"}]},
           {"rows": [{"v": 29434831921.89, "r": 0.4868296, "n": 140753}]}, {"definition": "last 90 days"}]


@pytest.mark.parametrize("text", [
    "Deposits were BDT 29.43 billion (48.68% CASA) in Q3 2026.",
    "Deposits were about 29.4 billion and CASA about 48.7%.",
    "There were 140,753 transactions in the 90 days to 2026-09-30, up from March 2026.",
    "Top 3 segments, 2 of them growing.",  # small counts are prose, not figures
])
def test_guardrail_accepts_supported_figures(text):
    assert unsupported_numbers(text, SOURCES) == []


@pytest.mark.parametrize(("text", "bad"), [
    ("CASA is 51.2%.", ["51.2%"]),
    ("Deposits reached BDT 31 billion.", ["31 billion"]),
    ("About 150,000 transactions.", ["150,000"]),
])
def test_guardrail_rejects_invented_figures(text, bad):
    assert [b.replace("BDT ", "") for b in unsupported_numbers(text, SOURCES)] == bad


# -- providers ------------------------------------------------------------------------------------------------------------
def test_inline_schema_resolves_refs_and_nullable():
    schema = {"$defs": {"R": {"type": "object", "title": "R", "properties": {
        "start": {"type": "string", "format": "date"}}}},
        "type": "object", "properties": {
            "r": {"$ref": "#/$defs/R"}, "g": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}}}
    out = inline_schema(schema)
    assert out["properties"]["r"]["properties"]["start"] == {"type": "string", "description": "(format YYYY-MM-DD)"}
    assert out["properties"]["g"] == {"type": "string"} and "$defs" not in out


async def test_backoff_retries_rate_limits_and_gives_up_on_fatal_errors():
    attempts, sleeps = [], []

    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("429")
        return "ok"

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    assert await with_backoff(flaky, lambda e: 0.0 if "429" in str(e) else None, fake_sleep) == "ok"
    assert len(attempts) == 3 and sleeps[1] > sleeps[0]  # exponential

    async def fatal() -> str:
        raise ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        await with_backoff(fatal, lambda e: None, fake_sleep)


def test_gemini_adapter_translates_tools_and_history():
    from app.providers.gemini import GeminiProvider
    from app.providers.base import ToolResult

    spec = ToolSpec("query_metrics", "desc", {"$defs": {}, "type": "object", "properties": {"limit": {"type": "integer"}}})
    tools = GeminiProvider.to_tools([spec])
    decl = tools[0].function_declarations[0]
    assert decl.name == "query_metrics" and decl.parameters_json_schema["properties"]["limit"]["type"] == "integer"
    msgs = [Message("user", "hi"),
            Message("assistant", "", [ToolCall("c1", "query_metrics", {"limit": 1})]),
            Message("tool", tool_results=[ToolResult("c1", "query_metrics", json.dumps({"a": 1}))])]
    contents = GeminiProvider.to_contents(msgs)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].function_call.name == "query_metrics"
    assert contents[2].parts[0].function_response.response == {"result": {"a": 1}}


def test_anthropic_adapter_translates_tools_and_history():
    from app.providers.anthropic_provider import AnthropicProvider
    from app.providers.base import ToolResult

    msgs = [Message("user", "hi"), Message("assistant", "ok", [ToolCall("c1", "t", {"x": 1})]),
            Message("tool", tool_results=[ToolResult("c1", "t", "{}", True)])]
    out = AnthropicProvider.to_messages(msgs)
    assert out[1]["content"][1] == {"type": "tool_use", "id": "c1", "name": "t", "input": {"x": 1}}
    assert out[2]["content"][0] == {"type": "tool_result", "tool_use_id": "c1", "content": "{}", "is_error": True}
    tools = AnthropicProvider.to_tools([ToolSpec("t", "d", {"type": "object", "properties": {}})])
    assert tools[0]["input_schema"]["type"] == "object"


def test_provider_factory_uses_only_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(ProviderError, match="Unknown LLM_PROVIDER"):
        create_provider()
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        create_provider()
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-x")
    assert create_provider().model == "gemini-x"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-x")
    assert create_provider().model == "claude-x"


def test_no_provider_specific_code_outside_the_providers_package():
    pattern = re.compile(r"google\.genai|from google import genai|import anthropic|from anthropic|gemini|claude", re.I)
    offenders = []
    for base in ("api/app", "mcp-server/app", "web/src"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "providers" in path.parts:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line) and not line.lstrip().startswith(("#", '"""')):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    # provider *names* in env/config plumbing are allowed; SDK usage is not
    offenders = [o for o in offenders if re.search(r"genai|import anthropic|from anthropic", o)]
    assert not offenders, offenders
