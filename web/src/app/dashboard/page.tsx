"use client";

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import Chart from "@/components/Chart";
import DataTable from "@/components/DataTable";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Block, DashboardView, Kpi } from "@/lib/types";

/** Presentation only: whether an increase is good news for the metric. */
const HIGHER_IS_BETTER: Record<string, boolean> = {
  total_deposits: true,
  casa_ratio: true,
  nim: true,
  active_customers: true,
  npl_ratio: false,
  churn_rate: false,
};

type Views = Partial<Record<"overview" | "segments" | "branches" | "campaigns", DashboardView>>;

function unitLookup(block: Block) {
  return (metric: string) => block.definitions.find((d) => d.name === metric)?.unit ?? "count";
}

function KpiCard({ k }: { k: Kpi }) {
  const dir = k.change === null || k.change === 0 ? 0 : k.change > 0 ? 1 : -1;
  const good = dir === 0 ? null : (dir > 0) === (HIGHER_IS_BETTER[k.metric] ?? true);
  const Icon = dir > 0 ? ArrowUpRight : dir < 0 ? ArrowDownRight : Minus;
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-sm" data-testid="kpi-card" title={k.definition}>
      <p className="text-xs font-medium text-ink2">{k.title}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-ink" data-testid="kpi-value">
        {k.display}
      </p>
      <p className={`mt-2 flex items-center gap-1 text-xs font-medium ${good === null ? "text-ink2" : good ? "text-good" : "text-bad"}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {k.change_display} <span className="font-normal text-muted">vs previous month ({k.previous_display})</span>
      </p>
    </div>
  );
}

function SectionSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" data-testid="dashboard-skeleton">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-72" />
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { session, epoch } = useAuth();
  if (!session) return <SectionSkeleton />;
  // remount on role switch so the numbers visibly change
  return <DashboardBody key={`${session.username}-${epoch}`} token={session.token} />;
}

function DashboardBody({ token }: { token: string }) {
  const [views, setViews] = useState<Views | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const names = ["overview", "segments", "branches", "campaigns"] as const;
    let live = true;
    Promise.all(names.map((n) => api<DashboardView>(`/dashboard/${n}`, token)))
      .then((res) => live && setViews(Object.fromEntries(names.map((n, i) => [n, res[i]])) as Views))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Failed to load"));
    return () => {
      live = false;
    };
  }, [token, attempt]);

  const load = () => {
    setViews(null);
    setError(null);
    setAttempt((a) => a + 1);
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!views) return <SectionSkeleton />;

  const { overview, segments, branches, campaigns } = views;
  const kpis = overview?.kpis ?? [];
  const charts = overview?.charts ?? [];
  const byId = (id: string) => charts.find((c) => c.id === id);
  const deposits = byId("deposits");
  const npl = byId("npl");
  const nim = byId("nim");
  const churn = byId("churn_segment");
  const channels = byId("channels");

  if (kpis.length === 0) return <EmptyState title="No data for this role" hint="The signed-in role has no rows in the selected period." />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">Executive dashboard</h1>
        <p className="text-xs text-ink2" data-testid="as-of">
          Data as of {overview?.as_of} · every figure traces to a governed metric definition (hover a card for its definition)
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6" data-testid="kpi-grid">
        {kpis.map((k) => (
          <KpiCard key={k.metric} k={k} />
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {deposits && (
          <>
            <Card testId="chart-deposits">
              <Chart title="Total deposits (month end)" type="line" rows={deposits.rows} displayRows={deposits.display_rows} columns={deposits.columns} x="period" y={["total_deposits"]} unitOf={unitLookup(deposits)} />
            </Card>
            <Card testId="chart-casa">
              <Chart title="CASA ratio" type="line" rows={deposits.rows} displayRows={deposits.display_rows} columns={deposits.columns} x="period" y={["casa_ratio"]} unitOf={unitLookup(deposits)} />
            </Card>
          </>
        )}
        {npl && (
          <Card testId="chart-npl">
            <Chart title="NPL ratio" type="line" rows={npl.rows} displayRows={npl.display_rows} columns={npl.columns} x="period" y={["npl_ratio"]} unitOf={unitLookup(npl)} />
          </Card>
        )}
        {nim && (
          <Card testId="chart-nim">
            <Chart title="Net interest margin (annualised)" type="line" rows={nim.rows} displayRows={nim.display_rows} columns={nim.columns} x="period" y={["nim"]} unitOf={unitLookup(nim)} />
          </Card>
        )}
        {churn && (
          <Card testId="chart-churn">
            <Chart title="Monthly churn rate by segment" type="line" rows={churn.rows} displayRows={churn.display_rows} columns={churn.columns} x="period" y={["churn_rate"]} series="segment" unitOf={unitLookup(churn)} />
          </Card>
        )}
        {channels && (
          <Card testId="chart-channels">
            <Chart title="Transactions by channel" type="line" rows={channels.rows} displayRows={channels.display_rows} columns={channels.columns} x="period" y={["txn_count"]} series="channel" unitOf={unitLookup(channels)} />
          </Card>
        )}
      </div>

      {segments?.tables?.[0] && (
        <Card title="Segments (latest quarter)" testId="table-segments">
          <DataTable columns={segments.tables[0].columns} rows={segments.tables[0].display_rows} />
        </Card>
      )}
      {branches?.tables?.[0] && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Branches (latest month)" testId="table-branches">
            <DataTable columns={branches.tables[0].columns} rows={branches.tables[0].display_rows} />
          </Card>
          {branches.charts?.[0] && (
            <Card testId="chart-npl-region">
              <Chart title="NPL ratio by region (quarterly)" type="line" rows={branches.charts[0].rows} displayRows={branches.charts[0].display_rows} columns={branches.charts[0].columns} x="period" y={["npl_ratio"]} series="region" unitOf={unitLookup(branches.charts[0])} />
            </Card>
          )}
        </div>
      )}
      {campaigns?.tables?.[0] && (
        <Card title="Campaign performance (sorted by cost per acquired customer)" testId="table-campaigns">
          <DataTable columns={campaigns.tables[0].columns} rows={campaigns.tables[0].display_rows} />
        </Card>
      )}
    </div>
  );
}
