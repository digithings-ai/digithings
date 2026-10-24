"use client";

import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "../../lib/utils";

/** How a desk column behaves when the table is narrower than its rows.
 *  `key` is the row label, pinned left while the rest scrolls.
 *  `num` is a number or a date: never wrapped, right-aligned, tabular figures.
 *  `text` is prose: the column that gives up width and wraps on word breaks. */
export type ColumnRole = "key" | "num" | "text";

const EMPTY_CELL = new Set(["", "—", "–", "-", "n/a", "N/A"]);
const NUMBER_CELL = /^[+\-−]?[$€£¥]?\d[\d,]*(\.\d+)?\s?(%|bp|bps|x|k|m|bn|[A-Z]{3})?$/i;
const DATE_CELL = /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?Z?)?$/;

const isNumeric = (cell: string): boolean => NUMBER_CELL.test(cell) || DATE_CELL.test(cell);

/** One role per column. A column is `num` only when every filled cell reads as
 *  a number or a date; the first column of a multi-column table is the row label. */
export function columnRoles(columns: string[], rows: string[][]): ColumnRole[] {
  const width = Math.max(columns.length, ...rows.map((row) => row.length), 0);
  const roles: ColumnRole[] = [];
  for (let col = 0; col < width; col += 1) {
    if (col === 0 && width > 1) {
      roles.push("key");
      continue;
    }
    const filled = rows
      .map((row) => (row[col] ?? "").trim())
      .filter((cell) => !EMPTY_CELL.has(cell));
    roles.push(filled.length > 0 && filled.every(isNumeric) ? "num" : "text");
  }
  return roles;
}

export type DataTableTone = "pos" | "neg";
export type DataTableRowVariant = "grp" | "total" | "sel";
type Direction = "asc" | "desc";

export type DataTableColumn<Row> = {
  key: string;
  label: string;
  /** Desk column role. `role="num"` and `num: true` are the same thing. */
  role?: ColumnRole;
  /** Numeric column — right-aligned, tabular figures. Shorthand for `role="num"`. */
  num?: boolean;
  /** Long text: wraps within the column and clamps instead of widening the table. */
  wrap?: boolean;
  /** Inline weight bar under the figure, 0–100. */
  bar?: (row: Row) => number | null;
  cell: (row: Row) => ReactNode;
  /** Money semantics for this cell — `--up` / `--down`, never a livery. */
  tone?: (row: Row) => DataTableTone | undefined;
  /** Sortable column. `true` sorts by the cell text/number; a function gives
   *  the sort value (null sorts last). */
  sort?: boolean | ((row: Row) => string | number | null | undefined);
  /** Plain text for the filter box; defaults to the sort value or a string/number cell. */
  text?: (row: Row) => string;
};

export type DataTableProps<Row> = {
  rows: Row[];
  cols: DataTableColumn<Row>[];
  rowKey: (row: Row, index: number) => string;
  variant?: (row: Row) => DataTableRowVariant | undefined;
  /** Shown when there are no rows at all. */
  empty?: string;
  /** Shown when a filter matches nothing. */
  noMatch?: string;
  /** Show a text filter box (matches any column's text). */
  filter?: boolean;
  /** Accessible name for the scroll region and the filter box. */
  label?: string;
  /** Row click / Enter / Space. Rows become keyboard-focusable. */
  onRowClick?: (row: Row, index: number) => void;
  /** Pin the first column while scrolling horizontally. */
  stickyFirst?: boolean;
  /** Rows per page; omit for no pagination. */
  pageSize?: number;
  className?: string;
};

const roleOf = <Row,>(column: DataTableColumn<Row>): ColumnRole =>
  column.role ?? (column.num ? "num" : "text");

const primitive = (value: ReactNode): string | number | null =>
  typeof value === "string" || typeof value === "number" ? value : null;

const sortValue = <Row,>(column: DataTableColumn<Row>, row: Row): string | number | null => {
  const value = typeof column.sort === "function" ? column.sort(row) : primitive(column.cell(row));
  return typeof value === "number" && !Number.isFinite(value) ? null : (value ?? null);
};

