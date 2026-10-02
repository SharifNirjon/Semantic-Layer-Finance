"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { UNAUTHORIZED_EVENT, api, login } from "./api";
import type { Session } from "./types";

export const ROLE_LABELS: Record<string, string> = { cmo: "CMO", branch_manager: "Branch manager", analyst: "Analyst" };

interface AuthState {
  session: Session | null;
  /** False until the stored session has been read, so pages don't flash the sign-in screen. */
  ready: boolean;
  /** Bumps on every sign-in so pages refetch for the new account. */
  epoch: number;
  /** True after the user chose to sign out (the next sign-in starts fresh instead of returning to the old page). */
  signedOutByUser: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = "gba.session";

function store(session: Session | null) {
  try {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: the session lives in memory only */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const [signedOutByUser, setSignedOutByUser] = useState(false);

  const drop = useCallback((byUser: boolean) => {
    store(null);
    setSession(null);
    setSignedOutByUser(byUser);
  }, []);
  const signOut = useCallback(() => drop(true), [drop]);

  const signIn = useCallback(async (username: string, password: string) => {
    const next = await login(username.trim(), password);
    store(next);
    setSession(next);
    setSignedOutByUser(false);
    setEpoch((e) => e + 1);
  }, []);

  useEffect(() => {
    let stored: Session | null = null;
    try {
      stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    } catch {
      stored = null;
    }
    // restore immediately, then refresh name/role/admin from the API (signs out if the account changed)
    const restore = async () => {
      if (!stored?.token) {
        setReady(true);
        return;
      }
      setSession(stored);
      setReady(true);
      try {
        const me = await api<Omit<Session, "token">>("/me", stored.token);
        const fresh = { ...stored, ...me };
        store(fresh);
        setSession(fresh);
      } catch {
        /* 401 is handled by the unauthorized listener; other errors keep the stored session */
      }
    };
    void restore();
    const expired = () => drop(false);
    window.addEventListener(UNAUTHORIZED_EVENT, expired);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, expired);
  }, [drop]);

  const value = useMemo(
    () => ({ session, ready, epoch, signedOutByUser, signIn, signOut }),
    [session, ready, epoch, signedOutByUser, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
