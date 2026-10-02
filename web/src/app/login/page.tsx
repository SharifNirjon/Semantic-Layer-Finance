"use client";

import { ArrowRight, Check, Loader2, Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";

interface DemoAccount {
  username: string;
  role: string;
  display_name: string;
}

const DEMO_PASSWORD = "demo123"; // only offered when the API has demo logins enabled (local development)

function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") && next !== "/login" ? next : "/dashboard";
}

export default function LoginPage() {
  const router = useRouter();
  const { session, ready, signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoAccount[]>([]);

  useEffect(() => {
    if (ready && session) router.replace(nextPath());
  }, [ready, session, router]);

  useEffect(() => {
    fetch(`${API_URL}/demo-users`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setDemo)
      .catch(() => setDemo([]));
  }, []);

  const submit = async (u: string, p: string) => {
    setBusy(true);
    setError(null);
    try {
      await signIn(u, p);
      router.replace(nextPath());
    } catch (e) {
      setError(e instanceof Error && e.message ? e.message : "Sign-in failed. Check your username and password.");
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-nav to-nav2 p-12 text-navink lg:flex lg:flex-col">
        <div className="orb pointer-events-none absolute -right-40 -top-40 h-[28rem] w-[28rem] rounded-full opacity-25 blur-3xl" aria-hidden />
        <div className="flex items-center gap-3">
          <span className="orb flex h-10 w-10 items-center justify-center rounded-xl">
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M3 10 12 4l9 6M5 10v8m4.5-8v8m5-8v8M19 10v8M3 20h18" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="leading-tight">
            <span className="block text-base font-semibold">Governed Banking</span>
            <span className="block text-[11px] font-medium uppercase tracking-[0.14em] text-navmuted">Analytics</span>
          </span>
        </div>
        <div className="relative mt-auto max-w-lg">
          <h1 className="text-4xl font-semibold leading-tight tracking-tight text-white">Every number, one governed definition.</h1>
          <p className="mt-4 text-[15px] leading-relaxed text-navmuted">
            Dashboards and AI answers come from the same certified metrics, filtered to what your role is allowed to see.
          </p>
          <ul className="mt-8 space-y-3 text-sm">
            {["Certified metric definitions", "Role and branch level access", "Every question and query audited"].map((t) => (
              <li key={t} className="flex items-center gap-3">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white/10">
                  <Check className="h-3.5 w-3.5 text-emerald-300" aria-hidden />
                </span>
                {t}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brandsoft text-brand">
            <Lock className="h-5 w-5" aria-hidden />
          </span>
          <h2 className="mt-5 text-2xl font-semibold tracking-tight text-ink">Sign in</h2>
          <p className="mt-1 text-sm text-ink2">Use the account your administrator created for you.</p>

          <form
            className="mt-8 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submit(username, password);
            }}
          >
            <label className="block">
              <span className="text-sm font-medium text-ink">Username</span>
              <input
                id="username"
                data-testid="login-username"
                autoComplete="username"
                autoFocus
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] text-ink shadow-card outline-none focus:border-brand/60"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-ink">Password</span>
              <input
                id="password"
                data-testid="login-password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] text-ink shadow-card outline-none focus:border-brand/60"
              />
            </label>
            {error && (
              <p role="alert" data-testid="login-error" className="rounded-lg bg-badsoft px-3 py-2 text-sm text-bad">
                {error}
              </p>
            )}
            <button
              type="submit"
              data-testid="login-submit"
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-brand to-brand2 px-4 py-2.5 text-[15px] font-medium text-white shadow-card transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ArrowRight className="h-4 w-4" aria-hidden />}
              Sign in
            </button>
          </form>

          {demo.length > 0 && (
            <div className="mt-8 border-t border-line pt-5" data-testid="demo-accounts">
              <p className="text-xs font-semibold uppercase tracking-wider text-muted">Demo accounts (development only)</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {demo.map((d) => (
                  <button
                    key={d.username}
                    disabled={busy}
                    onClick={() => void submit(d.username, DEMO_PASSWORD)}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-ink2 shadow-card hover:border-brand/50 hover:text-brand disabled:opacity-50"
                  >
                    {ROLE_LABELS[d.role] ?? d.role}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
