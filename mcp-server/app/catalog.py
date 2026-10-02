"""Governed catalog built from Cube's /meta: metrics, dimensions and which combinations are allowed."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from .errors import ToolInputError

TIME_DIM = "business_date"


@dataclass(frozen=True)
class Metric:
    name: str
    cube: str
    title: str
    description: str
    unit: str
    time_semantics: str
    owner: str
    formula: str
    source_tables: list[str]
    caveats: str
    bank_wide: bool
    in_catalog: bool
    grain: str  # month | day

    @property
    def member(self) -> str:
        return f"{self.cube}.{self.name}"


@dataclass(frozen=True)
class Dimension:
    name: str
    title: str
    description: str
    customer_level: bool
    members: dict[str, str] = field(default_factory=dict)  # cube -> cube.member


@dataclass
class Catalog:
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]
    cube_dims: dict[str, set[str]]

    @classmethod
    def from_meta(cls, meta: dict[str, Any]) -> Catalog:
        metrics: dict[str, Metric] = {}
        dims: dict[str, Dimension] = {}
        cube_dims: dict[str, set[str]] = {}
        for cube in meta["cubes"]:
            cname = cube["name"]
            grain = (cube.get("meta") or {}).get("grain", "month")
            cube_dims[cname] = set()
            for d in cube["dimensions"]:
                short = d["name"].split(".", 1)[1]
                dmeta = d.get("meta") or {}
                if short == TIME_DIM or dmeta.get("internal"):
                    continue
                cube_dims[cname].add(short)
                existing = dims.get(short)
                members = {**(existing.members if existing else {}), cname: d["name"]}
                dims[short] = Dimension(short, d.get("shortTitle") or d["title"],
                                        (existing.description if existing else "") or d.get("description", ""),
                                        bool(dmeta.get("customer_level")), members)
            for m in cube["measures"]:
                mm = m.get("meta") or {}
                short = m["name"].split(".", 1)[1]
                metrics[short] = Metric(
                    name=short, cube=cname, title=m.get("shortTitle") or m["title"], description=m.get("description", ""),
                    unit=mm.get("unit", "count"), time_semantics=mm.get("time_semantics", "flow"),
                    owner=mm.get("owner", "unassigned"), formula=mm.get("formula", ""),
                    source_tables=list(mm.get("source_tables", [])), caveats=mm.get("caveats", ""),
                    bank_wide=bool(mm.get("bank_wide")), in_catalog=mm.get("catalog", True), grain=grain,
                )
        return cls(metrics, dims, cube_dims)

    # -- visibility (presentation only; Cube enforces access) ------------------------------------------------
    def visible_metrics(self, role: str) -> list[Metric]:
        return [m for m in self.metrics.values() if m.in_catalog and not (role == "branch_manager" and m.bank_wide)]

    def visible_dimensions(self, role: str) -> list[Dimension]:
        return [d for d in self.dimensions.values() if not (role == "analyst" and d.customer_level)]

    # -- validation ------------------------------------------------------------------------------------------
    def metric(self, name: str, role: str) -> Metric:
        m = self.metrics.get(name)
        if m is None or not m.in_catalog or m not in self.visible_metrics(role):
            raise ToolInputError(self._unknown("metric", name, [x.name for x in self.visible_metrics(role)]))
        return m

    def dimension(self, name: str, role: str) -> Dimension:
        d = self.dimensions.get(name)
        if d is None or d not in self.visible_dimensions(role):
            raise ToolInputError(self._unknown("dimension", name, [x.name for x in self.visible_dimensions(role)]))
        return d

    @staticmethod
    def _unknown(kind: str, name: str, options: list[str]) -> str:
        close = difflib.get_close_matches(name, options, n=3, cutoff=0.5)
        hint = f" Did you mean: {', '.join(close)}?" if close else ""
        return (f"Unknown {kind} '{name}'.{hint} Call list_catalog to see all {kind}s "
                f"({len(options)} available, e.g. {', '.join(sorted(options)[:6])}).")

    def check_combination(self, metric: Metric, dimension: Dimension) -> str:
        if dimension.name not in self.cube_dims[metric.cube]:
            allowed = sorted(self.cube_dims[metric.cube] - {d.name for d in self.dimensions.values() if d.customer_level})
            raise ToolInputError(f"Dimension '{dimension.name}' is not available for metric '{metric.name}'. "
                                 f"Dimensions available for {metric.name}: {', '.join(allowed)}.")
        return dimension.members[metric.cube]
