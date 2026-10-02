"use client";

import { ArrowDownRight, ArrowUpRight, CalendarDays, Info, Minus, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import Chart from "@/components/Chart";
import DataTable from "@/components/DataTable";
import Sparkline from "@/components/Sparkline";
import { Card, EmptyState, ErrorState, PageHeader, Pill, SectionTitle, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Block, DashboardView, Kpi, Row } from "@/lib/types";

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

function KpiCard({ k, trend }: { k: Kpi; trend: Row[] | null }) {
  const dir = k.change === null || k.change === 0 ? 0 : k.change > 0 ? 1 : -1;
  const good = dir === 0 ? null : (dir > 0) === (HIGHER_IS_BETTER[k.metric] ?? true);
  const Icon = dir > 0 ? ArrowUpRight : dir < 0 ? ArrowDownRight : Minus;
  const tone = good === null ? "bg-sunken text-ink2" : good ? "bg-goodsoft text-good" : "bg-badsoft text-bad";
  return (
    <div
      className="group flex flex-col rounded-2xl border border-line bg-surface p-4 shadow-card transition hover:-translate-y-0.5 hover:shadow-float"
      data-testid="kpi-card"
      title={k.definition}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium leading-snug text-ink2">{k.title}</p>
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted opacity-0 transition group-hover:opacity-100" aria-hidden />
      </div>
      <p className="num mt-2 text-[22px] sm:text-[26px] font-semibold leading-tight text-ink" data-testid="kpi-value">
        {k.display}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-semibold ${tone}`}>
          <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {k.change_display}
        </span>
        <span className="text-[11px] text-muted">vs prior month</span>
      </div>
      <div className="mt-auto pt-3">
        {trend ? (
          <Sparkline rows={trend} y={k.metric} color="var(--brand)" />
        ) : (
          <p className="line-clamp-2 h-12 pt-1 text-[11px] leading-snug text-muted">{k.definition}</p>
        )}
        <p className="mt-1 truncate text-[11px] text-muted">Previous: {k.previous_display}</p>
      </div>
    </div>
  );
}

function SectionSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" data-testid="dashboard-skeleton">
      <Skeleton className="h-20" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-80" />
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
  const { session } = useAuth();
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
  // KPI sparklines reuse the monthly trend blocks already fetched (same governed metric, same role)
  const trendFor = (metric: string) => charts.find((c) => c.columns.includes(metric) && !c.columns.some((col) => ["segment", "channel"].includes(col)))?.rows ?? null;

  if (kpis.length === 0) return <EmptyState title="No data for this role" hint="The signed-in role has no rows in the selected period." />;

  return (
    <div className="fade-in">
      <PageHeader
        eyebrow="Executive overview"
        title={session?.role === "branch_manager" ? "Branch performance" : "Bank performance at a glance"}
        description="Every figure traces to a certified metric in the governed semantic layer. Hover a tile for its definition."
        actions={
          <>
            <Pill tone="brand">
              <CalendarDays className="h-3.5 w-3.5" aria-hidden />
              <span data-testid="as-of">Data as of {overview?.as_of}</span>
            </Pill>
            <Pill tone="gold">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
              Certified metrics
            </Pill>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6" data-testid="kpi-grid">
        {kpis.map((k) => (
          <KpiCard key={k.metric} k={k} trend={trendFor(k.metric)} />
        ))}
      </div>

      <SectionTitle title="Balance sheet" hint="Month-end balances" />
      <div className="grid gap-4 lg:grid-cols-2">
        {deposits && (
          <>
            <Card testId="chart-deposits">
              <Chart title="Total deposits" subtitle="Month end, BDT" type="line" rows={deposits.rows} displayRows={deposits.display_rows} columns={deposits.columns} x="period" y={["total_deposits"]} unitOf={unitLookup(deposits)} />
            </Card>
            <Card testId="chart-casa">
              <Chart title="CASA ratio" subtitle="Current + savings share of deposits" type="line" rows={deposits.rows} displayRows={deposits.display_rows} columns={deposits.columns} x="period" y={["casa_ratio"]} unitOf={unitLookup(deposits)} />
            </Card>
          </>
        )}
      </div>

      <SectionTitle title="Risk and profitability" />
      <div className="grid gap-4 lg:grid-cols-2">
        {npl && (
          <Card testId="chart-npl">
            <Chart title="NPL ratio" subtitle="Non-performing share of loans outstanding" type="line" rows={npl.rows} displayRows={npl.display_rows} columns={npl.columns} x="period" y={["npl_ratio"]} unitOf={unitLookup(npl)} />
          </Card>
        )}
        {nim && (
          <Card testId="chart-nim">
            <Chart title="Net interest margin" subtitle="Annualised" type="line" rows={nim.rows} displayRows={nim.display_rows} columns={nim.columns} x="period" y={["nim"]} unitOf={unitLookup(nim)} />
          </Card>
        )}
      </div>

      <SectionTitle title="Customers and channels" />
      <div className="grid gap-4 lg:grid-cols-2">
        {churn && (
          <Card testId="chart-churn">
            <Chart title="Monthly churn rate by segment" subtitle="Segment as of the business date" type="line" rows={churn.rows} displayRows={churn.display_rows} columns={churn.columns} x="period" y={["churn_rate"]} series="segment" unitOf={unitLookup(churn)} />
          </Card>
        )}
        {channels && (
          <Card testId="chart-channels">
            <Chart title="Transactions by channel" subtitle="Monthly count" type="line" rows={channels.rows} displayRows={channels.display_rows} columns={channels.columns} x="period" y={["txn_count"]} series="channel" unitOf={unitLookup(channels)} />
          </Card>
        )}
      </div>

      {segments?.tables?.[0] && (
        <>
          <SectionTitle title="Segments" hint="Latest quarter" />
          <Card testId="table-segments">
            <DataTable columns={segments.tables[0].columns} rows={segments.tables[0].display_rows} rawRows={segments.tables[0].rows} bars={["total_deposits"]} />
          </Card>
        </>
      )}
      {branches?.tables?.[0] && (
        <>
          <SectionTitle title="Branch network" hint="Latest month" />
          <div className="grid gap-4 xl:grid-cols-5">
            <Card title="Branches" subtitle="Ranked by total deposits" testId="table-branches" className="xl:col-span-3">
              <DataTable columns={branches.tables[0].columns} rows={branches.tables[0].display_rows} rawRows={branches.tables[0].rows} bars={["total_deposits"]} maxHeight="max-h-[26rem]" />
            </Card>
            {branches.charts?.[0] && (
              <Card testId="chart-npl-region" className="xl:col-span-2">
                <Chart title="NPL ratio by region" subtitle="Quarterly" type="line" rows={branches.charts[0].rows} displayRows={branches.charts[0].display_rows} columns={branches.charts[0].columns} x="period" y={["npl_ratio"]} series="region" unitOf={unitLookup(branches.charts[0])} height="h-80" />
              </Card>
            )}
          </div>
        </>
      )}
      {campaigns?.tables?.[0] && (
        <>
          <SectionTitle title="Marketing campaigns" hint="Sorted by cost per acquired customer" />
          <Card testId="table-campaigns">
            <DataTable columns={campaigns.tables[0].columns} rows={campaigns.tables[0].display_rows} rawRows={campaigns.tables[0].rows} bars={["cac"]} titles={{ cac: "Cost per acquisition" }} />
          </Card>
        </>
      )}
    </div>
  );
}
