"use client";

import { useMemo, useState } from "react";

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
  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return CORPUS.filter((c) => c.toLowerCase().includes(t)).slice(0, 5);
  }, [q]);

  return (
    <section className="section-block">
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
        <div
          className="mt-[0.5rem] w-[min(100%,26rem)] overflow-hidden rounded-[10px] border border-hair bg-surface"
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
      ) : null}
    </section>
  );
}
