"use client";

import { useEffect, useState } from "react";
import { p } from "@/lib/base-path";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { DevkitPreview } from "./devkit-preview";

/** Wire shape of GET /api/devkit/configs (mirrors DevkitEntry, JSON-safe). */
interface DevkitEntryWire {
  id: string;
  kind: "file" | "env";
  path: string;
  label: string;
  readOnly: boolean;
  ok: boolean;
  redactedText: string | null;
  issues: string[];
  deployment: DigichatDeployment | null;
}

/**
 * P0 devkit shell: deployments menu + read-only redacted YAML view.
 * No editing yet (P1) — this slice proves listing, redaction, and display.
 */
export function DevkitClient() {
  const [entries, setEntries] = useState<DevkitEntryWire[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(p("/api/devkit/configs"))
      .then((res) => {
        if (!res.ok) throw new Error(`configs ${res.status}`);
        return res.json() as Promise<{ entries: DevkitEntryWire[] }>;
      })
      .then((data) => {
        if (!cancelled) setEntries(data.entries);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = entries?.find((e) => e.id === selectedId) ?? null;

  return (
    <main className="mx-auto flex h-full max-w-7xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-xl font-semibold">digichat devkit</h1>
        <p className="text-sm text-muted-foreground">
          Local deployment configs — read-only in P0. Secrets are redacted server-side.
        </p>
      </header>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          Failed to load configs: {error}
        </p>
      ) : entries === null ? (
        <p className="text-sm text-muted-foreground">Loading configs…</p>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
          <nav aria-label="Deployments" className="overflow-y-auto rounded-lg border p-2">
            <ul className="flex flex-col gap-1">
              {entries.map((entry) => (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(entry.id)}
                    aria-current={entry.id === selectedId}
                    className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm ${
                      entry.id === selectedId ? "bg-accent" : "hover:bg-accent/50"
                    }`}
                  >
                    <span
                      aria-label={entry.ok ? "valid" : "invalid"}
                      title={entry.ok ? "valid" : "invalid"}
                      className={`inline-block size-2 shrink-0 rounded-full ${
                        entry.ok ? "bg-green-500" : "bg-destructive"
                      }`}
                    />
                    <span className="min-w-0 flex-1 truncate font-mono text-xs">{entry.id}</span>
                    {entry.readOnly ? (
                      <span className="shrink-0 rounded border px-1 text-[10px] text-muted-foreground">
                        read-only
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <section aria-label="Config detail" className="flex min-h-0 flex-col gap-2">
            {selected === null ? (
              <p className="text-sm text-muted-foreground">Select a deployment to inspect it.</p>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-mono text-sm font-semibold">{selected.id}</h2>
                  {selected.readOnly ? (
                    <span className="rounded border px-1 text-[10px] text-muted-foreground">
                      read-only env tenant — never written
                    </span>
                  ) : null}
                </div>
                {selected.issues.length > 0 ? (
                  <ul className="rounded-lg border border-destructive/50 p-2 font-mono text-xs">
                    {selected.issues.map((issue) => (
                      <li key={issue} className="text-destructive">
                        {issue}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {selected.redactedText === null && selected.deployment === null ? (
                  <p className="text-sm text-muted-foreground">
                    No file text for env tenants — configuration lives in the environment.
                  </p>
                ) : (
                  <>
                    {selected.redactedText !== null ? (
                      <pre
                        className={`overflow-auto rounded-lg border bg-muted/30 p-3 font-mono text-xs ${
                          selected.deployment ? "max-h-72 shrink-0" : "min-h-0 flex-1"
                        }`}
                      >
                        {selected.redactedText}
                      </pre>
                    ) : null}
                    {selected.deployment ? (
                      <div className="min-h-[480px] flex-1 overflow-hidden rounded-lg border">
                        <DevkitPreview
                          key={selected.id}
                          entryId={selected.id}
                          deployment={selected.deployment}
                        />
                      </div>
                    ) : null}
                  </>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
