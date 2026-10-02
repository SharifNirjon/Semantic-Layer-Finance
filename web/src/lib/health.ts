"use client";

import { useEffect, useState } from "react";
import { API_URL } from "./api";

export interface Health {
  llm_configured: boolean;
  llm: { provider: string; model: string } | null;
  llm_error?: string | null;
}

/** API /health: whether the language model is configured and which one answers. */
export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    fetch(`${API_URL}/health`)
      .then((r) => r.json())
      .then((h: Health) => live && setHealth(h))
      .catch((e) => live && setDown(e instanceof Error ? e.message : "API unreachable"));
    return () => {
      live = false;
    };
  }, []);
  return { health, down };
}
