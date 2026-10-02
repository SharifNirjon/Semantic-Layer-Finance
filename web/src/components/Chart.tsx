"use client";

import { BarChart3, Table2 } from "lucide-react";
import { useId, useState } from "react";
import {
  Area,
  AreaChart,
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
  type TooltipContentProps,
} from "recharts";
import { compactTick, colorFor, formatByUnit, humanize, pivot } from "@/lib/format";
import type { Row } from "@/lib/types";
import DataTable from "./DataTable";

interface Props {
  title: string;
  subtitle?: string;
  type: "line" | "bar" | "pie";
  rows: Row[];
  displayRows: Record<string, string>[];
  columns: string[];
  x: string;
  y: string[];
  series?: string | null;
  unitOf: (metric: string) => string;
  testId?: string;
  height?: string;
}

type TipProps = TooltipContentProps<number, string>;

const AXIS = { fontSize: 11 };
const GRID = "var(--line)";

function ChartTip({ active, label: xLabel, payload, label_, fmt }: Pick<TipProps, "active" | "label" | "payload"> & { label_: (k: string) => string; fmt: (k: string, v: unknown) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-xl border border-line bg-surface/95 px-3 py-2 text-xs shadow-float backdrop-blur">
      <p className="mb-1.5 font-semibold text-ink">{xLabel}</p>
      <ul className="space-y-1">
        {[...payload]
          .sort((a, b) => Number(b.value) - Number(a.value))
          .map((p) => (
            <li key={String(p.dataKey ?? p.name)} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-1.5 text-ink2">
                <span className="h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden />
                {label_(String(p.name))}
              </span>
              <span className="num font-medium text-ink">{fmt(String(p.name), p.value)}</span>
            </li>
          ))}
      </ul>
    </div>
  );
}

/** One y-scale per chart. A table view is always available (accessibility and CVD relief). */
export default function Chart({ title, subtitle, type, rows, displayRows, columns, x, y, series = null, unitOf, testId, height = "h-64" }: Props) {
  const [showTable, setShowTable] = useState(false);
  const gradient = useId().replace(/:/g, "");
  const unit = unitOf(y[0]);
  const { data, keys } = pivot(rows, x, y, series);
  const horizontal = type === "bar" && data.length > 8 && !series;
  const label = (key: string) => (y.includes(key) ? humanize(key) : key);
  const fmt = (key: string, v: unknown) => formatByUnit(Number(v), y.includes(key) ? unitOf(key) : unit);

  const tip = <Tooltip content={(p) => <ChartTip active={p.active} label={p.label} payload={p.payload} label_={label} fmt={fmt} />} cursor={type === "bar" ? { fill: "var(--line)", opacity: 0.5 } : { stroke: "var(--axis)", strokeDasharray: "3 3" }} />;
  const legend = keys.length > 1 && <Legend iconType="circle" iconSize={8} wrapperStyle={{ paddingTop: 8 }} formatter={(v) => label(String(v))} />;

  return (
    <div data-testid={testId} className="w-full">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
        </div>
        <div className="flex shrink-0 rounded-lg border border-line bg-raised p-0.5" role="group" aria-label="Chart or table">
          {[
            { table: false, icon: BarChart3, text: "Show chart" },
            { table: true, icon: Table2, text: "View as table" },
          ].map((o) => (
            <button
              key={o.text}
              onClick={() => setShowTable(o.table)}
              aria-pressed={showTable === o.table}
              aria-label={o.text}
              title={o.text}
              className={`rounded-md p-1.5 transition ${showTable === o.table ? "bg-surface text-brand shadow-card" : "text-muted hover:text-ink"}`}
            >
              <o.icon className="h-3.5 w-3.5" aria-hidden />
            </button>
          ))}
        </div>
      </div>
      {showTable ? (
        <DataTable columns={columns} rows={displayRows} maxHeight="max-h-72" />
      ) : (
        <div role="img" aria-label={`${title}. Use "View as table" for the data.`} className={horizontal ? "h-[28rem]" : height}>
          <ResponsiveContainer width="100%" height="100%">
            {type === "pie" ? (
              <PieChart>
                <Pie data={data} dataKey={y[0]} nameKey={x} innerRadius={56} outerRadius={92} paddingAngle={1} stroke="var(--surface)" strokeWidth={2}>
                  {data.map((d) => (
                    <Cell key={String(d[x])} fill={colorFor(String(d[x]))} />
                  ))}
                </Pie>
                {tip}
                <Legend iconType="circle" iconSize={8} />
              </PieChart>
            ) : type === "line" && keys.length === 1 ? (
              <AreaChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={colorFor(keys[0])} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={colorFor(keys[0])} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey={x} tick={AXIS} stroke="var(--axis)" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={AXIS} stroke="var(--axis)" width={52} tickLine={false} axisLine={false} tickFormatter={(v: number) => compactTick(v, unit)} />
                {tip}
                <Area
                  isAnimationActive={false}
                  type="monotone"
                  dataKey={keys[0]}
                  name={keys[0]}
                  stroke={colorFor(keys[0])}
                  strokeWidth={2}
                  fill={`url(#${gradient})`}
                  dot={false}
                  activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
                />
              </AreaChart>
            ) : type === "line" ? (
              <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey={x} tick={AXIS} stroke="var(--axis)" tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis tick={AXIS} stroke="var(--axis)" width={52} tickLine={false} axisLine={false} tickFormatter={(v: number) => compactTick(v, unit)} />
                {tip}
                {legend}
                {keys.map((k) => (
                  <Line
                    key={k}
                    isAnimationActive={false}
                    type="monotone"
                    dataKey={k}
                    name={k}
                    stroke={colorFor(k)}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2 }}
                  />
                ))}
              </LineChart>
            ) : (
              <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 6, right: 8, left: horizontal ? 60 : 0, bottom: 0 }} barGap={2}>
                <CartesianGrid stroke={GRID} horizontal={!horizontal} vertical={horizontal} />
                {horizontal ? (
                  <>
                    <XAxis type="number" tick={AXIS} stroke="var(--axis)" tickLine={false} axisLine={false} tickFormatter={(v: number) => compactTick(v, unit)} />
                    <YAxis type="category" dataKey={x} tick={AXIS} stroke="var(--axis)" tickLine={false} axisLine={false} width={110} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey={x} tick={AXIS} stroke="var(--axis)" tickLine={false} axisLine={false} />
                    <YAxis tick={AXIS} stroke="var(--axis)" width={52} tickLine={false} axisLine={false} tickFormatter={(v: number) => compactTick(v, unit)} />
                  </>
                )}
                {tip}
                {legend}
                {keys.map((k) => (
                  <Bar
                    key={k}
                    isAnimationActive={false}
                    dataKey={k}
                    name={k}
                    fill={colorFor(k)}
                    maxBarSize={44}
                    radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
                    stroke="var(--surface)"
                    strokeWidth={2}
                  />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
