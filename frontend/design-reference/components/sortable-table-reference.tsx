"use client";

import { useState } from "react";

/**
 * Sortable data table — a strategy leaderboard you can reorder by any column.
 * Click a header to sort (toggles asc/desc), the active column shows a caret and
 * carries aria-sort; numeric columns sort numerically, text lexically. Returns
 * wear the up colour, drawdown the down colour; everything else stays ink.
 */
type Row = { strat: string; cagr: number; pf: number; win: number; dd: number; sharpe: number };

const ROWS: Row[] = [
  { strat: "trend_xsec", cagr: 44.9, pf: 2.31, win: 58, dd: -18.4, sharpe: 1.87 },
  { strat: "carry", cagr: 31.2, pf: 3.02, win: 64, dd: -12.1, sharpe: 2.4 },
  { strat: "mean_rev", cagr: 38.5, pf: 2.58, win: 61, dd: -22.0, sharpe: 1.6 },
  { strat: "breakout", cagr: 52.1, pf: 1.94, win: 49, dd: -29.3, sharpe: 1.2 },
  { strat: "pairs", cagr: 18.4, pf: 1.71, win: 55, dd: -9.8, sharpe: 1.9 },
  { strat: "momentum", cagr: 41.0, pf: 2.1, win: 52, dd: -24.6, sharpe: 1.4 },
];

type Col = {
  key: keyof Row;
  label: string;
  num: boolean;
  fmt: (v: Row[keyof Row]) => string;
  tone?: "up" | "down";
};

const COLS: Col[] = [
  { key: "strat", label: "strategy", num: false, fmt: (v) => String(v) },
  { key: "cagr", label: "cagr", num: true, fmt: (v) => `+${(v as number).toFixed(1)}%`, tone: "up" },
  { key: "pf", label: "pf", num: true, fmt: (v) => (v as number).toFixed(2) },
  { key: "win", label: "win", num: true, fmt: (v) => `${v}%` },
  { key: "dd", label: "max dd", num: true, fmt: (v) => `${(v as number).toFixed(1)}%`, tone: "down" },
  { key: "sharpe", label: "sharpe", num: true, fmt: (v) => (v as number).toFixed(2) },
];

export function SortableTableReference() {
  const [sortKey, setSortKey] = useState<keyof Row>("pf");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const sorted = [...ROWS].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
    return dir === "asc" ? cmp : -cmp;
  });

  const onSort = (key: keyof Row) => {
    if (key === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDir(key === "strat" ? "asc" : "desc");
    }
  };

  return (
    <section className="section-block" id="sortable-table">
      <p className="kicker">{"// sortable table"}</p>
      <h2 className="title">Rank by any column.</h2>
      <p className="section-copy">
        A strategy leaderboard you can reorder — click a header to sort, click again to flip. The
        active column shows a caret and reports <code>aria-sort</code>; numbers sort numerically,
        text lexically. Returns wear the up color, drawdown the down.
      </p>

      <div className="srt-scroll">
        <table className="srt-table">
          <thead>
            <tr>
              {COLS.map((c) => {
                const active = c.key === sortKey;
                return (
                  <th
                    key={c.key}
                    className={c.num ? "srt-r" : "srt-l"}
                    aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button type="button" className={`srt-head${active ? " is-active" : ""}`} onClick={() => onSort(c.key)}>
                      {c.label}
                      <span className="srt-caret" aria-hidden="true">
                        {active ? (dir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.strat}>
                {COLS.map((c) => (
                  <td key={c.key} className={`${c.num ? "srt-r" : "srt-l"}${c.tone ? ` ${c.tone}` : ""}${c.key === "strat" ? " srt-sym" : ""}`}>
                    {c.fmt(row[c.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
