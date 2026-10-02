"""Display formatting driven by the metric unit, so every surface shows numbers the same way."""

from __future__ import annotations


def format_value(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "percent":
        return f"{value * 100:.2f}%"
    if unit == "bdt":
        a = abs(value)
        if a >= 1e9:
            return f"BDT {value / 1e9:.2f} billion"
        if a >= 1e6:
            return f"BDT {value / 1e6:.2f} million"
        return f"BDT {value:,.0f}"
    if unit == "ratio":
        return f"{value:.2f}"
    return f"{value:,.0f}"


def format_change(change: float | None, unit: str) -> str:
    """Signed change; percent metrics are expressed in percentage points."""
    if change is None:
        return "n/a"
    sign = "+" if change > 0 else ""
    if unit == "percent":
        return f"{sign}{change * 100:.2f} pp"
    return sign + format_value(change, unit)


def format_pct_change(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    return f"{'+' if pct > 0 else ''}{pct * 100:.1f}%"
