"use client";

import { Landmark, Moon, ShieldCheck, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { DEMO_ROLES, useAuth } from "@/lib/auth";

const NAV = [
  { href: "/copilot", label: "Copilot" },
  { href: "/dashboard", label: "Executive dashboard" },
  { href: "/trust", label: "Trust center" },
];

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
      className="rounded-md border border-line p-2 text-ink2 hover:bg-raised"
    >
      {dark ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
    </button>
  );
}

export default function Header() {
  const path = usePathname();
  const { session, switchTo, error } = useAuth();
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/copilot" className="flex items-center gap-2 font-semibold text-ink">
          <Landmark className="h-5 w-5 text-brand" aria-hidden />
          <span>Governed Banking Analytics</span>
        </Link>
        <nav aria-label="Primary" className="flex gap-1">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={path.startsWith(n.href) ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                path.startsWith(n.href) ? "bg-brandsoft text-brand" : "text-ink2 hover:bg-raised"
              }`}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {error && <span className="text-xs text-bad">API unreachable</span>}
          <label className="flex items-center gap-2 text-xs text-ink2">
            <ShieldCheck className="h-4 w-4 text-brand" aria-hidden />
            <span className="hidden sm:inline">Viewing as</span>
            <select
              data-testid="role-switcher"
              value={session?.username ?? ""}
              onChange={(e) => void switchTo(e.target.value)}
              className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              {DEMO_ROLES.map((r) => (
                <option key={r.username} value={r.username}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <ThemeToggle />
        </div>
      </div>
      {session && (
        <div data-testid="role-banner" className="border-t border-line bg-brandsoft px-4 py-1 text-center text-xs text-brand">
          {session.display_name}
          {session.role === "branch_manager" && " - data is limited to this branch"}
          {session.role === "analyst" && " - aggregates only, no customer-level data"}
        </div>
      )}
    </header>
  );
}
