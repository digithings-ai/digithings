"use client";

import { useMemo, useState } from "react";

/**
 * Search bar — a search field with a leading glyph, a clear affordance that
 * appears once there's input, and results that resolve live as you type against
 * a small corpus. Focus lights the accent ring; an empty query shows nothing
 * rather than everything. Static interactive display template.
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

      <div className="ctl-search">
        <span className="inline-flex text-ink-mute" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
          </svg>
        </span>
        <input
          className="sb-input flex-1 border-none bg-transparent font-mono text-[0.82rem] text-ink outline-none placeholder:text-ink-mute"
          type="search"
          placeholder="Search strategies, metrics, modules…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search"
        />
        {q ? (
          <button
            type="button"
            className="cursor-pointer border-none bg-transparent px-[0.2rem] py-[0.1rem] text-[0.7rem] text-ink-mute hover:text-ink"
            aria-label="Clear search"
            onClick={() => setQ("")}
          >
            ✕
          </button>
        ) : (
          <kbd className="kbd sb-hint">/</kbd>
        )}
      </div>

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
