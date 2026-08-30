"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { SearchBar } from "@digithings/web";

/**
 * Search bar — a search field with a leading glyph, a clear affordance that
 * appears once there's input, and results that resolve live as you type against
 * a small corpus. Focus lights the accent ring; an empty query shows nothing
 * rather than everything. Static interactive display template. Consumes the
 * shared <SearchBar/> primitive from @digithings/web — the `/` keycap rides
 * its hint slot; the results pane stays specimen-side.
 */
const CORPUS = [
  "trend_xsec — cross-sectional momentum",
  "mean_rev — intraday mean reversion",
  "kelly sizing — position cap",
  "Sharpe ratio — risk-adjusted return",
  "maxDD — maximum drawdown",
  "atlas — research scheduler",
  "hermes — signal messenger",
  "tearsheet — re-runnable receipt",
];

export function SearchBarReference() {
  const [q, setQ] = useState("");
  const sectionRef = useRef<HTMLElement | null>(null);
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return CORPUS.filter((c) => c.toLowerCase().includes(t)).slice(0, 5);
  }, [q]);

  // The `/` keycap hint (SearchBar's own hint slot) promised a "press / to
  // focus search" shortcut that nothing actually bound. Scoped to this
  // component (not a global site-nav listener) since this is the only
  // SearchBar instance on the reference site; guarded against firing while
  // any other field already has focus so it doesn't hijack normal typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/") return;
      const active = document.activeElement;
      const isTyping =
        active instanceof HTMLElement &&
        (active.tagName === "INPUT" ||
          active.tagName === "TEXTAREA" ||
          active.tagName === "SELECT" ||
          active.isContentEditable);
      if (isTyping) return;
      e.preventDefault();
      sectionRef.current?.querySelector<HTMLInputElement>(".sb-input")?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <section className="section-block" ref={sectionRef}>
      <p className="kicker">{"// search"}</p>
      <h2 className="title">Search, with live results.</h2>
      <p className="section-copy">
        A search field with a leading glyph, a clear affordance that appears once there&apos;s
        input, and results that resolve as you type. Focus lights the accent ring; empty query
        shows nothing rather than everything.
      </p>

      <SearchBar
        className="mt-[1.2rem]"
        value={q}
        onChange={setQ}
        placeholder="Search strategies, metrics, modules…"
        hint={<kbd className="kbd sb-hint">/</kbd>}
      />

      {q.trim() ? (
        <>
          {/* Announces the count only — not the whole listbox — so a screen
              reader isn't re-read every option on each keystroke, just how
              many results just changed. */}
          <p className="sr-only" aria-live="polite">
            {results.length ? `${results.length} result${results.length === 1 ? "" : "s"}` : "No results"}
          </p>
          <div
            className="mt-[0.5rem] w-[min(100%,26rem)] overflow-hidden rounded-none border border-hair bg-surface"
            role="listbox"
            aria-label="Results"
          >
            {results.length ? (
              results.map((r) => {
                const [head, tail] = r.split(" — ");
                return (
                  <div
                    key={r}
                    className="flex items-baseline gap-[0.6rem] border-b border-hair/55 px-[0.8rem] py-[0.5rem] font-mono last:border-b-0"
                    role="option"
                    aria-selected="false"
                  >
                    <span className="text-[0.8rem] text-ink">{head}</span>
                    {tail ? <span className="text-[0.66rem] text-ink-mute">{tail}</span> : null}
                  </div>
                );
              })
            ) : (
              <p className="p-[0.8rem] font-mono text-[0.76rem] text-ink-mute">No matches for “{q}”.</p>
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}
