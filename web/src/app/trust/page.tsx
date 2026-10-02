"use client";

import { BookOpen, CheckCircle2, ClipboardList, Scale, Search, XCircle } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Card, EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatByUnit, humanize } from "@/lib/format";
import type { AuditEntry, Catalog, Reconciliation } from "@/lib/types";

type Tab = "audit" | "recon" | "dictionary";
const TABS: { id: Tab; label: string; icon: typeof Scale }[] = [
  { id: "audit", label: "Audit log", icon: ClipboardList },
  { id: "recon", label: "Reconciliation", icon: Scale },
  { id: "dictionary", label: "Metric dictionary", icon: BookOpen },
];

function useLoad<T>(path: string) {
  const { session } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!session) return;
    let live = true;
    api<T>(path, session.token)
      .then((d) => {
        if (!live) return;
        setData(d);
        setError(null);
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      live = false;
    };
  }, [session, path, tick]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

function summarize(e: AuditEntry): string {
  const a = e.args as Record<string, unknown>;
  if (e.tool === "chat") return String(a.question ?? "");
  const metrics = (a.metrics ?? (a.metric ? [a.metric] : [])) as string[];
  const dims = (a.dimensions ?? (a.dimension ? [a.dimension] : [])) as string[];
  const range = (a.date_range ?? a.period) as { start: string; end: string } | undefined;
  return [metrics.join(", ") || (a.name as string) || "", dims.length ? `by ${dims.join(", ")}` : "", range ? `${range.start} to ${range.end}` : ""]
    .filter(Boolean)
    .join(" · ");
}

