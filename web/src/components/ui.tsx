"use client";

import { AlertTriangle, CheckCircle2, Inbox, ShieldAlert, XCircle } from "lucide-react";
import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function Card({
  title,
  action,
  children,
  className = "",
  testId,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section data-testid={testId} className={`rounded-xl border border-line bg-surface p-4 shadow-sm ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-line bg-surface p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-bad" aria-hidden />
      <div className="flex-1">
        <p className="font-medium text-ink">Something went wrong</p>
        <p className="mt-1 break-words text-ink2">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-3 rounded-md border border-line px-3 py-1.5 text-xs font-medium hover:bg-raised">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line p-8 text-center">
      <Inbox className="h-6 w-6 text-muted" aria-hidden />
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-md text-xs text-ink2">{hint}</p>}
    </div>
  );
}

const STATUS_STYLES = {
  ok: { icon: CheckCircle2, cls: "text-good", label: "OK" },
  pass: { icon: CheckCircle2, cls: "text-good", label: "Pass" },
  error: { icon: XCircle, cls: "text-bad", label: "Error" },
  fail: { icon: XCircle, cls: "text-bad", label: "Fail" },
  denied: { icon: ShieldAlert, cls: "text-warn", label: "Denied" },
} as const;

/** Status never relies on color alone: icon + label. */
export function StatusBadge({ status }: { status: keyof typeof STATUS_STYLES }) {
  const s = STATUS_STYLES[status];
  const Icon = s.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${s.cls}`}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {s.label}
    </span>
  );
}

export function Collapsible({ title, children, testId }: { title: string; children: ReactNode; testId?: string }) {
  return (
    <details data-testid={testId} className="group rounded-lg border border-line bg-page/50 open:bg-page/80">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold text-ink2 hover:text-ink">{title}</summary>
      <div className="border-t border-line px-3 py-3 text-xs text-ink2">{children}</div>
    </details>
  );
}
