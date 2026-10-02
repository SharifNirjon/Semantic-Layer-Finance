"use client";

import { BookOpen, CheckCircle2, ClipboardList, Landmark, RefreshCw, Scale, Search, XCircle } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Card, EmptyState, ErrorState, PageHeader, Pill, Skeleton, StatusBadge } from "@/components/ui";
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

const SELECT = "rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink shadow-card";

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
  return (
    <Card
      title="Who asked what, and which query ran"
      subtitle={data ? `Showing: ${data.scope} · click a row for the exact semantic-layer query` : undefined}
      testId="audit-log"
      action={
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Filter by action" value={tool} onChange={(e) => setTool(e.target.value)} className={SELECT}>
            <option value="">All actions</option>
            {["chat", "query_metrics", "compare_periods", "top_movers", "list_catalog", "describe_metric"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className={SELECT}>
            <option value="">Any status</option>
            {["ok", "error", "denied"].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <button onClick={reload} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink shadow-card hover:bg-raised">
            <RefreshCw className="h-3.5 w-3.5" aria-hidden />
            Refresh
          </button>
        </div>
      }
    >
      {error && <ErrorState message={error} onRetry={reload} />}
      {!data && !error && <Skeleton className="h-64" />}
      {data &&
        (data.entries.length === 0 ? (
          <EmptyState title="No audit entries yet" hint="Ask the copilot a question or open the dashboard, then refresh." />
        ) : (
          <div className="max-h-[36rem] overflow-auto rounded-xl border border-line">
            <table className="w-full min-w-max text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-raised text-ink2">
                <tr>
                  {["Time", "User", "Action", "Request", "Rows", "Latency", "Status"].map((h) => (
                    <th key={h} scope="col" className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <Fragment key={e.id}>
                    <tr
                      className={`cursor-pointer border-t border-line transition-colors hover:bg-raised ${open === e.id ? "bg-raised" : ""}`}
                      onClick={() => setOpen(open === e.id ? null : e.id)}
                      data-testid="audit-row"
                    >
                      <td className="num whitespace-nowrap px-4 py-2.5 text-ink2">{new Date(e.ts).toLocaleString()}</td>
                      <td className="px-4 py-2.5">
                        <span className="block font-medium text-ink">{e.user}</span>
                        <span className="block text-[11px] text-muted">{e.role}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <code className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink">{e.tool}</code>
                      </td>
                      <td className="max-w-sm truncate px-4 py-2.5 text-ink2" title={summarize(e)}>
                        {summarize(e)}
                      </td>
                      <td className="num px-4 py-2.5">{e.row_count ?? "-"}</td>
                      <td className="num px-4 py-2.5">{e.latency_ms} ms</td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={e.status} />
                      </td>
                    </tr>
                    {open === e.id && (
                      <tr className="bg-raised">
                        <td colSpan={7} className="px-4 pb-4 pt-1 text-xs">
                          {e.error && <p className="mb-2 text-bad">{e.error}</p>}
                          <div className="grid gap-3 lg:grid-cols-2">
                            <div>
                              <p className="mb-1 font-semibold text-ink">Arguments</p>
                              <pre className="max-h-56 overflow-auto rounded-lg bg-sunken p-2.5 font-mono text-[11px]">{JSON.stringify(e.args, null, 2)}</pre>
                            </div>
                            <div>
                              <p className="mb-1 font-semibold text-ink">Semantic-layer query executed</p>
                              <pre className="max-h-56 overflow-auto rounded-lg bg-sunken p-2.5 font-mono text-[11px]">
                                {e.cube_query ? JSON.stringify(e.cube_query, null, 2) : "none (no data query)"}
                              </pre>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        ))}
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
  const pct = (v: number | null) => (v === null ? "n/a" : `${(v * 100).toFixed(3)}%`);
  return (
    <div className="space-y-4" data-testid="reconciliation">
      <section
        className={`relative overflow-hidden rounded-2xl border p-6 shadow-card ${ok ? "border-good/30 bg-goodsoft" : "border-bad/30 bg-badsoft"}`}
      >
        <div className="flex flex-wrap items-center gap-5">
          <span className={`flex h-14 w-14 items-center justify-center rounded-2xl bg-surface shadow-card ${ok ? "text-good" : "text-bad"}`}>
            {ok ? <CheckCircle2 className="h-8 w-8" aria-hidden /> : <XCircle className="h-8 w-8" aria-hidden />}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xl font-semibold tracking-tight text-ink" data-testid="recon-status">
              {ok ? "Reconciled: marts agree with the general ledger" : "Reconciliation break detected"}
            </p>
            <p className="mt-1 text-sm text-ink2">
              Deposits and loans are compared with GL control totals at each month end; tolerance {(data.tolerance_pct * 100).toFixed(2)}%. Latest month:{" "}
              {data.latest?.month}.
            </p>
          </div>
          {session?.role === "cmo" && (
            <button
              disabled={busy}
              onClick={() => void toggle()}
              data-testid="recon-toggle"
              className="rounded-xl border border-line bg-surface px-4 py-2.5 text-sm font-medium text-ink shadow-card transition hover:shadow-float disabled:opacity-50"
            >
              {data.injected_break_pct === null ? "Demo: inject a GL discrepancy" : "Demo: remove the discrepancy"}
            </button>
          )}
        </div>
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        {data.latest?.checks.map((c) => (
          <Card
            key={c.name}
            title={`${c.name}`}
            subtitle={`Month end ${data.latest?.month}`}
            testId={`recon-${c.name.toLowerCase()}`}
            action={<StatusBadge status={c.status} />}
          >
            <dl className="grid grid-cols-3 gap-3">
              {[
                ["Governed marts", formatByUnit(c.marts, "bdt")],
                ["General ledger", formatByUnit(c.gl, "bdt")],
                ["Difference", `${formatByUnit(c.difference, "bdt")} (${pct(c.difference_pct)})`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-raised p-3">
                  <dt className="text-[11px] font-medium uppercase tracking-wider text-muted">{k}</dt>
                  <dd className="num mt-1 text-sm font-semibold text-ink">{v}</dd>
                </div>
              ))}
            </dl>
          </Card>
        ))}
      </div>
      <Card title="Last six months" subtitle="Difference between governed marts and the general ledger">
        <div className="overflow-auto rounded-xl border border-line">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-raised text-ink2">
              <tr>
                {["Month", "Deposits difference", "Loans difference", "Result"].map((h) => (
                  <th key={h} scope="col" className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...data.history].reverse().map((h) => (
                <tr key={h.month} className="border-t border-line">
                  <td className="px-4 py-2.5 font-medium text-ink">{h.month}</td>
                  {h.checks.map((c) => (
                    <td key={c.name} className="num px-4 py-2.5">
                      {pct(c.difference_pct)}
                    </td>
                  ))}
                  <td className="px-4 py-2.5">
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

const UNIT_TONE: Record<string, "brand" | "gold" | "good" | "neutral"> = { bdt: "gold", percent: "brand", count: "neutral", ratio: "good" };

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
        <Search className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-muted" aria-hidden />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search metrics"
          placeholder="Search metrics and definitions"
          className="w-full rounded-xl border border-line bg-surface py-2.5 pl-10 pr-3 text-sm text-ink shadow-card outline-none focus:border-brand/50"
        />
      </div>
      <p className="text-xs text-ink2">
        {shown.length} certified metrics · {data.conventions[0]}
      </p>
      {shown.length === 0 && <EmptyState title="No metric matches your search" />}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {shown.map((m) => (
          <Card key={m.name} testId="metric-card" className="flex flex-col">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold text-ink">{m.title}</p>
                <p className="font-mono text-xs text-muted">{m.name}</p>
              </div>
              <Pill tone={UNIT_TONE[m.unit] ?? "neutral"}>{m.unit}</Pill>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink2">{m.definition}</p>
            <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 border-t border-line pt-3 text-xs">
              <dt className="text-muted">Owner</dt>
              <dd className="text-ink">{m.owner}</dd>
              <dt className="text-muted">Time basis</dt>
              <dd className="text-ink">{m.time_semantics}</dd>
              <dt className="text-muted">Source</dt>
              <dd className="font-mono text-ink">{m.source_tables.join(", ")}</dd>
              <dt className="text-muted">Break down by</dt>
              <dd className="text-ink">{m.dimensions.map(humanize).join(", ")}</dd>
              {m.caveats && (
                <>
                  <dt className="text-muted">Caveats</dt>
                  <dd className="text-ink">{m.caveats}</dd>
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
    <div className="fade-in">
      <PageHeader
        eyebrow="Governance"
        title="Trust center"
        description="Every question, every query and every definition on the record, plus continuous reconciliation against the general ledger."
        actions={
          <Pill tone="gold">
            <Landmark className="h-3.5 w-3.5" aria-hidden />
            Audit-ready
          </Pill>
        }
      />
      <div role="tablist" aria-label="Trust center sections" className="mb-5 inline-flex flex-wrap gap-1 rounded-xl border border-line bg-surface p-1 shadow-card">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
              tab === t.id ? "bg-gradient-to-br from-brand to-brand2 text-white shadow-card" : "text-ink2 hover:bg-raised hover:text-ink"
            }`}
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
