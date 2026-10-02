"use client";

import { AlertTriangle, CheckCircle2, ChevronRight, Inbox, ShieldAlert, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="hero -mx-4 -mt-6 mb-6 flex flex-wrap items-end justify-between gap-4 px-4 pb-2 pt-6 sm:-mx-6 sm:px-6 lg:-mx-10 lg:-mt-8 lg:px-10 lg:pt-8">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {description && <div className="mt-1.5 max-w-3xl text-sm text-ink2">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-3 mt-8 flex items-baseline justify-between gap-2 first:mt-0">
      <h2 className="text-[13px] font-semibold uppercase tracking-[0.12em] text-ink2">{title}</h2>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Pill({ children, tone = "neutral", className = "" }: { children: ReactNode; tone?: "neutral" | "brand" | "good" | "bad" | "gold"; className?: string }) {
  const tones = {
    neutral: "border-line bg-raised text-ink2",
    brand: "border-transparent bg-brandsoft text-brand",
    good: "border-transparent bg-goodsoft text-good",
    bad: "border-transparent bg-badsoft text-bad",
    gold: "border-transparent bg-goldsoft text-gold",
  };
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${tones[tone]} ${className}`}>{children}</span>;
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
  testId,
}: {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section data-testid={testId} className={`rounded-2xl border border-line bg-surface p-5 shadow-card ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 text-sm shadow-card">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-badsoft">
        <AlertTriangle className="h-5 w-5 text-bad" aria-hidden />
      </span>
      <div className="flex-1">
        <p className="font-medium text-ink">Something went wrong</p>
        <p className="mt-1 break-words text-ink2">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-raised">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-line bg-surface/50 p-10 text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sunken">
        <Inbox className="h-5 w-5 text-muted" aria-hidden />
      </span>
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-md text-xs text-ink2">{hint}</p>}
    </div>
  );
}

const STATUS_STYLES = {
  ok: { icon: CheckCircle2, cls: "bg-goodsoft text-good", label: "OK" },
  pass: { icon: CheckCircle2, cls: "bg-goodsoft text-good", label: "Pass" },
  error: { icon: XCircle, cls: "bg-badsoft text-bad", label: "Error" },
  fail: { icon: XCircle, cls: "bg-badsoft text-bad", label: "Fail" },
  denied: { icon: ShieldAlert, cls: "bg-warnsoft text-warn", label: "Denied" },
} as const;

/** Status never relies on color alone: icon + label. */
export function StatusBadge({ status }: { status: keyof typeof STATUS_STYLES }) {
  const s = STATUS_STYLES[status];
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${s.cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {s.label}
    </span>
  );
}

export function Collapsible({ title, icon, children, testId }: { title: string; icon?: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <details data-testid={testId} className="group rounded-xl border border-line bg-raised/60 open:bg-raised">
      <summary className="flex cursor-pointer select-none items-center gap-2 px-3.5 py-2.5 text-xs font-semibold text-ink2 hover:text-ink">
        <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden />
        {icon}
        {title}
      </summary>
      <div className="border-t border-line px-4 py-3.5 text-xs leading-relaxed text-ink2">{children}</div>
    </details>
  );
}
