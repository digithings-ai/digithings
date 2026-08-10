"use client";

import { useState } from "react";

/**
 * SortableTable — the reorderable leaderboard promoted from the design
 * reference (data/sortable-table): click (or keyboard-activate — real
 * <button>s in the headers) a column to sort, click again to flip. The active
 * column shows a caret and reports `aria-sort` on its <th>; numeric columns
 * sort numerically and right-align, text sorts lexically. Column `tone`
 * wears the money colors (--up / --down) — returns up, drawdowns down —
 * and everything else stays ink.
 *
 * The table grammar (srt-*) lives in styles/finance-composites.css: header
 * hover/active state, caret accent, hairline row rules, td money colors —
 * descendant/state selectors that stay CSS per migrate-vs-leave. Rows render
 * fully server-side markup-wise; without JS you get the table in its default
 * order.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/finance-composites.css";
 *                 @source "<path-to>/digiweb/web/src/components/finance-composites";
 */
export type SortableColumn<Row> = {
  /** Row field this column reads (and sorts by). */
  key: keyof Row & string;
  /** Mono micro-caps header label. */
  label: string;
  /** Numeric columns right-align and default to descending on first sort. */
  numeric?: boolean;
  /** Preformats the cell read; defaults to String(value). */
  format?: (value: Row[keyof Row & string], row: Row) => string;
  /** Money semantics for the whole column: returns "up", drawdowns "down". */
  tone?: "up" | "down";
  /** Identifier column emphasis — the read stays ink instead of ink-soft. */
  emphasis?: boolean;
};

export type SortableTableProps<Row> = {
  rows: Row[];
  columns: SortableColumn<Row>[];
  /** Stable React key per row — e.g. `(r) => r.strat`. */
  rowKey: (row: Row) => string;
  /** Initial sort; defaults to the first column in its natural direction. */
  defaultSort?: { key: keyof Row & string; dir?: "asc" | "desc" };
  /** Extra classes on the scroll shell (margins — the call site's business). */
  className?: string;
};

export function SortableTable<Row>({
  rows,
  columns,
  rowKey,
  defaultSort,
  className,
}: SortableTableProps<Row>) {
  const naturalDir = (key: keyof Row & string): "asc" | "desc" =>
    columns.find((c) => c.key === key)?.numeric ? "desc" : "asc";

  const initialKey = defaultSort?.key ?? columns[0]?.key;
  const [sortKey, setSortKey] = useState<keyof Row & string>(initialKey);
  const [dir, setDir] = useState<"asc" | "desc">(
    defaultSort?.dir ?? (initialKey ? naturalDir(initialKey) : "asc"),
  );

  const sorted = [...rows].sort((a, b) => {
    const av = a[sortKey];
    const bv = b[sortKey];
    const cmp =
      typeof av === "number" && typeof bv === "number"
        ? av - bv
        : String(av).localeCompare(String(bv));
    return dir === "asc" ? cmp : -cmp;
  });

  const onSort = (key: keyof Row & string) => {
    if (key === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDir(naturalDir(key));
    }
  };

  return (
    <div
      className={`overflow-x-auto rounded-[12px] border border-hair bg-surface${
        className ? ` ${className}` : ""
      }`}
    >
      <table className="srt-table">
        <thead>
          <tr>
            {columns.map((c) => {
              const active = c.key === sortKey;
              return (
                <th
                  key={c.key}
                  className={c.numeric ? "srt-r" : "srt-l"}
                  aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <button
                    type="button"
                    className={`srt-head${active ? " is-active" : ""}`}
                    onClick={() => onSort(c.key)}
                  >
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
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`${c.numeric ? "srt-r" : "srt-l"}${c.tone ? ` ${c.tone}` : ""}${
                    c.emphasis ? " srt-sym" : ""
                  }`}
                >
                  {c.format ? c.format(row[c.key], row) : String(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
