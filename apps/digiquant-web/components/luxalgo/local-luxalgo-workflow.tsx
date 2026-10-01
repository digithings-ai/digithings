"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { CtaLink } from "@digithings/ui";
import { Badge, Button, Input } from "@digithings/ui/ui";
import {
  fetchHealthz,
  fetchLuxalgoSearch,
  resolveGatewayState,
} from "@/lib/gateway/gateway-client";

type BridgeStatus = "checking" | "ready" | "unset" | "blocked" | "offline";

type SearchRow = {
  kind: string | null;
  name: string;
  family: string | null;
};

function searchRows(data: unknown): SearchRow[] {
  if (!data || typeof data !== "object" || !("results" in data)) return [];
  const results = (data as { results?: unknown }).results;
  if (!Array.isArray(results)) return [];
  return results.flatMap((value): SearchRow[] => {
    if (!value || typeof value !== "object") return [];
    const row = value as Record<string, unknown>;
    if (typeof row.name !== "string") return [];
    return [{
      kind: typeof row.kind === "string" ? row.kind : null,
      name: row.name,
      family: typeof row.family === "string" ? row.family : null,
    }];
  });
}

const STATUS_COPY: Record<BridgeStatus, string> = {
  checking: "Local wire checks after hydration",
  ready: "Local gateway connected",
  unset: "Local wire off · env not set",
  blocked: "Local wire blocked · loopback only",
  offline: "Local gateway offline",
};

export function LocalLuxalgoWorkflow() {
  const mounted = useRef(false);
  const [status, setStatus] = useState<BridgeStatus>("checking");
  const [query, setQuery] = useState("risk management");
  const [rows, setRows] = useState<SearchRow[]>([]);
  const [attribution, setAttribution] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState("Research metadata only · no source code or signals");

  useEffect(() => {
    mounted.current = true;
    void (async () => {
      const state = resolveGatewayState();
      if (!state.available) {
        if (mounted.current) setStatus(state.reason === "unset" ? "unset" : "blocked");
        return;
      }
      const result = await fetchHealthz();
      if (mounted.current) setStatus(result.ok ? "ready" : "offline");
    })();
    return () => {
      mounted.current = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || status !== "ready") return;
    setSearching(true);
    setMessage("Searching the local read-only bridge…");
    const result = await fetchLuxalgoSearch(trimmed, 4);
    if (!mounted.current) return;
    setSearching(false);
    if (!result.ok) {
      setRows([]);
      setAttribution([]);
      setMessage(`Search unavailable · ${result.error}`);
      return;
    }
    const nextRows = searchRows(result.envelope.data);
    setRows(nextRows);
    setAttribution(result.envelope.attribution);
    setMessage(
      nextRows.length > 0
        ? `${nextRows.length} Library reference${nextRows.length === 1 ? "" : "s"}`
        : result.envelope.empty ?? "No Library references matched",
    );
  }

  return (
    <section aria-labelledby="luxalgo-workflow-h" className="border border-hair">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-3 py-2 font-mono">
        <h3 id="luxalgo-workflow-h" className="m-0 text-[0.78rem] font-normal text-ink">
          LuxAlgo, as a demo
        </h3>
        <Badge variant={status === "ready" ? "accent" : "neutral"}>{STATUS_COPY[status]}</Badge>
      </div>

      <div className="grid gap-x-6 gap-y-3 p-3 min-[900px]:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <p className="m-0 text-[0.8125rem] leading-[1.55] text-ink-soft">
            Charts and the trade journal stay in LuxAlgo; this site renders no competing chart. The local gateway looks up
            Library concepts and indicator metadata, and an idea goes to digiquant for a Nautilus backtest before anything
            is exported.
          </p>
          <p className="m-0 mt-2 font-mono text-[0.65rem] text-ink-mute">
            A demo of what the gateway can reach, not a search tool. The product is the dashboard.
          </p>
        </div>
        <div className="min-w-0">
          <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
            <label htmlFor="luxalgo-library-query" className="sr-only">Search LuxAlgo Library</label>
            <Input
              id="luxalgo-library-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={60}
              pattern={"[A-Za-z0-9 .,&'_-]{1,60}"}
              aria-describedby="luxalgo-search-status"
              placeholder="Search LuxAlgo Library"
              disabled={status !== "ready" || searching}
            />
            <Button type="submit" variant="outline" disabled={status !== "ready" || searching || !query.trim()}>
              {searching ? "Searching…" : "Search LuxAlgo Library"}
            </Button>
            <CtaLink href="https://www.luxalgo.com/" external variant="ghost">
              Continue in LuxAlgo ↗
            </CtaLink>
          </form>

          <p id="luxalgo-search-status" aria-live="polite" className="mb-0 mt-2 font-mono text-[0.65rem] text-ink-mute">
            {message}
          </p>

          {rows.length > 0 ? (
            <ul className="mb-0 mt-3 grid list-none gap-px border border-hair bg-border p-0 sm:grid-cols-2">
              {rows.map((row) => (
                <li key={`${row.kind ?? "reference"}:${row.name}`} className="bg-bg px-3 py-2">
                  <span className="block text-[0.78rem] text-ink">{row.name}</span>
                  <span className="font-mono text-[0.62rem] text-ink-mute">
                    {[row.kind, row.family].filter(Boolean).join(" · ") || "Library reference"}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}

          {attribution.length > 0 ? (
            <p className="mb-0 mt-2 text-[0.62rem] text-ink-mute">{attribution.join(" · ")}</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
