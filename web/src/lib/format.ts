import type { Row } from "./types";

/** Formatting only (axis ticks, tooltips). Figures themselves always come from the semantic layer. */
export function formatByUnit(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (unit === "percent") return `${(value * 100).toFixed(2)}%`;
  if (unit === "bdt") {
    const a = Math.abs(value);
    if (a >= 1e9) return `BDT ${(value / 1e9).toFixed(2)} billion`;
    if (a >= 1e6) return `BDT ${(value / 1e6).toFixed(2)} million`;
    return `BDT ${Math.round(value).toLocaleString("en-US")}`;
  }
  if (unit === "ratio") return value.toFixed(2);
  return Math.round(value).toLocaleString("en-US");
}

export function compactTick(value: number, unit: string): string {
  if (unit === "percent") return `${(value * 100).toFixed(1)}%`;
  const a = Math.abs(value);
  if (a >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(value / 1e3).toFixed(0)}K`;
  return unit === "ratio" ? value.toFixed(1) : String(Math.round(value));
}

export function humanize(column: string): string {
  return column.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Categorical colors follow the entity (first seen keeps its slot), never its rank. */
const registry = new Map<string, number>();
export function colorFor(key: string): string {
  if (!registry.has(key)) registry.set(key, registry.size % 8);
  return `var(--c${(registry.get(key) ?? 0) + 1})`;
}

export interface Pivoted {
  data: Row[];
  keys: string[];
}

/** Long rows -> wide rows: one key per series value (single y) so each series becomes one line/bar. */
export function pivot(rows: Row[], x: string, y: string[], series: string | null): Pivoted {
  if (!series) return { data: rows, keys: y };
  const keys = [...new Set(rows.map((r) => String(r[series])))].slice(0, 8);
  const byX = new Map<string, Row>();
  for (const r of rows) {
    const k = String(r[series]);
    if (!keys.includes(k)) continue;
    const row = byX.get(String(r[x])) ?? { [x]: r[x] };
    row[k] = r[y[0]];
    byX.set(String(r[x]), row);
  }
  return { data: [...byX.values()], keys };
}
