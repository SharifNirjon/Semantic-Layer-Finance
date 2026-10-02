"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login } from "./api";
import type { Role, Session } from "./types";

export const DEMO_ROLES: { username: string; role: Role; label: string }[] = [
  { username: "cmo", role: "cmo", label: "CMO" },
  { username: "branch_manager_dhaka", role: "branch_manager", label: "Branch manager" },
  { username: "analyst", role: "analyst", label: "Analyst" },
];

interface AuthState {
  session: Session | null;
  /** Bumps on every role switch so pages refetch and visibly change results. */
  epoch: number;
  error: string | null;
  switchTo: (username: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = "gba.session";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const switchTo = useCallback(async (username: string) => {
    try {
      const next = await login(username);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable: session lives in memory only */
      }
      setSession(next);
      setEpoch((e) => e + 1);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cannot reach the API");
    }
  }, []);

  useEffect(() => {
    const restore = async () => {
      let stored: Session | null = null;
      try {
        stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      } catch {
        stored = null;
      }
      if (stored) setSession(stored);
      else await switchTo("cmo");
    };
    void restore();
  }, [switchTo]);

  const value = useMemo(() => ({ session, epoch, error, switchTo }), [session, epoch, error, switchTo]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
