"use client";

import { Loader2, RotateCcw, Send, Sparkles, Wrench } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import ResponseCard from "@/components/ResponseCard";
import { ErrorState } from "@/components/ui";
import { API_URL, api, streamChat } from "@/lib/api";
import { useAuth } from "@/lib/auth";
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
  const [llmError, setLlmError] = useState<string | null>(null);
  const [apiDown, setApiDown] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((h) => setLlmError(h.llm_configured ? null : (h.llm_error ?? "No language model is configured.")))
      .catch((e) => setApiDown(e instanceof Error ? e.message : "API unreachable"));
  }, []);

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
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      {apiDown && <ErrorState message={`The API is not reachable (${apiDown}). Start the stack with "make up".`} />}
      {llmError && (
        <div role="status" className="rounded-xl border border-line bg-surface p-4 text-sm text-ink2" data-testid="llm-banner">
          <p className="font-medium text-ink">The AI model is not configured yet.</p>
          <p className="mt-1">{llmError} Add a key to <code>.env</code> and restart the api service. Dashboards and the Trust center work without it.</p>
        </div>
      )}

      {turns.length === 0 && (
        <div className="py-10 text-center" data-testid="copilot-empty">
          <Sparkles className="mx-auto h-8 w-8 text-brand" aria-hidden />
          <h1 className="mt-3 text-2xl font-semibold text-ink">Ask the governed analytics copilot</h1>
          <p className="mx-auto mt-2 max-w-xl text-sm text-ink2">
            Every number comes from a certified metric definition. Answers show their chart, table, definition and the exact query that produced them.
          </p>
        </div>
      )}

      <ol className="flex flex-col gap-6" aria-live="polite">
        {turns.map((t) => (
          <li key={t.id} className="flex flex-col gap-2" data-testid="turn">
            <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-brand px-4 py-2 text-sm text-brandink" data-testid="user-message">
              {t.question}
              <div className="mt-1 text-[11px] opacity-80">as {t.askedAs}</div>
            </div>
            <div className="max-w-full rounded-2xl rounded-bl-sm border border-line bg-surface p-4" data-testid="assistant-message">
              {t.steps.length > 0 && (
                <ul className="mb-3 flex flex-wrap gap-2" aria-label="Steps taken">
                  {t.steps.map((s) => (
                    <li key={s.id} className="flex items-center gap-1.5 rounded-full border border-line bg-page px-2.5 py-1 text-[11px] text-ink2" data-testid="tool-step">
                      {s.state === "running" ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : <Wrench className="h-3 w-3" aria-hidden />}
                      <span className="font-medium text-ink">{s.name}</span>
                      <span className="max-w-[16rem] truncate">{describe(s.args)}</span>
                      {s.state !== "running" && <span>{s.state === "error" ? "failed" : `${s.rows ?? 0} rows, ${s.ms} ms`}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {!t.done && !t.answer && (
                <p className="flex items-center gap-2 text-sm text-ink2">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {t.status}...
                </p>
              )}
              {t.error && <ErrorState message={t.error} />}
              {t.answer && (
                <p data-testid="answer-text" className={`whitespace-pre-wrap text-sm leading-relaxed text-ink ${!t.done && !t.response ? "caret" : ""}`}>
                  {t.answer}
                </p>
              )}
              {t.response && <ResponseCard response={t.response} />}
              {t.done && session && t.askedAs !== session.display_name && (
                <button
                  onClick={() => void ask(t.question)}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-brand hover:bg-raised"
                  data-testid="reask"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden /> Ask again as {session.display_name}
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
      <div ref={bottom} />

      <div className="sticky bottom-0 -mx-4 border-t border-line bg-page/95 px-4 pb-4 pt-3 backdrop-blur">
        {chips.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2" data-testid="suggestions">
            {chips.map((c) => (
              <button
                key={c}
                disabled={busy || !!llmError}
                onClick={() => void ask(c)}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-xs text-ink2 hover:border-brand hover:text-brand disabled:opacity-50"
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
          className="flex gap-2"
        >
          <input
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about churn, deposits, NPL, campaigns..."
            aria-label="Your question"
            maxLength={2000}
            className="flex-1 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm text-ink placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={busy || !input.trim() || !!llmError}
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-brandink disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}