/** Nulls sort last in both directions, so a missing figure never heads the table. */
const compare = (a: string | number | null, b: string | number | null, dir: Direction): number => {
  if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
  const delta =
    typeof a === "number" && typeof b === "number"
      ? a - b
      : String(a).localeCompare(String(b), undefined, { numeric: true });
  return dir === "asc" ? delta : -delta;
};

/** A `<button>` does not inherit the page face, so the header voice is restated. */
const SORT_BUTTON =
  "inline-flex w-full cursor-pointer items-center gap-1 bg-transparent p-0 text-left " +
  "font-mono text-[0.64rem] tracking-[0.08em] hover:text-ink " +
  "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent";

const CONTROL =
  "cursor-pointer border border-hair px-2 py-0.5 font-mono text-[0.72rem] text-ink " +
  "disabled:cursor-not-allowed disabled:text-ink-mute " +
  "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent";

/**
 * DataTable — hairline rows, mono right-aligned figures, sticky header.
 * Every extra is opt-in: sortable columns, text filter, row click, sticky first
 * column, pagination. With none of them it renders the bare table.
 *
 * The sort is a real button per header (keyboard-native) and reports `aria-sort`
 * on its `<th>`; `tone` wears the money colours; `variant` marks group and total
 * rows, which stay pinned below the sorted body.
 */
