"use client";

import { useMemo, useState } from "react";

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
        <span className="sb-glyph" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
          </svg>
        </span>
        <input
          className="sb-input"
          type="search"
          placeholder="Search strategies, metrics, modules…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search"
        />
        {q ? (
          <button type="button" className="sb-clear" aria-label="Clear search" onClick={() => setQ("")}>
            ✕
          </button>
        ) : (
          <kbd className="kbd sb-hint">/</kbd>
        )}
      </div>

      {q.trim() ? (
        <div className="sb-results" role="listbox" aria-label="Results">
          {results.length ? (
            results.map((r) => {
              const [head, tail] = r.split(" — ");
              return (
                <div key={r} className="sb-result" role="option" aria-selected="false">
                  <span className="sb-result-head">{head}</span>
                  {tail ? <span className="sb-result-tail">{tail}</span> : null}
                </div>
              );
            })
          ) : (
            <p className="sb-empty">No matches for “{q}”.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
