"""Evaluation runner.

    python tests/eval/run_eval.py --provider gemini [--ids q01,q05] [--delay 6] [--min-pass-rate 0.9]

`--provider oracle` replays scripted tool calls (harness self-test, not a model score). Needs the stack running
(Cube + MCP server) and, for real providers, the matching API key in the environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import jwt
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "api"), str(Path(__file__).parent)]

from app.agent import Agent, Identity  # noqa: E402
from app.gateway import McpGateway  # noqa: E402
from app.guardrail import cited_numbers  # noqa: E402
from app.models import ChatResponse  # noqa: E402
from app.providers import ProviderError, create_provider  # noqa: E402
from oracle_provider import OracleProvider  # noqa: E402

QUESTIONS = Path(__file__).with_name("questions.yaml")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-demo-secret-at-least-32-chars-long")
BRANCH_MANAGER_BRANCH = 7


def identity(role: str) -> Identity:
    branch = BRANCH_MANAGER_BRANCH if role == "branch_manager" else None
    claims: dict[str, Any] = {"sub": f"eval-{role}", "role": role, "exp": int(time.time()) + 3600}
    if branch:
        claims["branch_id"] = branch
    return Identity(f"eval-{role}", role, branch, jwt.encode(claims, JWT_SECRET, algorithm="HS256"))


def numbers_in_tables(resp: ChatResponse) -> list[float]:
    out: list[float] = []
    for t in resp.tables:
        for row in t.rows:
            out += [float(v) for v in row.values() if isinstance(v, int | float) and not isinstance(v, bool)]
    return out


def evaluate(q: dict[str, Any], resp: ChatResponse) -> list[str]:
    """Return a list of failure reasons (empty = pass)."""
    exp, fails = q["expect"], []
    text = resp.answer_text.lower()
    if not resp.guardrail.passed:
        fails.append(f"guardrail fell back to the safe message (unsupported: {resp.guardrail.unsupported_numbers})")
    missing = set(exp.get("metrics", [])) - set(resp.provenance.metrics_used)
    if missing:
        fails.append(f"metrics not used: {sorted(missing)}")
    used_dims = {d for c in resp.provenance.tool_calls for d in (c["arguments"].get("dimensions") or [])}
    used_dims |= {c["arguments"]["dimension"] for c in resp.provenance.tool_calls if "dimension" in c["arguments"]}
    if set(exp.get("dimensions", [])) - used_dims:
        fails.append(f"dimensions not used: {sorted(set(exp['dimensions']) - used_dims)}")
    nums = numbers_in_tables(resp)
    for v in exp.get("values", []):
        if not any(abs(n - v["value"]) <= abs(v["value"]) * v["rel_tol"] for n in nums):
            fails.append(f"expected value {v['value']:.6g} not found in returned data")
    if exp.get("answer_contains_any") and not any(s.lower() in text for s in exp["answer_contains_any"]):
        fails.append(f"answer lacks any of {exp['answer_contains_any']}")
    for s in exp.get("answer_not_contains", []):
        if s.lower() in text:
            fails.append(f"answer contains forbidden text {s!r}")
    cols = {c for t in resp.tables for c in t.columns}
    if set(exp.get("no_columns", [])) & cols:
        fails.append(f"forbidden columns returned: {sorted(set(exp['no_columns']) & cols)}")
    if exp.get("no_figures") and cited_numbers(resp.answer_text):
        fails.append(f"answer cites figures: {[c[0] for c in cited_numbers(resp.answer_text)]}")
    if exp.get("only_branch"):
        for t in resp.tables:
            if "branch" in t.columns and {r["branch"] for r in t.rows} - {exp["only_branch"]}:
                fails.append(f"data for other branches returned: {sorted({r['branch'] for r in t.rows})}")
    return fails


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, help="gemini | anthropic | oracle")
    ap.add_argument("--ids", help="comma separated question ids")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait between questions (free-tier quotas)")
    ap.add_argument("--min-pass-rate", type=float, default=0.0)
    ap.add_argument("--mcp-url", default=os.getenv("MCP_URL", "http://localhost:8765/mcp"))
    args = ap.parse_args()

    questions = yaml.safe_load(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    if args.ids:
        questions = [q for q in questions if q["id"] in args.ids.split(",")]
    gateway = McpGateway(args.mcp_url)
    await gateway.discover()
    try:
        provider = OracleProvider(questions) if args.provider == "oracle" else create_provider(args.provider)
    except ProviderError as exc:
        print(f"Cannot start provider '{args.provider}': {exc}")
        return 2
    agent = Agent(provider, gateway)  # type: ignore[arg-type]  # no cache: every question hits the model

    results, by_cat = [], defaultdict(lambda: [0, 0])
    print(f"Provider: {provider.name} ({provider.model}), {len(questions)} questions")
    for i, q in enumerate(questions):
        started = time.perf_counter()
        try:
            resp = await agent.ask(q["question"], identity(q["role"]))
            fails = evaluate(q, resp)
            answer = resp.answer_text
        except Exception as exc:  # a provider failure counts as a failed question
            fails, answer = [f"{type(exc).__name__}: {exc}"], ""
        ok = not fails
        by_cat[q["category"]][0] += ok
        by_cat[q["category"]][1] += 1
        results.append({"id": q["id"], "category": q["category"], "role": q["role"], "question": q["question"],
                        "passed": ok, "failures": fails, "answer": answer,
                        "seconds": round(time.perf_counter() - started, 1)})
        print(f"[{'PASS' if ok else 'FAIL'}] {q['id']} ({q['category']}, {q['role']}) {q['question'][:70]}")
        for f in fails:
            print(f"        - {f}")
        if args.delay and i < len(questions) - 1:
            await asyncio.sleep(args.delay)

    passed = sum(r["passed"] for r in results)
    rate = passed / len(results) if results else 0.0
    print(f"\nPass rate [{provider.name}]: {passed}/{len(results)} = {rate:.0%}")
    for cat, (p, n) in sorted(by_cat.items()):
        print(f"  {cat:12s} {p}/{n}")
    out = Path(__file__).parent / "results"
    out.mkdir(exist_ok=True)
    (out / f"{provider.name}-{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(
        json.dumps({"provider": provider.name, "model": provider.model, "pass_rate": rate, "results": results}, indent=1),
        encoding="utf-8")
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
