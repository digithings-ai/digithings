"use client";

import { useEffect, useRef, useState } from "react";
// Stopgap: globals.css (Phase 0 owned) does not import this family yet. Remove once it does.
import "@digithings/ui/styles/terminal-manifest.css";
import { TerminalManifest, useMotionSafe, type TerminalManifestRow } from "@digithings/ui";

/** The MCP band's terminal listing. When the block scrolls into view the rows stack
 *  in and the first one opens. Server render, reduced motion and no
 *  IntersectionObserver show the final state with nothing hidden. */
export function McpManifest({ rows }: { rows: TerminalManifestRow[] }) {
  const safe = useMotionSafe();
  const ref = useRef<HTMLDivElement>(null);
  const [armed, setArmed] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!safe || !el || typeof IntersectionObserver === "undefined") {
      setArmed(false);
      setRunning(false);
      return;
    }
    setArmed(true);
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          io.disconnect();
          setArmed(false);
          setRunning(true);
        }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [safe]);

  const online = rows.filter((r) => r.status === "online").length;
  const roadmap = rows.filter((r) => r.status === "roadmap").length;

  return (
    <div ref={ref} className={`min-w-0 transition-opacity duration-300 ${armed ? "opacity-0" : "opacity-100"}`}>
      <TerminalManifest
        key={running ? "run" : "idle"}
        command="mcp"
        prompt="▸"
        meta={`· ${online} online · ${roadmap} on the roadmap`}
        hint="select a row for detail"
        animateRows={running}
        defaultSelectedId={running ? (rows[0]?.id ?? null) : null}
        rows={rows}
        aria-label="MCP tool groups, online and on the roadmap"
      />
    </div>
  );
}
