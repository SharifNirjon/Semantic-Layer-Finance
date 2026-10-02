"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compactTick, colorFor, formatByUnit, humanize, pivot } from "@/lib/format";
import type { Row } from "@/lib/types";
import DataTable from "./DataTable";

interface Props {
  title: string;
  type: "line" | "bar" | "pie";
  rows: Row[];
  displayRows: Record<string, string>[];
  columns: string[];
  x: string;
  y: string[];
  series?: string | null;
  unitOf: (metric: string) => string;
  testId?: string;
}

/** One y-scale per chart. A table view is always available (accessibility and CVD relief). */
export default function Chart({ title, type, rows, displayRows, columns, x, y, series = null, unitOf, testId }: Props) {
  const [showTable, setShowTable] = useState(false);
  const unit = unitOf(y[0]);
  const { data, keys } = pivot(rows, x, y, series);
  const horizontal = type === "bar" && data.length > 8 && !series;
  const tooltipFmt = (v: unknown, name: unknown): [string, string] => {
    const key = String(name);
    return [formatByUnit(Number(v), y.includes(key) ? unitOf(key) : unit), y.includes(key) ? humanize(key) : key];
  };

  return (
    <div data-testid={testId} className="w-full">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <button onClick={() => setShowTable((s) => !s)} className="text-xs font-medium text-brand hover:underline">
          {showTable ? "Show chart" : "View as table"}
        </button>
      </div>
      {showTable ? (
        <DataTable columns={columns} rows={displayRows} />
      ) : (
        <div role="img" aria-label={`${title}. Use "View as table" for the data.`} className={horizontal ? "h-[28rem]" : "h-64"}>
          <ResponsiveContainer width="100%" height="100%">
            {type === "pie" ? (
              <PieChart>
                <Pie data={data} dataKey={y[0]} nameKey={x} innerRadius={50} outerRadius={90} stroke="var(--surface)" strokeWidth={2}>
                  {data.map((d) => (
                    <Cell key={String(d[x])} fill={colorFor(String(d[x]))} />
                  ))}
                </Pie>
                <Tooltip formatter={tooltipFmt} />
                <Legend />
              </PieChart>
            ) : type === "line" ? (
              <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey={x} tick={{ fontSize: 11 }} stroke="var(--axis)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--axis)" width={56} tickFormatter={(v: number) => compactTick(v, unit)} />
                <Tooltip formatter={tooltipFmt} contentStyle={{ background: "var(--raised)", border: "1px solid var(--line)", borderRadius: 8 }} />
                {keys.length > 1 && <Legend />}
                {keys.map((k) => (
                  <Line key={k} type="monotone" dataKey={k} name={k} stroke={colorFor(k)} strokeWidth={2} dot={{ r: 3, stroke: "var(--surface)", strokeWidth: 2 }} activeDot={{ r: 5 }} />
                ))}
              </LineChart>
            ) : (
              <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, left: horizontal ? 60 : 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--line)" horizontal={!horizontal} vertical={horizontal} />
                {horizontal ? (
                  <>
                    <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--axis)" tickFormatter={(v: number) => compactTick(v, unit)} />
                    <YAxis type="category" dataKey={x} tick={{ fontSize: 11 }} stroke="var(--axis)" width={110} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey={x} tick={{ fontSize: 11 }} stroke="var(--axis)" />
                    <YAxis tick={{ fontSize: 11 }} stroke="var(--axis)" width={56} tickFormatter={(v: number) => compactTick(v, unit)} />
                  </>
                )}
                <Tooltip formatter={tooltipFmt} cursor={{ fill: "var(--line)", opacity: 0.4 }} contentStyle={{ background: "var(--raised)", border: "1px solid var(--line)", borderRadius: 8 }} />
                {keys.length > 1 && <Legend />}
                {keys.map((k) => (
                  <Bar key={k} dataKey={k} name={k} fill={colorFor(k)} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} stroke="var(--surface)" strokeWidth={2} />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
