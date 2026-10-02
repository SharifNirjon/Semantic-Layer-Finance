"use client";

import { BadgeCheck, Info } from "lucide-react";
import type { ChatResponse } from "@/lib/types";
import Chart from "./Chart";
import DataTable from "./DataTable";
import { Collapsible } from "./ui";

/** Chart + table + provenance panels for one validated answer. */
export default function ResponseCard({ response }: { response: ChatResponse }) {
  const unitOf = (metric: string) => response.provenance.definitions.find((d) => d.name === metric)?.unit ?? "count";
  const chart = response.chart_spec;
  const source = chart ? response.tables.find((t) => t.call_id === chart.source_call_id) ?? response.tables[0] : null;
  const p = response.provenance;

  return (
    <div className="mt-3 space-y-3" data-testid="response-card">
      {chart && chart.type !== "none" && source && (
        <div className="rounded-lg border border-line bg-surface p-3" data-testid="chat-chart">
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
          <p className="mb-1 text-xs font-semibold text-ink2">{t.title}</p>
          <DataTable columns={t.columns} rows={t.display_rows} />
        </div>
      ))}
      <Collapsible title="Definition" testId="panel-definition">
        {p.definitions.length === 0 ? (
          <p>No metric was queried for this answer.</p>
        ) : (
          <ul className="space-y-3">
            {p.definitions.map((d) => (
              <li key={d.name}>
                <p className="font-semibold text-ink">
                  {d.title} <span className="font-normal text-muted">({d.name})</span>
                </p>
                <p>{d.definition}</p>
                <p className="mt-1 text-muted">
                  Owner: {d.owner} · Time basis: {d.time_semantics} · Unit: {d.unit}
                </p>
                {d.caveats && <p className="mt-1 flex gap-1"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{d.caveats}</p>}
              </li>
            ))}
          </ul>
        )}
      </Collapsible>
      <Collapsible title="How this was calculated" testId="panel-calculation">
        <div className="space-y-3">
          <p>
            Executed as <strong className="text-ink">{p.executed_as.role}</strong>
            {p.executed_as.branch_id ? ` (branch ${p.executed_as.branch_id} only)` : ""}. Numbers come only from the governed
            semantic layer; the model never sees raw tables or writes SQL.
          </p>
          <div>
            <p className="font-semibold text-ink">Tool calls</p>
            <ul className="mt-1 list-disc pl-4">
              {p.tool_calls.map((c) => (
                <li key={c.id}>
                  <code>{c.tool}</code> <span className="text-muted">{c.latency_ms} ms</span>
                  {c.error && <span className="text-bad"> - {c.error}</span>}
                  <pre className="mt-1 overflow-x-auto rounded bg-surface p-2 text-[11px]">{JSON.stringify(c.arguments)}</pre>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="font-semibold text-ink">Semantic-layer (Cube) queries executed</p>
            <pre data-testid="cube-query" className="mt-1 max-h-64 overflow-auto rounded bg-surface p-2 text-[11px]">
              {JSON.stringify(p.cube_queries, null, 2)}
            </pre>
          </div>
          <p className="flex items-center gap-1">
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
  );
}
