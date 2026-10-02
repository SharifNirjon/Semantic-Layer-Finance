"use client";

import { humanize } from "@/lib/format";

interface Props {
  columns: string[];
  rows: Record<string, string>[];
  titles?: Record<string, string>;
  testId?: string;
}

/** Renders governed display strings exactly as returned by the semantic layer. */
export default function DataTable({ columns, rows, titles = {}, testId }: Props) {
  return (
    <div className="max-h-96 overflow-auto rounded-lg border border-line" data-testid={testId}>
      <table className="w-full min-w-max text-left text-xs">
        <thead className="sticky top-0 bg-raised text-ink2">
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col" className="whitespace-nowrap px-3 py-2 font-semibold">
                {titles[c] ?? humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c, j) => (
                <td key={c} className={`whitespace-nowrap px-3 py-1.5 text-ink ${j > 0 ? "tabular-nums" : "font-medium"}`}>
                  {r[c] ?? ""}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-ink2">
                No rows
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
