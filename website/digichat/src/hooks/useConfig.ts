import { useState, useEffect } from "react";
import { Config, CONFIG_DEFAULTS } from "../types";

function stripMeta(obj: Record<string, unknown>): Partial<Config> {
  const o = { ...obj };
  delete o.$schema;
  return o as Partial<Config>;
}

async function tryFetch(path: string): Promise<Record<string, unknown>> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(String(r.status));
  return r.json() as Promise<Record<string, unknown>>;
}

export function useConfig() {
  const [config, setConfig] = useState<Config>({ ...CONFIG_DEFAULTS });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function load() {
      let loaded: Partial<Config> = {};
      try {
        const data = await tryFetch("config.json");
        loaded = stripMeta(data);
      } catch {
        try {
          const data = await tryFetch("config.example.json");
          loaded = stripMeta(data);
        } catch {
          /* use defaults */
        }
      }

      const merged: Config = { ...CONFIG_DEFAULTS, ...loaded };

      // Apply ?digigraphUrl= query-param override (single canonical key)
      const params = new URLSearchParams(window.location.search);
      const override = params.get("digigraphUrl");
      if (override) merged.digigraphUrl = override.replace(/\/$/, "");

      // Normalise trailing slash
      merged.digigraphUrl = merged.digigraphUrl.replace(/\/$/, "");

      setConfig(merged);
      setReady(true);

      // Update page title
      document.title = `${merged.title || "Digichat"} · digithings`;
    }

    void load();
  }, []);

  return { config, ready };
}
