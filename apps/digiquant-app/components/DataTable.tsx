'use client';

import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react';

export type Col<R> = {
  key: string;
  label: string;
  num?: boolean;
  /** Long text: wraps within the column and clamps to 3 lines instead of widening the table. */
  wrap?: boolean;
  /** Inline weight bar under the figure, 0–100. */
  bar?: (r: R) => number | null;
  cell: (r: R) => ReactNode;
  tone?: (r: R) => 'pos' | 'neg' | undefined;
  /** Sortable column. `true` sorts by the cell text/number; a function gives the sort value (null sorts last). */
  sort?: boolean | ((r: R) => string | number | null | undefined);
  /** Plain text for the filter box; defaults to the sort value or a string/number cell. */
  text?: (r: R) => string;
};

type Dir = 'asc' | 'desc';
type Variant = 'grp' | 'total' | 'sel';

const prim = (v: ReactNode): string | number | null => (typeof v === 'string' || typeof v === 'number' ? v : null);
const sortVal = <R,>(c: Col<R>, r: R): string | number | null => {
  const v = typeof c.sort === 'function' ? c.sort(r) : prim(c.cell(r));
  return typeof v === 'number' && !Number.isFinite(v) ? null : (v ?? null);
};
const cmp = (a: string | number | null, b: string | number | null, dir: Dir) => {
  if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1; // nulls last in both directions
  const d = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true });
  return dir === 'asc' ? d : -d;
};

/**
 * Table atom — hairline rows, mono right-aligned figures, sticky header. Row variants: grp, total.
 * v2 (all opt-in): sortable columns, text filter, row click, sticky first column, pagination.
 * With none of those props it renders the bare table exactly as before.
 */
export function DataTable<R>({ rows, cols, rowKey, variant, empty = 'no rows', filter, onRowClick, stickyFirst, pageSize }: {
  rows: R[];
  cols: Col<R>[];
  rowKey: (r: R, i: number) => string;
  variant?: (r: R) => Variant | undefined;
  empty?: string;
  /** Show a text filter box (matches any column's text). */
  filter?: boolean;
  /** Row click / Enter / Space. Rows become keyboard-focusable. */
  onRowClick?: (r: R, i: number) => void;
  /** Pin the first column while scrolling horizontally. */
  stickyFirst?: boolean;
  /** Rows per page; omit for no pagination. */
  pageSize?: number;
}) {
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<{ key: string; dir: Dir } | null>(null);
  const [page, setPage] = useState(0);
  const safe = Array.isArray(rows) ? rows : [];

  const view = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = safe.map((r, i) => ({ r, i }));
    if (needle) {
      out = out.filter(({ r }) => cols.some((c) => {
        const t = c.text ? c.text(r) : sortVal(c, r);
        return t != null && String(t).toLowerCase().includes(needle);
      }));
    }
    const col = sort && cols.find((c) => c.key === sort.key);
    if (col && sort) {
      // Total rows stay pinned at the end; everything else sorts.
      const tail = out.filter(({ r }) => variant?.(r) === 'total');
      const body = out.filter(({ r }) => variant?.(r) !== 'total');
      body.sort((a, b) => cmp(sortVal(col, a.r), sortVal(col, b.r), sort.dir) || a.i - b.i);
      out = [...body, ...tail];
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safe, cols, q, sort, variant]);

  if (!safe.length) return <p className="note mute">{empty}</p>;

  const pages = pageSize ? Math.max(1, Math.ceil(view.length / pageSize)) : 1;
  const cur = Math.min(page, pages - 1);
  const shown = pageSize ? view.slice(cur * pageSize, (cur + 1) * pageSize) : view;
  const v2 = !!(filter || pageSize);

  const toggle = (key: string) => {
    setPage(0);
    setSort((s) => (!s || s.key !== key ? { key, dir: 'asc' } : s.dir === 'asc' ? { key, dir: 'desc' } : null));
  };
  const onKey = (e: KeyboardEvent, r: R, i: number) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick?.(r, i); }
  };

  const table = (
    <table className={`tbl${stickyFirst ? ' stick1' : ''}${onRowClick ? ' clickable' : ''}`}>
      <thead>
        <tr>
          {cols.map((c) => {
            const on = sort?.key === c.key ? sort.dir : null;
            return (
              <th key={c.key} className={c.num ? 'num' : undefined} aria-sort={on ? (on === 'asc' ? 'ascending' : 'descending') : c.sort ? 'none' : undefined}>
                {c.sort ? (
                  <button type="button" className="th-sort" onClick={() => toggle(c.key)}>
                    {c.label}<span className="th-dir" aria-hidden="true">{on === 'asc' ? '▲' : on === 'desc' ? '▼' : ''}</span>
                  </button>
                ) : c.label}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {shown.map(({ r, i }) => (
          <tr
            key={rowKey(r, i)}
            className={variant?.(r)}
            tabIndex={onRowClick ? 0 : undefined}
            onClick={onRowClick ? () => onRowClick(r, i) : undefined}
            onKeyDown={onRowClick ? (e) => onKey(e, r, i) : undefined}
          >
            {cols.map((c) => {
              const w = c.bar?.(r);
              const cls = [c.num ? 'num' : '', c.wrap ? 'wrap' : '', c.tone?.(r) ?? ''].join(' ').trim() || undefined;
              return (
                <td key={c.key} className={cls}>
                  {c.wrap ? <span className="clamp">{c.cell(r)}</span> : c.cell(r)}
                  {w != null && Number.isFinite(w) ? <span className="bar"><i style={{ width: `${Math.max(0, Math.min(100, w))}%` }} /></span> : null}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );

  if (!v2) return table;
  return (
    <>
      {filter ? (
        <div className="tbl-bar">
          <input className="tbl-filter mono" type="search" placeholder="filter" aria-label="Filter rows" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          <span className="mono mute">{view.length}/{safe.length}</span>
        </div>
      ) : null}
      {view.length ? table : <p className="note mute">no match</p>}
      {pageSize && pages > 1 ? (
        <div className="tbl-pager mono">
          <button type="button" disabled={cur === 0} onClick={() => setPage(cur - 1)} aria-label="Previous page">‹ prev</button>
          <span>{cur + 1} / {pages}</span>
          <button type="button" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} aria-label="Next page">next ›</button>
        </div>
      ) : null}
    </>
  );
}
