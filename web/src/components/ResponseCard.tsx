"use client";

import { BadgeCheck, BookOpen, Code2, Info, ShieldAlert } from "lucide-react";
import type { ChatResponse } from "@/lib/types";
import Chart from "./Chart";
import DataTable from "./DataTable";
import { Collapsible } from "./ui";

export function VerifiedBadge({ response }: { response: ChatResponse }) {
  const g = response.guardrail;
  return g.passed ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-goodsoft px-2 py-0.5 text-[11px] font-semibold text-good" title="Every figure was checked against the tool results">
      <BadgeCheck className="h-3.5 w-3.5" aria-hidden />
      Figures verified{g.cached ? " · demo cache" : ""}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-warnsoft px-2 py-0.5 text-[11px] font-semibold text-warn">
      <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
      Narrative withheld
    </span>
  );
}

/** Chart + table + provenance panels for one validated answer. */
export default function ResponseCard({ response }: { response: ChatResponse }) {
  const chart = response.chart_spec;
  const source = chart ? response.tables.find((t) => t.call_id === chart.source_call_id) ?? response.tables[0] : null;
  const defs = response.provenance.definitions;
  // comparison tables name their value columns period_a/period_b: use the compared metric's unit
  const unitOf = (col: string) => (defs.find((d) => d.name === col) ?? defs.find((d) => d.name === source?.metric))?.unit ?? "count";
  const p = response.provenance;

  return (
    <div className="mt-4 space-y-3" data-testid="response-card">
      {chart && chart.type !== "none" && source && (
        <div className="rounded-xl border border-line bg-surface p-4" data-testid="chat-chart">
          <Chart
            title={chart.title || source.title}
            type={chart.type as "line" | "bar" | "pie"}
            rows={chart.data}
            displayRows={source.display_rows}
            columns={source.columns}
            x={chart.x}
            y={chart.y}
            series={chart.series}
            unitOf={unitOf}
          />
        </div>
      )}
      {response.tables.map((t) => (
        <div key={t.call_id} data-testid="chat-table">
          <p className="mb-1.5 text-xs font-semibold text-ink2">{t.title}</p>
          <DataTable columns={t.columns} rows={t.display_rows} />
        </div>
      ))}
      <div className="grid gap-2">
        <Collapsible title="Definition" icon={<BookOpen className="h-3.5 w-3.5" aria-hidden />} testId="panel-definition">
          {p.definitions.length === 0 ? (
            <p>No metric was queried for this answer.</p>
          ) : (
            <ul className="space-y-3">
              {p.definitions.map((d) => (
                <li key={d.name}>
                  <p className="font-semibold text-ink">
                    {d.title} <span className="font-mono font-normal text-muted">{d.name}</span>
                  </p>
                  <p className="mt-0.5">{d.definition}</p>
                  <p className="mt-1.5 flex flex-wrap gap-1.5 text-[11px]">
                    {[`Owner: ${d.owner}`, `Time basis: ${d.time_semantics}`, `Unit: ${d.unit}`].map((m) => (
                      <span key={m} className="rounded-md bg-sunken px-1.5 py-0.5 text-ink2">
                        {m}
                      </span>
                    ))}
                  </p>
                  {d.caveats && (
                    <p className="mt-1.5 flex gap-1">
                      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                      {d.caveats}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Collapsible>
        <Collapsible title="How this was calculated" icon={<Code2 className="h-3.5 w-3.5" aria-hidden />} testId="panel-calculation">
          <div className="space-y-3">
            <p>
              Executed as <strong className="text-ink">{p.executed_as.role}</strong>
              {p.executed_as.branch_id ? ` (branch ${p.executed_as.branch_id} only)` : ""}. Numbers come only from the governed semantic layer; the
              model never sees raw tables or writes SQL.
            </p>
            <div>
              <p className="font-semibold text-ink">Tool calls</p>
              <ul className="mt-1.5 space-y-2">
                {p.tool_calls.map((c) => (
                  <li key={c.id}>
                    <code className="font-mono text-ink">{c.tool}</code> <span className="text-muted">{c.latency_ms} ms</span>
                    {c.error && <span className="text-bad"> - {c.error}</span>}
                    <pre className="mt-1 overflow-x-auto rounded-lg bg-sunken p-2.5 font-mono text-[11px]">{JSON.stringify(c.arguments)}</pre>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-semibold text-ink">Semantic-layer (Cube) queries executed</p>
              <pre data-testid="cube-query" className="mt-1.5 max-h-64 overflow-auto rounded-lg bg-sunken p-2.5 font-mono text-[11px]">
                {JSON.stringify(p.cube_queries, null, 2)}
              </pre>
            </div>
            <p className="flex items-center gap-1.5">
              <BadgeCheck className="h-4 w-4 text-good" aria-hidden />
              {response.guardrail.passed
                ? `Every figure in the answer was verified against the tool results${response.guardrail.retried ? " (after one correction)" : ""}.`
                : "Figure check could not confirm every number, so no narrative is shown."}
              {response.guardrail.cached && " Served from the demo cache."}
            </p>
            <p className="text-muted">
              Model: {response.provider} / {response.model}
            </p>
          </div>
        </Collapsible>
      </div>
    </div>
  );
}
