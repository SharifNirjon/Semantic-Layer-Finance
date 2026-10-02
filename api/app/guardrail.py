"""Post-check: every figure cited in the answer must appear in the tool results."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

SCALE_WORDS = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9,
               "lakh": 1e5, "crore": 1e7}
NUMBER = re.compile(r"(?<![\w.])([-+]?\d[\d,]*(?:\.\d+)?)\s*(%|pp|thousand|million|billion|bn|crore|lakh|k|m|b)?(?!\w)",
                    re.IGNORECASE)
MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
NOISE = [
    re.compile(r"\b\d{4}-\d{2}(-\d{2})?\b"),  # ISO dates and months
    re.compile(r"\bQ[1-4]\b", re.IGNORECASE),
    re.compile(r"\bFY\s?\d+\b", re.IGNORECASE),
    re.compile(rf"\b({MONTHS})\.?\s+\d{{1,4}}\b", re.IGNORECASE),
    re.compile(rf"\b\d{{1,2}}\s+({MONTHS})(\s+\d{{4}})?\b", re.IGNORECASE),
]
# raw value, x100 (fraction shown as percent), and scaled forms (thousand, lakh, million, crore, billion)
SCALES = (1.0, 100.0, 1e-3, 1e-5, 1e-6, 1e-7, 1e-9)


def _strip_noise(text: str) -> str:
    for pattern in NOISE:
        text = pattern.sub(" ", text)
    return text


def cited_numbers(text: str) -> list[tuple[str, float, int, str]]:
    """(token, value, decimals, suffix) for each figure worth verifying."""
    found = []
    for m in NUMBER.finditer(_strip_noise(text)):
        raw, suffix = m.group(1).replace(",", ""), (m.group(2) or "").lower()
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw)
        bare_int = not suffix and decimals == 0 and "," not in m.group(1)
        if bare_int and (1900 <= abs(value) <= 2100 or abs(value) <= 10):  # years, "top 3", "2 segments"
            continue
        found.append((m.group(0).strip(), value, decimals, suffix))
    return found


def _numbers_in(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield float(value)
    elif isinstance(value, str):
        for m in NUMBER.finditer(value):
            yield float(m.group(1).replace(",", ""))
    elif isinstance(value, dict):
        for v in value.values():
            yield from _numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from _numbers_in(v)


def allowed_numbers(sources: Iterable[Any]) -> list[float]:
    allowed: set[float] = set()
    for source in sources:
        for n in _numbers_in(source):
            allowed.update(n * s for s in SCALES)
    return sorted(allowed)


def unsupported_numbers(answer_text: str, sources: Iterable[Any]) -> list[str]:
    """Figures in `answer_text` that no tool result (or tool argument) supports, within display rounding."""
    allowed = allowed_numbers(sources)
    bad = []
    for token, value, decimals, suffix in cited_numbers(answer_text):
        scale = SCALE_WORDS.get(suffix, 1.0)
        tol = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(c - value * scale) <= tol * scale or abs(c - value) <= tol for c in allowed):
            bad.append(token)
    return bad
