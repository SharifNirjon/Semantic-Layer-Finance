export type Role = "cmo" | "branch_manager" | "analyst";

export interface Session {
  token: string;
  username: string;
  role: Role;
  branch_id: number | null;
  display_name: string;
}

export type Row = Record<string, string | number | null>;

export interface Definition {
  name: string;
  title: string;
  definition: string;
  description?: string;
  owner: string;
  unit: string;
  time_semantics: string;
  source_tables: string[];
  caveats: string | null;
}

export interface Table {
  call_id: string;
  title: string;
  columns: string[];
  rows: Row[];
  display_rows: Record<string, string>[];
}

export interface ChartPayload {
  type: "line" | "bar" | "pie" | "none";
  x: string;
  y: string[];
  series: string | null;
  title: string;
  source_call_id: string;
  data: Row[];
}

export interface ToolCallInfo {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  error: string | null;
  latency_ms: number;
}

export interface ChatResponse {
  answer_text: string;
  tables: Table[];
  chart_spec: ChartPayload | null;
  provenance: {
    metrics_used: string[];
    definitions: Definition[];
    cube_queries: Record<string, unknown>[];
    tool_call_ids: string[];
    tool_calls: ToolCallInfo[];
    executed_as: { user: string; role: string; branch_id: number | null };
  };
  follow_up_suggestions: string[];
  guardrail: { passed: boolean; retried: boolean; unsupported_numbers: string[]; cached: boolean };
  provider: string;
  model: string;
}

export type ChatEvent =
  | { type: "status"; message: string }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; id: string; name: string; ok: boolean; rows: number; latency_ms: number; error: string | null }
  | { type: "answer_start" }
  | { type: "answer_chunk"; text: string }
  | { type: "final"; response: ChatResponse }
  | { type: "error"; message: string };

export interface Block {
  id: string;
  title: string;
  columns: string[];
  rows: Row[];
  display_rows: Record<string, string>[];
  notes: string[];
  metrics_used: string[];
  definitions: Definition[];
  cube_queries: Record<string, unknown>[];
}

export interface Kpi {
  metric: string;
  title: string;
  value: number;
  display: string;
  previous_display: string;
  change: number | null;
  change_display: string;
  change_pct_display: string;
  unit: string;
  definition: string;
  cube_queries: Record<string, unknown>[];
}

export interface DashboardView {
  view: string;
  as_of: string;
  role: string;
  kpis?: Kpi[];
  charts?: Block[];
  tables?: Block[];
}

export interface AuditEntry {
  id: number;
  ts: string;
  user: string;
  role: string;
  tool: string;
  args: Record<string, unknown>;
  cube_query: Record<string, unknown>[] | null;
  row_count: number | null;
  latency_ms: number;
  status: "ok" | "error" | "denied";
  error: string | null;
}

export interface ReconCheck {
  name: string;
  marts: number;
  gl: number;
  difference: number;
  difference_pct: number | null;
  status: "pass" | "fail";
}

export interface Reconciliation {
  tolerance_pct: number;
  as_of: string;
  overall: "pass" | "fail" | "unknown";
  latest: { month: string; checks: ReconCheck[]; status: string } | null;
  history: { month: string; checks: ReconCheck[]; status: string }[];
  injected_break_pct: number | null;
  cube_queries: Record<string, unknown>[];
}

export interface CatalogMetric {
  name: string;
  title: string;
  definition: string;
  unit: string;
  time_semantics: string;
  owner: string;
  caveats: string | null;
  source_tables: string[];
}

export interface Catalog {
  data_available: { from: string; to: string } | null;
  conventions: string[];
  metric_groups: { metrics: CatalogMetric[]; dimensions: string[] }[];
}