function AuditLog() {
  const [tool, setTool] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const qs = new URLSearchParams({ limit: "100", ...(tool && { tool }), ...(status && { status }) }).toString();
  const { data, error, reload } = useLoad<{ scope: string; entries: AuditEntry[] }>(`/audit?${qs}`);
  const sel = "rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink";
  return (
    <Card
      title="Who asked what, and which query ran"
      testId="audit-log"
      action={
        <div className="flex items-center gap-2">
          <select aria-label="Filter by action" value={tool} onChange={(e) => setTool(e.target.value)} className={sel}>
            <option value="">All actions</option>
            {["chat", "query_metrics", "compare_periods", "top_movers", "list_catalog", "describe_metric"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className={sel}>
            <option value="">Any status</option>
            {["ok", "error", "denied"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <button onClick={reload} className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-raised">
            Refresh
          </button>
        </div>
      }
    >
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Skeleton className="h-64" />}
      {data && (
        <>
          <p className="mb-2 text-xs text-ink2">Showing: {data.scope}</p>
          {data.entries.length === 0 ? (
            <EmptyState title="No audit entries yet" hint="Ask the copilot a question or open the dashboard, then refresh." />
          ) : (
            <div className="max-h-[32rem] overflow-auto rounded-lg border border-line">
              <table className="w-full min-w-max text-left text-xs">
                <thead className="sticky top-0 bg-raised text-ink2">
                  <tr>
                    {["Time", "User", "Role", "Action", "Request", "Rows", "Latency", "Status"].map((h) => (
                      <th key={h} scope="col" className="px-3 py-2 font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((e) => (
                    <Fragment key={e.id}>
                      <tr className="cursor-pointer border-t border-line hover:bg-raised" onClick={() => setOpen(open === e.id ? null : e.id)} data-testid="audit-row">
                        <td className="whitespace-nowrap px-3 py-1.5 tabular-nums">{new Date(e.ts).toLocaleString()}</td>
                        <td className="px-3 py-1.5">{e.user}</td>
                        <td className="px-3 py-1.5">{e.role}</td>
                        <td className="px-3 py-1.5 font-medium text-ink">{e.tool}</td>
                        <td className="max-w-md truncate px-3 py-1.5" title={summarize(e)}>
                          {summarize(e)}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums">{e.row_count ?? "-"}</td>
                        <td className="px-3 py-1.5 tabular-nums">{e.latency_ms} ms</td>
                        <td className="px-3 py-1.5">
                          <StatusBadge status={e.status} />
                        </td>
                      </tr>
                      {open === e.id && (
                        <tr className="border-t border-line bg-page/60">
                          <td colSpan={8} className="px-3 py-3">
                            {e.error && <p className="mb-2 text-bad">{e.error}</p>}
                            <p className="font-semibold text-ink">Arguments</p>
                            <pre className="mb-2 overflow-auto rounded bg-surface p-2 text-[11px]">{JSON.stringify(e.args, null, 2)}</pre>
                            <p className="font-semibold text-ink">Semantic-layer query executed</p>
                            <pre className="max-h-56 overflow-auto rounded bg-surface p-2 text-[11px]">{e.cube_query ? JSON.stringify(e.cube_query, null, 2) : "none (no data query)"}</pre>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function ReconciliationView() {
  const { session } = useAuth();
  const { data, error, reload } = useLoad<Reconciliation>("/reconciliation");
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    if (!session || !data) return;
    setBusy(true);
    try {
      await api("/admin/recon-break", session.token, {
        method: "POST",
        body: JSON.stringify({ enabled: data.injected_break_pct === null, delta_pct: 0.35 }),
      });
    } finally {
      setBusy(false);
      reload();
    }
  };
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Skeleton className="h-72" />;
  const ok = data.overall === "pass";
  return (
    <div className="space-y-4" data-testid="reconciliation">
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          {ok ? <CheckCircle2 className="h-12 w-12 text-good" aria-hidden /> : <XCircle className="h-12 w-12 text-bad" aria-hidden />}
          <div className="flex-1">
            <p className="text-lg font-semibold text-ink" data-testid="recon-status">
              {ok ? "Reconciled: marts agree with the general ledger" : "Reconciliation break detected"}
            </p>
            <p className="text-sm text-ink2">
              Deposits and loans are compared with GL control totals at each month end; tolerance {(data.tolerance_pct * 100).toFixed(2)}%. Latest month:{" "}
              {data.latest?.month}.
            </p>
          </div>
          {session?.role === "cmo" && (
            <button disabled={busy} onClick={() => void toggle()} data-testid="recon-toggle" className="rounded-lg border border-line px-3 py-2 text-sm font-medium hover:bg-raised disabled:opacity-50">
              {data.injected_break_pct === null ? "Demo: inject a GL discrepancy" : "Demo: remove the discrepancy"}
            </button>
          )}
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {data.latest?.checks.map((c) => (
          <Card key={c.name} title={`${c.name} (${data.latest?.month})`} testId={`recon-${c.name.toLowerCase()}`}>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-ink2">Governed marts</dt>
              <dd className="text-right tabular-nums">{formatByUnit(c.marts, "bdt")}</dd>
              <dt className="text-ink2">General ledger</dt>
              <dd className="text-right tabular-nums">{formatByUnit(c.gl, "bdt")}</dd>
              <dt className="text-ink2">Difference</dt>
              <dd className="text-right tabular-nums">
                {formatByUnit(c.difference, "bdt")} ({c.difference_pct === null ? "n/a" : `${(c.difference_pct * 100).toFixed(3)}%`})
              </dd>
              <dt className="text-ink2">Result</dt>
              <dd className="text-right">
                <StatusBadge status={c.status} />
              </dd>
            </dl>
          </Card>
        ))}
      </div>
      <Card title="Last six months">
        <div className="overflow-auto rounded-lg border border-line">
          <table className="w-full text-left text-xs">
            <thead className="bg-raised text-ink2">
              <tr>
                {["Month", "Deposits difference", "Loans difference", "Result"].map((h) => (
                  <th key={h} scope="col" className="px-3 py-2 font-semibold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...data.history].reverse().map((h) => (
                <tr key={h.month} className="border-t border-line">
                  <td className="px-3 py-1.5 font-medium">{h.month}</td>
                  {h.checks.map((c) => (
                    <td key={c.name} className="px-3 py-1.5 tabular-nums">
                      {c.difference_pct === null ? "n/a" : `${(c.difference_pct * 100).toFixed(3)}%`}
                    </td>
                  ))}
                  <td className="px-3 py-1.5">
                    <StatusBadge status={h.status === "pass" ? "pass" : "fail"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Dictionary() {
  const { data, error, reload } = useLoad<Catalog>("/catalog");
  const [q, setQ] = useState("");
  const metrics = useMemo(
    () => (data?.metric_groups ?? []).flatMap((g) => g.metrics.map((m) => ({ ...m, dimensions: g.dimensions }))),
    [data],
  );
  const shown = metrics.filter((m) => `${m.name} ${m.title} ${m.definition}`.toLowerCase().includes(q.toLowerCase()));
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <Skeleton className="h-72" />;
  return (
    <div className="space-y-4" data-testid="dictionary">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search metrics" placeholder="Search metrics and definitions" className="w-full rounded-lg border border-line bg-surface py-2 pl-9 pr-3 text-sm" />
      </div>
      <p className="text-xs text-ink2">
        {shown.length} certified metrics · {data.conventions[0]}
      </p>
      {shown.length === 0 && <EmptyState title="No metric matches your search" />}
      <div className="grid gap-4 md:grid-cols-2">
        {shown.map((m) => (
          <Card key={m.name} testId="metric-card">
            <p className="font-semibold text-ink">{m.title}</p>
            <p className="text-xs text-muted">{m.name}</p>
            <p className="mt-2 text-sm text-ink2">{m.definition}</p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt className="text-muted">Owner</dt>
              <dd>{m.owner}</dd>
              <dt className="text-muted">Time basis</dt>
              <dd>{m.time_semantics}</dd>
              <dt className="text-muted">Unit</dt>
              <dd>{m.unit}</dd>
              <dt className="text-muted">Source</dt>
              <dd>{m.source_tables.join(", ")}</dd>
              <dt className="text-muted">Break down by</dt>
              <dd>{m.dimensions.map(humanize).join(", ")}</dd>
              {m.caveats && (
                <>
                  <dt className="text-muted">Caveats</dt>
                  <dd>{m.caveats}</dd>
                </>
              )}
            </dl>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function TrustPage() {
  const [tab, setTab] = useState<Tab>("audit");
  const { epoch } = useAuth();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink">Trust center</h1>
      <div role="tablist" aria-label="Trust center sections" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium ${tab === t.id ? "border-brand text-brand" : "border-transparent text-ink2 hover:text-ink"}`}
          >
            <t.icon className="h-4 w-4" aria-hidden />
            {t.label}
          </button>
        ))}
      </div>
      {tab === "audit" && <AuditLog key={epoch} />}
      {tab === "recon" && <ReconciliationView key={epoch} />}
      {tab === "dictionary" && <Dictionary key={epoch} />}
    </div>
  );
}
