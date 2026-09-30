"use client";

import { useEffect, useRef, useState } from "react";
// Stopgap: globals.css (Phase 0 owned) does not import this family yet. Remove once it does.
import "@digithings/ui/styles/terminal-manifest.css";
import { TerminalManifest, useMotionSafe, type TerminalManifestRow } from "@digithings/ui";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@digithings/ui/ui";
import type { IntegrationRow, IntegrationStatus } from "@/app/_products";

/** The band's signature moment. When the block scrolls into view, the manifest rows
 *  stack in and the ledger is scanned top to bottom: each row's badge reads `[..]`
 *  while the marker is on it, then flips to its status.
 *
 *  Modes: `static` is the server render, reduced motion and no IntersectionObserver
 *  (everything final, no hidden state). `armed` waits for the block to be seen.
 *  `running` plays once. The timer fires once per row, never per frame, and only
 *  opacity is animated. */
type Mode = "static" | "armed" | "running";
type Phase = "done" | "scan" | "hidden";

const STEP_MS = 380;

const VARIANT: Record<IntegrationStatus, "accent" | "neutral"> = {
  live: "accent",
  integrated: "neutral",
  "built on": "neutral",
  "local only": "neutral",
  "in development": "neutral",
};

export function ProductsScan({
  manifest,
  integrations,
}: {
  manifest: TerminalManifestRow[];
  integrations: IntegrationRow[];
}) {
  const safe = useMotionSafe();
  const ref = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<Mode>("static");
  const [step, setStep] = useState(0);

  // Arm or disarm the scan once the client knows the motion preference and IntersectionObserver.
  useEffect(() => {
    const el = ref.current;
    if (!safe || !el || typeof IntersectionObserver === "undefined") {
      setMode("static");
      return;
    }
    setStep(0);
    setMode("armed");
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          io.disconnect();
          setMode("running");
        }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [safe]);

  useEffect(() => {
    if (mode !== "running" || step >= integrations.length) return;
    const t = window.setTimeout(() => setStep((s) => s + 1), step === 0 ? 650 : STEP_MS);
    return () => window.clearTimeout(t);
  }, [mode, step, integrations.length]);

  const phase = (i: number): Phase => {
    if (mode === "static") return "done";
    if (mode === "armed") return "hidden";
    return i < step ? "done" : i === step ? "scan" : "hidden";
  };

  return (
    <div ref={ref} className="flex min-w-0 flex-col gap-[1.5rem]">
      <div className={`transition-opacity duration-300 ${mode === "armed" ? "opacity-0" : "opacity-100"}`}>
        <TerminalManifest
          key={mode === "running" ? "run" : "idle"}
          command="products"
          prompt="▸"
          meta={`· ${manifest.filter((r) => r.status === "online").length} online · ${manifest.filter((r) => r.status === "roadmap").length} on the roadmap`}
          hint="select a row for detail"
          animateRows={mode === "running"}
          defaultSelectedId={mode === "running" ? (manifest[0]?.id ?? null) : null}
          rows={manifest}
          aria-label="Products, online and on the roadmap"
        />
      </div>

      <div className="border border-hair font-mono">
        <div className="flex items-center justify-between gap-3 border-b border-hair px-[0.75rem] py-[0.5rem] text-[0.68rem] text-ink-mute">
          <span>[integrations] text only</span>
          <span aria-hidden="true">{mode === "running" && step < integrations.length ? "scanning" : " "}</span>
        </div>
        <Table density="compact" className="text-[0.78rem] text-ink-soft">
          <TableHeader className="max-sm:hidden">
            <TableRow className="border-hair hover:bg-transparent">
              <TableHead className="w-[1.25rem] px-0" aria-hidden="true" />
              <TableHead className="w-[9rem] text-[0.68rem] font-normal text-ink-mute">name</TableHead>
              <TableHead className="w-[8.5rem] text-[0.68rem] font-normal text-ink-mute">status</TableHead>
              <TableHead className="text-[0.68rem] font-normal text-ink-mute">what / where</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {integrations.map((row, i) => {
              const p = phase(i);
              return (
                <TableRow
                  key={row.id}
                  className={`border-hair transition-opacity duration-300 hover:bg-surface-2 max-sm:grid max-sm:grid-cols-[minmax(0,1fr)_auto] max-sm:gap-x-3 ${
                    p === "hidden" ? "opacity-0" : "opacity-100"
                  } ${p === "scan" ? "bg-surface-2" : ""}`}
                >
                  <TableCell aria-hidden="true" className="w-[1.25rem] px-0 ps-[0.5rem] text-accent max-sm:hidden">
                    {p === "scan" ? "▸" : ""}
                  </TableCell>
                  <TableCell className="text-[0.82rem] text-ink max-sm:py-[0.4rem]">{row.name}</TableCell>
                  <TableCell className="max-sm:order-last max-sm:py-[0.4rem] max-sm:text-end">
                    <span className="sr-only">{row.status}</span>
                    <Badge
                      aria-hidden="true"
                      variant={p === "scan" ? "neutral" : VARIANT[row.status]}
                      className={`min-w-[7.25rem] font-mono text-[0.68rem] ${
                        row.status === "in development" && p === "done" ? "border-dashed" : ""
                      }`}
                    >
                      {p === "done" ? `[${row.status}]` : "[..]"}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-normal pe-[0.75rem] leading-[1.5] max-sm:col-span-2 max-sm:pt-0 max-sm:pb-[0.6rem]">
                    {row.what}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <p className="m-0 border-t border-hair px-[0.75rem] py-[0.5rem] text-[0.68rem] text-ink-mute">
          Product names belong to their owners. Listing one here implies no affiliation.
        </p>
      </div>
    </div>
  );
}
