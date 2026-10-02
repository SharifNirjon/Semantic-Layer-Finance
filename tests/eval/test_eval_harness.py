"""Eval harness tests. Real-model runs are gated on API keys; the oracle run proves the pipeline end to end."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml
from conftest import JWT_SECRET
from run_eval import evaluate

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = yaml.safe_load((Path(__file__).with_name("questions.yaml")).read_text(encoding="utf-8"))["questions"]


def test_question_set_has_25_questions_with_adversarial_coverage():
    assert len(QUESTIONS) == 25
    assert len({q["id"] for q in QUESTIONS}) == 25
    adversarial = " ".join(q["question"].lower() for q in QUESTIONS if q["category"] == "adversarial")
    for needle in ("lifetime value", "sql", "gulshan", "ignore all previous instructions"):
        assert needle in adversarial
    assert {q["role"] for q in QUESTIONS} == {"cmo", "branch_manager", "analyst"}
    for q in QUESTIONS:
        assert q["expect"] and q["oracle"] is not None


def fake_response(**kw):
    from app.models import ChatResponse, Guardrail, Provenance, Table

    tables = kw.get("tables", [])
    return ChatResponse(
        answer_text=kw.get("text", "ok"), tables=tables, chart_spec=None,
        provenance=Provenance(metrics_used=kw.get("metrics", []), definitions=[], cube_queries=[], tool_call_ids=[],
                              tool_calls=kw.get("tool_calls", []), executed_as={}),
        follow_up_suggestions=[], guardrail=Guardrail(passed=kw.get("passed", True)), provider="x", model="y"), Table


def test_evaluator_flags_each_failure_mode():
    from app.models import Table

    t = Table(call_id="1", title="t", columns=["branch", "v"], rows=[{"branch": "Gulshan", "v": 100.0}],
              display_rows=[{"branch": "Gulshan", "v": "100"}])
    q = {"expect": {"metrics": ["m"], "dimensions": ["branch"], "values": [{"value": 999.0, "rel_tol": 1e-3}],
                    "answer_not_contains": ["secret"], "no_columns": ["v"], "only_branch": "Narayanganj",
                    "no_figures": True, "answer_contains_any": ["decline"]}}
    resp, _ = fake_response(text="the secret is 4.5%", tables=[t], passed=False)
    fails = " | ".join(evaluate(q, resp))
    for needle in ("guardrail", "metrics not used", "dimensions not used", "expected value", "forbidden text",
                   "forbidden columns", "other branches", "cites figures", "lacks any"):
        assert needle in fails, needle


def test_evaluator_passes_a_correct_answer():
    from app.models import Table

    t = Table(call_id="1", title="t", columns=["branch", "v"], rows=[{"branch": "Narayanganj", "v": 100.0}],
              display_rows=[{"branch": "Narayanganj", "v": "100"}])
    q = {"expect": {"metrics": ["m"], "values": [{"value": 100.05, "rel_tol": 1e-3}], "only_branch": "Narayanganj"}}
    resp, _ = fake_response(tables=[t], metrics=["m"])
    assert evaluate(q, resp) == []


@pytest.mark.integration
def test_oracle_run_passes_every_question(cube):
    port = 18766
    env = {**os.environ, "MCP_TRANSPORT": "http", "MCP_PORT": str(port), "JWT_SECRET": JWT_SECRET,
           "CUBE_URL": "http://localhost:4000"}
    server = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT / "mcp-server", env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"http://localhost:{port}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        run = subprocess.run([sys.executable, str(ROOT / "tests/eval/run_eval.py"), "--provider", "oracle",
                              "--min-pass-rate", "1.0", "--mcp-url", f"http://localhost:{port}/mcp"],
                             capture_output=True, text=True, env={**os.environ, "JWT_SECRET": JWT_SECRET}, timeout=600)
        assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1500:]
        assert "25/25" in run.stdout
    finally:
        server.kill()


@pytest.mark.llm
@pytest.mark.parametrize(("provider", "key"), [("gemini", "GEMINI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")])
def test_real_model_meets_the_pass_rate(provider, key, cube):
    if not os.getenv(key):
        pytest.skip(f"{key} is not set")
    port = 18767
    env = {**os.environ, "MCP_TRANSPORT": "http", "MCP_PORT": str(port), "JWT_SECRET": JWT_SECRET,
           "CUBE_URL": "http://localhost:4000"}
    server = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT / "mcp-server", env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(8)
        run = subprocess.run([sys.executable, str(ROOT / "tests/eval/run_eval.py"), "--provider", provider,
                              "--min-pass-rate", "0.9", "--delay", "5", "--mcp-url", f"http://localhost:{port}/mcp"],
                             capture_output=True, text=True, env=env, timeout=3000)
        assert run.returncode == 0, run.stdout[-4000:]
    finally:
        server.kill()
