"use client";

import { Pencil, Plus, Trash2, UserPlus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Card, EmptyState, ErrorState, PageHeader, Pill, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import type { AppUser, Branch, Role } from "@/lib/types";

const ROLE_HELP: Record<Role, string> = {
  cmo: "All data, bank-wide",
  branch_manager: "Only their branch's data",
  analyst: "Aggregates only, no customer-level data",
};
const FIELD = "mt-1 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-brand/60";

interface Draft {
  username: string;
  display_name: string;
  password: string;
  role: Role;
  branch_id: number | null;
  is_admin: boolean;
  active: boolean;
}

const EMPTY: Draft = { username: "", display_name: "", password: "", role: "analyst", branch_id: null, is_admin: false, active: true };

function UserForm({
  initial,
  editing,
  branches,
  self,
  onSave,
  onDelete,
  onCancel,
}: {
  initial: Draft;
  editing: boolean;
  branches: Branch[];
  self: boolean;
  onSave: (d: Draft) => Promise<void>;
  onDelete?: () => Promise<void>;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(() => onSave(d));
  };

  return (
    <Card
      title={editing ? `Edit ${initial.display_name || initial.username}` : "Add a user"}
      subtitle={editing ? `@${initial.username}` : "They sign in with this username and password."}
      testId="user-form"
      action={
        <button onClick={onCancel} aria-label="Close" className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-ink">
          <X className="h-4 w-4" aria-hidden />
        </button>
      }
    >
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        {!editing && (
          <label className="text-sm font-medium text-ink">
            Username
            <input id="new-username" data-testid="user-username" required value={d.username} onChange={(e) => set("username", e.target.value.toLowerCase())} placeholder="e.g. rahim.uddin" className={FIELD} />
          </label>
        )}
        <label className="text-sm font-medium text-ink">
          Full name
          <input id="display-name" data-testid="user-display-name" value={d.display_name} onChange={(e) => set("display_name", e.target.value)} placeholder="Shown in the app" className={FIELD} />
        </label>
        <label className="text-sm font-medium text-ink">
          {editing ? "New password (leave empty to keep)" : "Password"}
          <input
            id="user-password"
            data-testid="user-password"
            type="password"
            autoComplete="new-password"
            required={!editing}
            minLength={8}
            value={d.password}
            onChange={(e) => set("password", e.target.value)}
            placeholder="At least 8 characters"
            className={FIELD}
          />
        </label>
        <label className="text-sm font-medium text-ink">
          Data access
          <select id="user-role" data-testid="user-role" value={d.role} onChange={(e) => set("role", e.target.value as Role)} className={FIELD}>
            {(Object.keys(ROLE_HELP) as Role[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}: {ROLE_HELP[r]}
              </option>
            ))}
          </select>
        </label>
        {d.role === "branch_manager" && (
          <label className="text-sm font-medium text-ink">
            Branch
            <select
              id="user-branch"
              data-testid="user-branch"
              required
              value={d.branch_id ?? ""}
              onChange={(e) => set("branch_id", e.target.value ? Number(e.target.value) : null)}
              className={FIELD}
            >
              <option value="">Choose a branch</option>
              {branches.map((b) => (
                <option key={b.branch_id} value={b.branch_id}>
                  {b.branch} ({b.region})
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="flex flex-col justify-end gap-2 text-sm text-ink sm:col-span-2 sm:flex-row sm:items-center sm:justify-start sm:gap-6">
          <label className="flex items-center gap-2">
            <input id="user-admin" type="checkbox" checked={d.is_admin} disabled={self} onChange={(e) => set("is_admin", e.target.checked)} />
            Administrator (can manage users)
          </label>
          {editing && (
            <label className="flex items-center gap-2">
              <input id="user-active" type="checkbox" checked={d.active} disabled={self} onChange={(e) => set("active", e.target.checked)} />
              Account active (can sign in)
            </label>
          )}
        </div>
        {error && (
          <p role="alert" className="rounded-lg bg-badsoft px-3 py-2 text-sm text-bad sm:col-span-2">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
          <button
            type="submit"
            data-testid="user-save"
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-br from-brand to-brand2 px-4 py-2 text-sm font-medium text-white shadow-card disabled:opacity-50"
          >
            {editing ? "Save changes" : (<><UserPlus className="h-4 w-4" aria-hidden /> Create user</>)}
          </button>
          <button type="button" onClick={onCancel} className="rounded-lg border border-line px-4 py-2 text-sm text-ink hover:bg-raised">
            Cancel
          </button>
          {editing && onDelete && !self && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                if (window.confirm(`Delete ${initial.username}? This cannot be undone.`)) void run(onDelete);
              }}
              className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-bad hover:bg-badsoft"
            >
              <Trash2 className="h-4 w-4" aria-hidden /> Delete user
            </button>
          )}
        </div>
      </form>
    </Card>
  );
}

export default function AdminPage() {
  const { session } = useAuth();
  const [users, setUsers] = useState<AppUser[] | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ mode: "new" } | { mode: "edit"; user: AppUser } | null>(null);
  const token = session?.token ?? "";

  const reload = useCallback(() => {
    api<AppUser[]>("/admin/users", token)
      .then((u) => {
        setUsers(u);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load users"));
  }, [token]);

  useEffect(() => {
    if (!token || !session?.is_admin) return;
    reload();
    api<Branch[]>("/admin/branches", token)
      .then(setBranches)
      .catch(() => setBranches([]));
  }, [token, session?.is_admin, reload]);

  const branchName = useMemo(() => new Map(branches.map((b) => [b.branch_id, b.branch])), [branches]);

  if (!session?.is_admin) return <ErrorState message="Only an administrator can manage users." />;

  const save = async (d: Draft) => {
    if (form?.mode === "edit") {
      const changes: Record<string, unknown> = { display_name: d.display_name, role: d.role, branch_id: d.branch_id, is_admin: d.is_admin, active: d.active };
      if (d.password) changes.password = d.password;
      await api(`/admin/users/${encodeURIComponent(form.user.username)}`, token, { method: "PATCH", body: JSON.stringify(changes) });
    } else {
      await api("/admin/users", token, { method: "POST", body: JSON.stringify(d) });
    }
    setForm(null);
    reload();
  };

  return (
    <div className="fade-in">
      <PageHeader
        eyebrow="Administration"
        title="Users"
        description="Create accounts and choose what each person can see. Access applies to the dashboard, AI answers and the audit log."
        actions={
          <button
            data-testid="add-user"
            onClick={() => setForm({ mode: "new" })}
            className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-br from-brand to-brand2 px-4 py-2.5 text-sm font-medium text-white shadow-card hover:opacity-90"
          >
            <Plus className="h-4 w-4" aria-hidden /> Add user
          </button>
        }
      />

      {form && (
        <div className="mb-5">
          <UserForm
            key={form.mode === "edit" ? form.user.username : "new"}
            editing={form.mode === "edit"}
            initial={form.mode === "edit" ? { ...form.user, password: "" } : EMPTY}
            branches={branches}
            self={form.mode === "edit" && form.user.username === session.username}
            onSave={save}
            onDelete={
              form.mode === "edit"
                ? async () => {
                    await api(`/admin/users/${encodeURIComponent(form.user.username)}`, token, { method: "DELETE" });
                    setForm(null);
                    reload();
                  }
                : undefined
            }
            onCancel={() => setForm(null)}
          />
        </div>
      )}

      {error && <ErrorState message={error} onRetry={reload} />}
      {!users && !error && <Skeleton className="h-64" />}
      {users &&
        (users.length === 0 ? (
          <EmptyState title="No users yet" hint="Add the first account with the button above." />
        ) : (
          <Card testId="user-list" title={`${users.length} account${users.length === 1 ? "" : "s"}`}>
            <div className="overflow-auto rounded-xl border border-line">
              <table className="w-full min-w-max text-left text-[13px]">
                <thead className="bg-raised text-ink2">
                  <tr>
                    {["Name", "Access", "Branch", "Status", "Last sign-in", ""].map((h) => (
                      <th key={h} scope="col" className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.username} className="border-t border-line" data-testid="user-row">
                      <td className="px-4 py-2.5">
                        <span className="block font-medium text-ink">{u.display_name}</span>
                        <span className="block text-[11px] text-muted">@{u.username}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="flex flex-wrap gap-1.5">
                          <Pill tone="brand">{ROLE_LABELS[u.role]}</Pill>
                          {u.is_admin && <Pill tone="gold">Admin</Pill>}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-ink2">{u.branch_id ? (branchName.get(u.branch_id) ?? `Branch ${u.branch_id}`) : "All branches"}</td>
                      <td className="px-4 py-2.5">{u.active ? <Pill tone="good">Active</Pill> : <Pill tone="bad">Deactivated</Pill>}</td>
                      <td className="num px-4 py-2.5 text-ink2">{u.last_login ? new Date(u.last_login).toLocaleString() : "Never"}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          onClick={() => setForm({ mode: "edit", user: u })}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-raised"
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden /> Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
    </div>
  );
}
