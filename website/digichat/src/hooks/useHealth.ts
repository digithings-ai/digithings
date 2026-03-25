import { useState, useEffect, useCallback } from "react";
import { HealthState } from "../types";

export function useHealth(digigraphUrl: string, enabled: boolean) {
  const [health, setHealth] = useState<HealthState>("unknown");

  const ping = useCallback(async () => {
    if (!enabled || !digigraphUrl) return;
    try {
      const r = await fetch(`${digigraphUrl}/health`, { cache: "no-store" });
      setHealth(r.ok ? "ok" : "err");
    } catch {
      setHealth("err");
    }
  }, [digigraphUrl, enabled]);

  useEffect(() => {
    if (!enabled) return;
    void ping();
    const id = setInterval(() => void ping(), 30_000);
    return () => clearInterval(id);
  }, [ping, enabled]);

  return { health, ping };
}
