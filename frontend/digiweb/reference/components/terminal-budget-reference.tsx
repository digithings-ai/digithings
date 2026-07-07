"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useInView, useReducedMotion } from "motion/react";

type Line = {
  text: string;
  kind: "prompt" | "comment" | "tool" | "output";
  module?: "digigraph" | "digiquant" | "digisearch" | "digikey";
};

const COMMAND = "digithings init";
const LINES: Line[] = [
  { text: "Detected workspace: digigraph · digiquant · digisearch · digikey", kind: "output" },
  { text: "// resolving MCP capabilities", kind: "comment" },
  { text: "[digigraph.route] ✓ routed to digiquant.backtest", kind: "tool", module: "digigraph" },
  { text: "[digiquant.backtest] ✓ 3 strategies loaded", kind: "tool", module: "digiquant" },
  { text: "[digisearch.index] ✓ corpus online", kind: "tool", module: "digisearch" },
  { text: "[digikey.exchange] ✓ scoped token issued", kind: "tool", module: "digikey" },
  { text: "> ready.", kind: "prompt" },
];

const MODULES = ["digigraph", "digiquant", "digisearch", "digikey"] as const;

// CLI line colours by kind — migrated from `.terminal-shell .line.<kind>`.
const LINE_COLOR: Record<Line["kind"], string> = {
  prompt: "text-ink",
  comment: "text-term-mute",
  tool: "text-ink-soft",
  output: "text-up",
};

/**
 * Terminal + budget sidebar — a diegetic `digithings init` CLI session that
 * types its command and reveals output rows in view, paired with an
 * illustrative context-budget sidebar that lights up each module as its line
 * lands. Explicitly labelled example data, not live; reduced motion renders the
 * finished session with no typing.
 */
export function TerminalBudgetReference() {
  const reduced = useReducedMotion();
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const inView = useInView(scopeRef, { amount: 0.35, once: true });

  const [charCount, setCharCount] = useState(COMMAND.length);
  const [visibleRows, setVisibleRows] = useState(LINES.length);

  useEffect(() => {
    if (!inView || reduced) return;

    let alive = true;
    let rowTimer = 0;
    let interval = 0;

    const start = window.setTimeout(() => {
      if (!alive) return;
      setCharCount(0);
      setVisibleRows(0);

      interval = window.setInterval(() => {
        if (!alive) return;
        setCharCount((n) => {
          if (n >= COMMAND.length) {
            window.clearInterval(interval);
            return COMMAND.length;
          }
          return n + 1;
        });
      }, 24);

      const kickoff = window.setTimeout(() => {
        rowTimer = window.setInterval(() => {
          setVisibleRows((n) => {
            if (n >= LINES.length) {
              window.clearInterval(rowTimer);
              return LINES.length;
            }
            return n + 1;
          });
        }, 210);
      }, COMMAND.length * 24 + 220);

      return () => window.clearTimeout(kickoff);
    }, 0);

    return () => {
      alive = false;
      window.clearTimeout(start);
      window.clearInterval(interval);
      window.clearInterval(rowTimer);
    };
  }, [inView, reduced]);

  const shown = LINES.slice(0, visibleRows);
  const contextUsed = useMemo(() => 2100 + visibleRows * 380, [visibleRows]);
  const lit = new Set(shown.filter((line) => line.module).map((line) => line.module));

  return (
    <section className="section-block" id="terminal-budget" ref={scopeRef}>
      <div className="section-head">
        <p className="kicker">{"// terminal + budget sidebar"}</p>
        <h2 className="title">Diegetic CLI session with explicit illustrative budget.</h2>
      </div>

      <div className="mt-[1.2rem] grid grid-cols-[minmax(0,1fr)_220px] gap-[1rem] max-[900px]:grid-cols-1">
        <article
          className="rounded-[12px] border border-hair bg-surface p-[1rem]"
          aria-label="Scripted digithings terminal"
        >
          <header className="flex justify-between font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-soft">
            <span>digithings session</span>
            <span className="muted">illustrative</span>
          </header>
          <pre className="mt-[0.7rem] max-w-full overflow-auto font-mono text-[0.78rem] leading-[1.95] text-term-ink">
            <code>
              <span className="block text-ink">
                <span className="text-accent">❯</span> {COMMAND.slice(0, charCount)}
              </span>
              {shown.map((line) => (
                <span key={line.text} className={`block ${LINE_COLOR[line.kind]}`}>
                  {line.text}
                </span>
              ))}
            </code>
          </pre>
        </article>

        <aside className="budget-shell" aria-label="Illustrative budget sidebar">
          <p className="badge">Example data · not live</p>
          <p className="budget-title">Context</p>
          <p className="budget-value">{(contextUsed / 1000).toFixed(1)}k / 32k tokens</p>
          <ul>
            {MODULES.map((module) => (
              <li key={module} className={lit.has(module) ? "on" : undefined}>
                {module}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </section>
  );
}
