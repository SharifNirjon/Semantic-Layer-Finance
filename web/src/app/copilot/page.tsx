"use client";

import { ArrowUp, BadgeCheck, Check, Database, Loader2, Lock, RotateCcw, Sparkles, TrendingUp, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import ResponseCard, { VerifiedBadge } from "@/components/ResponseCard";
import { ErrorState } from "@/components/ui";
import { api, streamChat } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { assistantName, useHealth } from "@/lib/health";
import type { ChatEvent, ChatResponse } from "@/lib/types";

interface Step {
  id: string;
  name: string;
  args: Record<string, unknown>;
  state: "running" | "ok" | "error";
  rows?: number;
  ms?: number;
}

interface Turn {
  id: number;
  question: string;
  askedAs: string;
  status: string;
  steps: Step[];
  answer: string;
  response?: ChatResponse;
  error?: string;
  done: boolean;
}

const ICONS = [TrendingUp, Database, Sparkles, BadgeCheck];

function describe(args: Record<string, unknown>): string {
  const metrics = (args.metrics ?? (args.metric ? [args.metric] : [])) as string[];
  const dims = (args.dimensions ?? (args.dimension ? [args.dimension] : [])) as string[];
  return [metrics.join(", "), dims.length ? `by ${dims.join(", ")}` : ""].filter(Boolean).join(" ");
}

export default function CopilotPage() {
  const { session, epoch } = useAuth();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const { health, down: apiDown } = useHealth();
  const llmError = health && !health.llm_configured ? (health.llm_error ?? "No language model is configured.") : null;
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!session) return;
    api<string[]>("/suggestions", session.token)
      .then(setSuggestions)
      .catch(() => setSuggestions([]));
  }, [session, epoch]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const patch = useCallback((id: number, fn: (t: Turn) => Turn) => setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t))), []);

  const ask = useCallback(
    async (question: string) => {
      if (!session || !question.trim() || busy) return;
      const id = Date.now();
      const history = turns.filter((t) => t.response).slice(-3).flatMap((t) => [
        { role: "user", text: t.question },
        { role: "assistant", text: t.response?.answer_text ?? "" },
      ]);
      setTurns((all) => [...all, { id, question, askedAs: session.display_name, status: "Starting", steps: [], answer: "", done: false }]);
      setInput("");
      setBusy(true);
      abort.current = new AbortController();
      const onEvent = (e: ChatEvent) => {
        if (e.type === "status") patch(id, (t) => ({ ...t, status: e.message }));
        else if (e.type === "tool_call") patch(id, (t) => ({ ...t, steps: [...t.steps, { id: e.id, name: e.name, args: e.arguments, state: "running" }] }));
        else if (e.type === "tool_result")
          patch(id, (t) => ({
            ...t,
            steps: t.steps.map((s) => (s.id === e.id ? { ...s, state: e.ok ? "ok" : "error", rows: e.rows, ms: e.latency_ms } : s)),
          }));
        else if (e.type === "answer_chunk") patch(id, (t) => ({ ...t, answer: t.answer + e.text }));
        else if (e.type === "final") patch(id, (t) => ({ ...t, response: e.response, answer: e.response.answer_text, done: true }));
        else if (e.type === "error") patch(id, (t) => ({ ...t, error: e.message, done: true }));
      };
      try {
        await streamChat(session.token, question, history, onEvent, abort.current.signal);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Request failed";
        patch(id, (t) => ({ ...t, error: message, done: true }));
      } finally {
        patch(id, (t) => ({ ...t, done: true }));
        setBusy(false);
      }
    },
    [session, busy, turns, patch],
  );

  const followUps = turns.at(-1)?.response?.follow_up_suggestions ?? [];
  const chips = followUps.length ? followUps : suggestions;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-4xl flex-col gap-5">
      {apiDown && <ErrorState message={`The API is not reachable (${apiDown}). Start the stack with "make up".`} />}
      {llmError && (
        <div role="status" className="flex gap-3 rounded-2xl border border-line bg-warnsoft/60 p-4 text-sm text-ink2" data-testid="llm-banner">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
          <div>
            <p className="font-medium text-ink">The AI model is not configured yet.</p>
            <p className="mt-1">
              {llmError} Add a key to <code className="font-mono">.env</code> and restart the api service. Dashboards and the Trust center work without it.
            </p>
          </div>
        </div>
      )}

      {turns.length === 0 && (
        <div className="fade-in flex flex-1 flex-col items-center justify-center py-8 text-center" data-testid="copilot-empty">
          <span className="orb flex h-14 w-14 items-center justify-center rounded-2xl shadow-float">
            <Sparkles className="h-7 w-7 text-white" aria-hidden />
          </span>
          <h1 className="mt-5 text-3xl font-semibold tracking-tight text-ink">Ask {assistantName(health)} about the bank</h1>
          <p className="mx-auto mt-2 max-w-xl text-[15px] text-ink2">
            Ask about deposits, churn, risk or campaigns. Every answer shows its chart, table, certified definition and the exact query that produced it.
          </p>
          <ul className="mt-5 flex flex-wrap justify-center gap-2 text-xs text-ink2">
            {["Certified metrics only", "Role-aware row security", "Every figure verified", "No SQL, no raw tables"].map((t) => (
              <li key={t} className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 shadow-card">
                <Check className="h-3.5 w-3.5 text-good" aria-hidden />
                {t}
              </li>
            ))}
          </ul>
          {suggestions.length > 0 && (
            <div className="mt-8 grid w-full gap-3 text-left sm:grid-cols-2" data-testid="suggestions">
              {suggestions.slice(0, 6).map((c, i) => {
                const Icon = ICONS[i % ICONS.length];
                return (
                  <button
                    key={c}
                    disabled={busy || !!llmError}
                    onClick={() => void ask(c)}
                    className="group flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 text-left text-sm text-ink shadow-card transition hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-float disabled:pointer-events-none disabled:opacity-50"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brandsoft text-brand">
                      <Icon className="h-4 w-4" aria-hidden />
                    </span>
                    <span className="leading-snug">{c}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <ol className="flex flex-col gap-8" aria-live="polite">
        {turns.map((t) => (
          <li key={t.id} className="fade-in flex flex-col gap-3" data-testid="turn">
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-brand to-brand2 px-4 py-3 text-[15px] text-white shadow-card" data-testid="user-message">
              {t.question}
              <div className="mt-1 text-[11px] text-white/75">as {t.askedAs}</div>
            </div>
            <div className="flex gap-3">
              <span className="orb mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl" aria-hidden>
                <Sparkles className="h-4 w-4 text-white" />
              </span>
              <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-line bg-surface p-5 shadow-card" data-testid="assistant-message">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-ink">{assistantName(health)}</span>
                  {t.response && <VerifiedBadge response={t.response} />}
                </div>
                {t.steps.length > 0 && (
                  <ul className="mb-4 space-y-1.5 border-l-2 border-line pl-3" aria-label="Steps taken">
                    {t.steps.map((s) => (
                      <li key={s.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink2" data-testid="tool-step">
                        {s.state === "running" ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" aria-hidden />
                        ) : s.state === "error" ? (
                          <X className="h-3.5 w-3.5 text-bad" aria-hidden />
                        ) : (
                          <Check className="h-3.5 w-3.5 text-good" aria-hidden />
                        )}
                        <span className="font-mono font-medium text-ink">{s.name}</span>
                        <span className="max-w-[20rem] truncate">{describe(s.args)}</span>
                        {s.state !== "running" && (
                          <span className="text-muted">{s.state === "error" ? "failed" : `${s.rows ?? 0} rows · ${s.ms} ms`}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {!t.done && !t.answer && (
                  <p className="flex items-center gap-2 text-sm text-ink2">
                    <Loader2 className="h-4 w-4 animate-spin text-brand" aria-hidden /> {t.status}...
                  </p>
                )}
                {t.error && <ErrorState message={t.error} />}
                {t.answer && (
                  <p data-testid="answer-text" className={`whitespace-pre-wrap text-[15px] leading-relaxed text-ink ${!t.done && !t.response ? "caret" : ""}`}>
                    {t.answer}
                  </p>
                )}
                {t.response && <ResponseCard response={t.response} />}
                {t.done && session && t.askedAs !== session.display_name && (
                  <button
                    onClick={() => void ask(t.question)}
                    className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-brand hover:bg-raised"
                    data-testid="reask"
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Ask again as {session.display_name}
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
      <div ref={bottom} />

      <div className="sticky bottom-0 -mx-4 mt-auto bg-gradient-to-t from-page via-page to-transparent px-4 pb-5 pt-6 sm:-mx-6 sm:px-6">
        {turns.length > 0 && chips.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2" data-testid="suggestions">
            {chips.map((c) => (
              <button
                key={c}
                disabled={busy || !!llmError}
                onClick={() => void ask(c)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-xs text-ink2 shadow-card transition hover:border-brand/50 hover:text-brand disabled:opacity-50"
              >
                {c}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask(input);
          }}
          className="flex items-center gap-2 rounded-2xl border border-line bg-surface p-2 shadow-float focus-within:border-brand/50"
        >
          <Sparkles className="ml-2 h-4 w-4 shrink-0 text-brand" aria-hidden />
          <input
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about churn, deposits, NPL, campaigns..."
            aria-label="Your question"
            maxLength={2000}
            className="min-w-0 flex-1 bg-transparent px-2 py-2 text-[15px] text-ink outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={busy || !input.trim() || !!llmError}
            aria-label="Ask"
            className="flex h-10 items-center gap-1.5 rounded-xl bg-gradient-to-br from-brand to-brand2 px-4 text-sm font-medium text-white shadow-card transition hover:opacity-90 disabled:opacity-40"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ArrowUp className="h-4 w-4" aria-hidden />}
            Ask
          </button>
        </form>
        <p className="mt-2 text-center text-[11px] text-muted">Answers are computed by the governed semantic layer and checked before they are shown.</p>
      </div>
    </div>
  );
}
