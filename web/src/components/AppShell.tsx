"use client";

import { LayoutDashboard, LogOut, Menu, MessageSquareText, Moon, ShieldCheck, Sun, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { assistantName, useHealth } from "@/lib/health";

const NAV = [
  { href: "/dashboard", label: "Executive dashboard", hint: "KPIs, trends, network", icon: LayoutDashboard },
  { href: "/copilot", label: "Ask", hint: "Questions in plain English", icon: MessageSquareText },
  { href: "/trust", label: "Trust center", hint: "Audit, GL, definitions", icon: ShieldCheck },
];
const ADMIN_NAV = { href: "/admin", label: "Users", hint: "Accounts and access", icon: Users };

const SCOPE: Record<string, string> = {
  cmo: "Bank-wide access",
  branch_manager: "Data is limited to this branch",
  analyst: "Aggregates only, no customer-level data",
};

function subscribeTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

function ThemeToggle() {
  const dark = useSyncExternalStore(
    subscribeTheme,
    () => document.documentElement.dataset.theme === "dark",
    () => false,
  );
  const toggle = () => {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("gba.theme", next);
    } catch {
      /* ignore */
    }
  };
  return (
    <button
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-navmuted transition hover:bg-white/5 hover:text-navink"
    >
      {dark ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
    </button>
  );
}

function initials(name: string) {
  return name
    .split(/[\s,]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

function Brand() {
  return (
    <Link href="/dashboard" className="flex items-center gap-3">
      <span className="orb flex h-9 w-9 items-center justify-center rounded-xl shadow-lg shadow-blue-900/40">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 10 12 4l9 6M5 10v8m4.5-8v8m5-8v8M19 10v8M3 20h18" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="leading-tight">
        <span className="block text-[15px] font-semibold tracking-tight text-navink">Governed Banking</span>
        <span className="block text-[11px] font-medium uppercase tracking-[0.14em] text-navmuted">Analytics</span>
      </span>
    </Link>
  );
}

function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const path = usePathname();
  const { session, signOut } = useAuth();
  const { health } = useHealth();
  return (
    <div className="flex h-full flex-col gap-6 bg-gradient-to-b from-nav to-nav2 px-4 py-5 text-navink">
      <div className="flex items-center justify-between px-1">
        <Brand />
      </div>

      <nav aria-label="Primary" className="flex flex-col gap-1">
        <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-navmuted">Workspace</p>
        {[...NAV, ...(session?.is_admin ? [ADMIN_NAV] : [])].map((n) => {
          const active = path.startsWith(n.href);
          const label = n.href === "/copilot" ? `Ask ${assistantName(health)}` : n.label;
          return (
            <Link
              key={n.href}
              href={n.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 transition ${
                active ? "bg-white/10 text-white shadow-inner ring-1 ring-white/10" : "text-navmuted hover:bg-white/5 hover:text-navink"
              }`}
            >
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-lg ${active ? "bg-gradient-to-br from-[#3b6cf6] to-[#6d5cf5] text-white" : "bg-white/5"}`}
              >
                <n.icon className="h-4 w-4" aria-hidden />
              </span>
              <span className="leading-tight">
                <span className="block text-sm font-medium">{label}</span>
                <span className="block text-[11px] text-navmuted">{n.hint}</span>
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex flex-col gap-3">
        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-navmuted">Viewing as</p>
          {session && (
            <div data-testid="role-banner" className="mt-2 flex items-center gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#f5c96a] to-[#c8902a] text-xs font-bold text-[#1f1503]">
                {initials(session.display_name)}
              </span>
              <span className="min-w-0 leading-tight">
                <span className="block truncate text-sm font-medium text-white">{session.display_name}</span>
                <span className="block text-[11px] text-navmuted">{SCOPE[session.role]}</span>
              </span>
            </div>
          )}
          {session && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="rounded-md bg-white/10 px-2 py-1 text-[11px] font-medium text-navink">
                {ROLE_LABELS[session.role] ?? session.role}
                {session.is_admin ? " · Admin" : ""}
              </span>
              <button
                data-testid="sign-out"
                onClick={signOut}
                className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-navmuted transition hover:bg-white/10 hover:text-navink"
              >
                <LogOut className="h-3.5 w-3.5" aria-hidden />
                Sign out
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 px-1">
          <span className="flex min-w-0 items-center gap-2 text-[11px] text-navmuted" data-testid="model-status">
            <span className={`h-2 w-2 shrink-0 rounded-full ${health?.llm_configured ? "bg-emerald-400 shadow-[0_0_8px] shadow-emerald-400" : "bg-amber-400"}`} aria-hidden />
            <span className="truncate">
              {health?.llm ? `${health.llm.provider} · ${health.llm.model}` : health ? "AI model not configured" : "Connecting..."}
            </span>
          </span>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const router = useRouter();
  const { session, ready, signedOutByUser } = useAuth();
  const isLogin = path.startsWith("/login");

  useEffect(() => {
    // an expired session returns to this page after sign-in; a deliberate sign-out starts fresh
    if (ready && !session && !isLogin) router.replace(signedOutByUser ? "/login" : `/login?next=${encodeURIComponent(path)}`);
  }, [ready, session, isLogin, path, router, signedOutByUser]);

  if (isLogin) return <>{children}</>;
  if (!ready || !session) return <div className="min-h-screen bg-page" aria-busy="true" />;
  return (
    <div className="min-h-screen lg:pl-[272px]">
      {/* Single sidebar instance: fixed on desktop, off-canvas drawer on small screens. */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-[272px] transition-transform duration-200 lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <Sidebar onNavigate={() => setOpen(false)} />
        <button
          onClick={() => setOpen(false)}
          aria-label="Close menu"
          className="absolute right-3 top-5 rounded-lg p-1.5 text-navmuted hover:bg-white/10 lg:hidden"
        >
          <X className="h-5 w-5" aria-hidden />
        </button>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}

      <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-3 backdrop-blur lg:hidden">
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-lg border border-line p-2 text-ink2">
          <Menu className="h-4 w-4" aria-hidden />
        </button>
        <span className="text-sm font-semibold text-ink">Governed Banking Analytics</span>
      </div>

      <main className="mx-auto w-full max-w-[1440px] px-4 pb-10 pt-6 sm:px-6 lg:px-10 lg:pt-8">{children}</main>
    </div>
  );
}