export function DataTable<Row>({
  rows,
  cols,
  rowKey,
  variant,
  empty = "no rows",
  noMatch = "no match",
  filter,
  label,
  onRowClick,
  stickyFirst,
  pageSize,
  className,
}: DataTableProps<Row>) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: string; dir: Direction } | null>(null);
  const [page, setPage] = useState(0);
  const safe = Array.isArray(rows) ? rows : [];

  const view = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let out = safe.map((row, index) => ({ row, index }));
    if (needle) {
      out = out.filter(({ row }) =>
        cols.some((column) => {
          const text = column.text ? column.text(row) : sortValue(column, row);
          return text != null && String(text).toLowerCase().includes(needle);
        }),
      );
    }
    const column = sort && cols.find((c) => c.key === sort.key);
    if (column && sort) {
      // Total rows stay pinned at the end; everything else sorts.
      const tail = out.filter(({ row }) => variant?.(row) === "total");
      const body = out.filter(({ row }) => variant?.(row) !== "total");
      body.sort(
        (a, b) =>
          compare(sortValue(column, a.row), sortValue(column, b.row), sort.dir) ||
          a.index - b.index,
      );
      out = [...body, ...tail];
    }
    return out;
  }, [safe, cols, query, sort, variant]);

  if (!safe.length) return <p className="py-2 font-mono text-[0.72rem] text-ink-mute">{empty}</p>;

  const pages = pageSize ? Math.max(1, Math.ceil(view.length / pageSize)) : 1;
  const current = Math.min(page, pages - 1);
  const shown = pageSize ? view.slice(current * pageSize, (current + 1) * pageSize) : view;

  const toggle = (key: string) => {
    setPage(0);
    setSort((active) =>
      !active || active.key !== key
        ? { key, dir: "asc" }
        : active.dir === "asc"
          ? { key, dir: "desc" }
          : null,
    );
  };

  const onKey = (event: KeyboardEvent, row: Row, index: number) => {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick?.(row, index);
    }
  };

  const table = (
    <div
      // A horizontally-scrolling region has no keyboard route on its own: without
      // a tab stop a keyboard user cannot arrow-scroll the clipped columns.
      tabIndex={0}
      role="region"
      aria-label={label ? `${label} table` : "Table, scrollable horizontally"}
      className={cn(
        "overflow-x-auto rounded-none border border-hair bg-surface text-ink",
        "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent",
        className,
      )}
    >
      <table className="w-full border-collapse text-[0.8125rem]">
        <thead>
          <tr>
            {cols.map((column, position) => {
              const role = roleOf(column);
              const active = sort?.key === column.key ? sort.dir : null;
              return (
                <th
                  key={column.key}
                  scope="col"
                  data-col={role}
                  aria-sort={
                    active
                      ? active === "asc"
                        ? "ascending"
                        : "descending"
                      : column.sort
                        ? "none"
                        : undefined
                  }
                  className={cn(
                    "sticky top-0 z-[2] border-b border-hair-2 bg-surface px-3 py-2 align-bottom",
                    "font-normal tracking-[0.08em] text-ink-mute uppercase text-[0.64rem]",
                    role === "num" ? "text-right" : "text-left",
                    stickyFirst && position === 0 && "left-0 z-[3]",
                  )}
                >
                  {column.sort ? (
                    <button
                      type="button"
                      className={cn(SORT_BUTTON, role === "num" && "justify-end")}
                      onClick={() => toggle(column.key)}
                    >
                      {column.label}
                      <span aria-hidden="true">
                        {active === "asc" ? "▲" : active === "desc" ? "▼" : ""}
                      </span>
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {shown.map(({ row, index }) => {
            const state = variant?.(row);
            return (
              <tr
                key={rowKey(row, index)}
                className={cn(
                  "border-b border-hair last:border-b-0",
                  state === "total" && "border-t border-hair-2 font-semibold",
                  state === "grp" && "text-[0.72rem] tracking-[0.08em] text-ink-mute uppercase",
                  state === "sel" && "bg-surface-2",
                  onRowClick &&
                    "cursor-pointer hover:bg-surface-2 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-[-2px] focus-visible:outline-accent",
                )}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={onRowClick ? () => onRowClick(row, index) : undefined}
                onKeyDown={onRowClick ? (event) => onKey(event, row, index) : undefined}
              >
                {cols.map((column, position) => {
                  const role = roleOf(column);
                  const bar = column.bar?.(row);
                  const filled = bar != null && Number.isFinite(bar);
                  return (
                    <td
                      key={column.key}
                      data-col={role}
                      className={cn(
                        "px-3 py-1.5 align-baseline",
                        role === "num" &&
                          "whitespace-nowrap text-right [font-variant-numeric:tabular-nums]",
                        role === "key" && "text-ink",
                        role === "text" && "text-ink-soft",
                        column.wrap ? "max-w-[28rem]" : role === "text" && "whitespace-nowrap",
                        column.tone?.(row) === "pos" && "text-up",
                        column.tone?.(row) === "neg" && "text-down",
                        stickyFirst && position === 0 && "sticky left-0 z-[1] bg-surface",
                      )}
                    >
                      {column.wrap ? (
                        <span className="line-clamp-3 break-words">{column.cell(row)}</span>
                      ) : (
                        column.cell(row)
                      )}
                      {filled ? (
                        <span className="mt-1 block h-[2px] w-full bg-hair-2" aria-hidden="true">
                          <i
                            className="block h-full bg-accent"
                            style={{ width: `${Math.max(0, Math.min(100, bar))}%` }}
                          />
                        </span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  if (!filter && !pageSize) return table;

  return (
    <div className="flex flex-col">
      {filter ? (
        <div className="flex items-center gap-3 pb-2">
          <input
            type="search"
            value={query}
            aria-label={label ? `Filter ${label}` : "Filter rows"}
            placeholder="filter"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            className={cn(
              "min-w-[10rem] flex-1 rounded-none border border-hair bg-transparent px-2 py-1",
              "font-mono text-[0.75rem] text-ink placeholder:text-ink-mute",
              "focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-accent",
            )}
          />
          <span aria-live="polite" className="font-mono text-[0.72rem] text-ink-mute">
            {view.length}/{safe.length}
          </span>
        </div>
      ) : null}
      {view.length ? (
        table
      ) : (
        <p className="py-2 font-mono text-[0.72rem] text-ink-mute">{noMatch}</p>
      )}
      {pageSize && pages > 1 ? (
        <div className="flex items-center gap-3 border-t border-hair pt-2 font-mono text-[0.72rem]">
          <button
            type="button"
            className={CONTROL}
            disabled={current === 0}
            aria-label="Previous page"
            onClick={() => setPage(current - 1)}
          >
            ‹ prev
          </button>
          <span className="text-ink-soft">
            {current + 1} / {pages}
          </span>
          <button
            type="button"
            className={CONTROL}
            disabled={current >= pages - 1}
            aria-label="Next page"
            onClick={() => setPage(current + 1)}
          >
            next ›
          </button>
        </div>
      ) : null}
    </div>
  );
}
