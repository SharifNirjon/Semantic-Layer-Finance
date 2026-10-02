"use client";

import { humanize } from "@/lib/format";
import type { Row } from "@/lib/types";

interface Props {
  columns: string[];
  rows: Record<string, string>[];
  titles?: Record<string, string>;
  testId?: string;
  /** Raw numeric rows (same order as `rows`); columns listed in `bars` get an inline magnitude bar. */
  rawRows?: Row[];
  bars?: string[];
  maxHeight?: string;
}

/** Renders governed display strings exactly as returned by the semantic layer. */
export default function DataTable({ columns, rows, titles = {}, testId, rawRows, bars = [], maxHeight = "max-h-96" }: Props) {
  const max = Object.fromEntries(
    bars.map((c) => [c, Math.max(0, ...(rawRows ?? []).map((r) => Math.abs(Number(r[c]) || 0)))]),
  );
  return (
    <div className={`${maxHeight} overflow-auto rounded-xl border border-line`} data-testid={testId}>
      <table className="w-full min-w-max text-left text-[13px]">
        <thead className="sticky top-0 z-10 bg-raised text-ink2">
          <tr>
            {columns.map((c, j) => (
              <th key={c} scope="col" className={`whitespace-nowrap px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider ${j > 0 ? "text-right" : ""}`}>
                {titles[c] ?? humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line transition-colors hover:bg-raised/70">
              {columns.map((c, j) => {
                const raw = rawRows?.[i]?.[c];
                const share = bars.includes(c) && max[c] ? Math.abs(Number(raw) || 0) / max[c] : null;
                return (
                  <td key={c} className={`whitespace-nowrap px-4 py-2.5 ${j > 0 ? "num text-right text-ink" : "font-medium text-ink"}`}>
                    {share === null ? (
                      (r[c] ?? "")
                    ) : (
                      <span className="inline-flex items-center justify-end gap-2.5">
                        <span className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-sunken sm:block" aria-hidden>
                          <span className="block h-full rounded-full bg-brand/70" style={{ width: `${Math.max(4, share * 100)}%` }} />
                        </span>
                        {r[c] ?? ""}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-ink2">
                No rows
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
